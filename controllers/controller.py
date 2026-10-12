import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, render_template, request
from werkzeug.wrappers import Response

from services.entry_data_processing import get_params_dict, pdf_parser
from services.exist_parser import ExistParser
from services.autopiter_parser import AutopiterParser
from services.sale_parts_parser import SalePartsParser
from services.prepare_data import get_brand, get_out_tables, get_tables_data
from services.web_parser import EMEXParser
from static.constants import (BASE_PVZ,
                              DATA_SOURCE_EMEX,
                              DATA_SOURCE_EXIST,
                              DATA_SOURCE_AUTOPITER,
                              DATA_SOURCE_SALE_PARTS,
                              DATA_SOURCES,
                              FOUND_TABLE_HEADER,
                              NOT_FOUND_TABLE_HEADER)
from static.messages import (ERROR_EMEX_UNAVAILABLE,
                             ERROR_EMPTY_TABLES,
                             ERROR_EXIST_UNAVAILABLE,
                             ERROR_AUTOPITER_UNAVAILABLE,
                             ERROR_SALE_PARTS_UNAVAILABLE,
                             ERROR_FILE_TYPE,
                             ERROR_INTERNAL,
                             ERROR_NO_SELECTED_FILE,
                             ERROR_NOT_FILE_PART,
                             ERROR_NOT_PROXY_ENABLED,
                             ERROR_UNKNOWN_DATA_SOURCE,
                             NO_DATA_FOUND)
from utils.validators import allowed_file_type


logger = logging.getLogger(__name__)
params = Blueprint('pdf', __name__)

JOB_TTL_SECONDS = int(os.getenv('JOB_TTL_SECONDS', '3600'))
# A file-backed store lets every Gunicorn worker on this host see the same jobs.
JOB_STORE_PATH = os.getenv('JOB_STORE_PATH', os.path.join('instance', 'jobs.sqlite3'))
_jobs = {}
_jobs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv('SEARCH_WORKERS', '2'))),
                               thread_name_prefix='parts-search')


def _connect_job_store():
    directory = os.path.dirname(os.path.abspath(JOB_STORE_PATH))
    os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(JOB_STORE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _init_job_store() -> None:
    connection = _connect_job_store()
    try:
        with connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL
                )
            ''')
    finally:
        connection.close()


_init_job_store()


def _save_job(job_id: str, job: dict) -> None:
    payload = json.dumps(job, ensure_ascii=False)
    connection = _connect_job_store()
    try:
        with connection:
            connection.execute('''
                INSERT INTO jobs (job_id, payload, updated_at, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at,
                    status = excluded.status
            ''', (job_id, payload, job.get('updated_at', time.time()), job.get('status', 'queued')))
    finally:
        connection.close()


def _load_job(job_id: str):
    connection = _connect_job_store()
    try:
        row = connection.execute('SELECT payload FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
    finally:
        connection.close()
    return json.loads(row['payload']) if row else None


def is_error_response(value) -> bool:
    return isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], Response)


def get_parser(entry_params: dict, brand: str, entry_table_data: list):
    data_source = entry_params.get('data_source', DATA_SOURCE_EMEX)

    if data_source == DATA_SOURCE_EXIST:
        return ExistParser(entry_params, BASE_PVZ, brand, entry_table_data)
    if data_source == DATA_SOURCE_EMEX:
        return EMEXParser(entry_params, BASE_PVZ, brand, entry_table_data)
    if data_source == DATA_SOURCE_AUTOPITER:
        return AutopiterParser(entry_params, BASE_PVZ, brand, entry_table_data)
    if data_source == DATA_SOURCE_SALE_PARTS:
        return SalePartsParser(entry_params, BASE_PVZ, brand, entry_table_data)
    return None


def get_parsers(entry_params: dict, brand: str, entry_table_data: list):
    selected = entry_params.get('data_sources') or entry_params.get('data_source') or DATA_SOURCE_EMEX
    if isinstance(selected, str):
        selected = [selected]

    parsers = []
    for data_source in selected:
        if data_source not in DATA_SOURCES:
            continue
        source_params = {**entry_params, 'data_source': data_source}
        parser = get_parser(source_params, brand, entry_table_data)
        if parser is not None:
            parsers.append(parser)
    return parsers


def _cleanup_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    connection = _connect_job_store()
    try:
        with connection:
            connection.execute('''
                DELETE FROM jobs WHERE updated_at < ? AND status IN ('completed', 'failed')
            ''', (cutoff,))
    finally:
        connection.close()
    with _jobs_lock:
        expired = [job_id for job_id, job in _jobs.items()
                   if job.get('updated_at', 0) < cutoff and job.get('status') in {'completed', 'failed'}]
        for job_id in expired:
            _jobs.pop(job_id, None)


def _update_job(job_id: str, **values) -> None:
    with _jobs_lock:
        job = _load_job(job_id) or _jobs.get(job_id)
        if job is None:
            return
        job.update(values)
        job['updated_at'] = time.time()
        _jobs[job_id] = job
        _save_job(job_id, job)


def _normalized_part_number(value) -> str:
    return re.sub(r'[^0-9A-ZА-Я]', '', str(value or '').upper())


def _get_source_totals(results: list, entry_key_qty_list: list, selected_sources: list) -> list:
    quantities_by_key = {}
    for key_number, quantity in entry_key_qty_list:
        normalized_key = _normalized_part_number(key_number)
        quantities_by_key[normalized_key] = quantities_by_key.get(normalized_key, 0) + int(quantity or 1)

    source_order = list(dict.fromkeys(selected_sources))
    prices_by_source = {source: {} for source in source_order}
    for item in results:
        source = getattr(item, 'source', 'сайт')
        if source not in prices_by_source:
            prices_by_source[source] = {}
            source_order.append(source)

        normalized_key = _normalized_part_number(item.key_number)
        price = float(item.price or 0)
        previous = prices_by_source[source].get(normalized_key)
        if previous is None or price < previous:
            prices_by_source[source][normalized_key] = price

    totals = []
    total_positions = len(quantities_by_key)
    for source in source_order:
        source_prices = prices_by_source[source]
        found_positions = len(source_prices)
        total_sum = sum(price * quantities_by_key.get(key, 1)
                        for key, price in source_prices.items())
        totals.append({'source': source,
                       'found_count': found_positions,
                       'total_count': total_positions,
                       'total_sum': round(total_sum, 2)})
    return totals


def _search_job(job_id: str,
                parser,
                entry_key_qty_list: list,
                total_table: list,
                single_item_search: bool = False,
                offer_mode: str = 'per_source') -> None:
    _update_job(job_id, status='running')

    try:
        parsers = parser if isinstance(parser, (list, tuple)) else [parser]
        source_errors = {}
        all_results = []
        known_errors = {
            ERROR_NOT_PROXY_ENABLED,
            ERROR_EXIST_UNAVAILABLE,
            ERROR_EMEX_UNAVAILABLE,
            ERROR_AUTOPITER_UNAVAILABLE,
            ERROR_SALE_PARTS_UNAVAILABLE,
        }

        with ThreadPoolExecutor(max_workers=max(1, len(parsers)),
                                thread_name_prefix='parts-source') as source_executor:
            futures = {source_executor.submit(source_parser.search_data): source_parser
                       for source_parser in parsers}
            for future, source_parser in futures.items():
                source = (source_parser.entry_params.get('data_source') or
                          getattr(source_parser, 'source_name', 'сайт'))
                try:
                    result = future.result()
                except Exception:
                    logger.exception('Не удалось выполнить поиск на %s', source)
                    source_errors[source] = ERROR_INTERNAL
                    continue

                if len(result) == 1 and isinstance(result[0], str):
                    if result[0] in known_errors:
                        source_errors[source] = result[0]
                    elif result[0] != NO_DATA_FOUND:
                        source_errors[source] = result[0]
                elif result:
                    for offer in result:
                        offer.source = source
                    all_results.extend(result)

        if not all_results:
            if source_errors:
                error_text = '; '.join(f'{source}: {message}'
                                       for source, message in source_errors.items())
            else:
                error_text = NO_DATA_FOUND
            _update_job(job_id,
                        status='completed',
                        result={'error': error_text, 'source_errors': source_errors})
            return

        selected_sources = [source_parser.entry_params.get('data_source') or
                            getattr(source_parser, 'source_name', 'сайт')
                            for source_parser in parsers]
        source_totals = _get_source_totals(all_results, entry_key_qty_list, selected_sources)
        if offer_mode == 'mix':
            cheapest_by_key = {}
            for offer in all_results:
                normalized_key = _normalized_part_number(offer.key_number)
                current = cheapest_by_key.get(normalized_key)
                if current is None or float(offer.price or 0) < float(current.price or 0):
                    cheapest_by_key[normalized_key] = offer

            key_order = list(dict.fromkeys(_normalized_part_number(key)
                                           for key, _ in entry_key_qty_list))
            all_results = [cheapest_by_key[key] for key in key_order if key in cheapest_by_key]

        result_table = get_out_tables(all_results,
                                      entry_key_qty_list,
                                      FOUND_TABLE_HEADER,
                                      total_table,
                                      NOT_FOUND_TABLE_HEADER)
        result = result_table.get_out_tables()
        if single_item_search:
            # При поиске одной детали строки показывают отдельные предложения
            # выбранных сайтов, а их сумма не является итоговой стоимостью.
            result['found']['total_sum'] = ''
            result['not_found']['rows'] = []
            result['not_found']['total_sum'] = ''
            result.pop('total_comparison', None)
        elif offer_mode == 'per_source':
            # Строки содержат альтернативы с сайтов; общую сумму строим
            # отдельно по каждому сайту, чтобы не складывать варианты между собой.
            result['found']['total_sum'] = ''
            result.pop('total_comparison', None)
            result['source_totals'] = source_totals
        if source_errors:
            result['source_errors'] = source_errors
        _update_job(job_id, status='completed', result=result)
    except Exception:
        logger.exception('Необработанная ошибка фонового поиска')
        _update_job(job_id, status='failed', result={'error': ERROR_INTERNAL})


@params.route('/')
def index():
    return render_template('upload.html')


@params.route('/health')
def health():
    return jsonify({'status': 'ok'})


@params.route('/upload_data', methods=['POST'])
def upload_data():
    if 'file' not in request.files:
        return jsonify({'error': ERROR_NOT_FILE_PART}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': ERROR_NO_SELECTED_FILE}), 400
    if not allowed_file_type(file.filename):
        return jsonify({'error': ERROR_FILE_TYPE}), 400

    return pdf_parser(file=file)


@params.route('/run_process', methods=['POST'])
def run_process():
    """Быстро разбирает PDF и запускает сетевой поиск в фоне.

    Ответ 202 не держит nginx/CDN-соединение минутами и избавляет от 504.
    """

    part_number = str(request.form.get('part_number') or '').strip()
    single_item_search = bool(part_number)
    offer_mode = str(request.form.get('offer_mode') or 'per_source').strip()
    if offer_mode not in {'per_source', 'mix'}:
        return jsonify({'error': 'Выберите корректный режим сравнения.'}), 400

    if single_item_search:
        if len(part_number) > 100 or any(ord(char) < 32 for char in part_number):
            return jsonify({'error': 'Введите корректный артикул (не более 100 символов).'}), 400
        try:
            entry_params = get_params_dict().params_to_dict()['params'][0]
        except ValueError as error:
            return jsonify({'error': str(error)}), 400

        # Формат строки совпадает с данными, которые парсеры получают из PDF.
        entry_table_data = [['1', part_number, part_number, '0', '', '1', '0', '']]
        entry_key_qty_list = [(part_number, 1)]
        total_table = []
        target_brand = ''
    else:
        uploaded = upload_data()
        if is_error_response(uploaded):
            return uploaded

        raw_results = uploaded.get_json()
        if not isinstance(raw_results, list) or not raw_results:
            return jsonify({'error': ERROR_EMPTY_TABLES}), 400

        entry_params = raw_results[0]
        raw_entry_tables = raw_results[1:]
        if not raw_entry_tables:
            return jsonify({'error': ERROR_EMPTY_TABLES}), 400

        tables = get_tables_data(raw_entry_tables)
        if is_error_response(tables):
            return tables

        entry_table_data, _, total_table = tables
        entry_key_qty_list = [(item[1], item[4]) for item in entry_table_data]
        target_brand = get_brand(raw_entry_tables)
    parsers = get_parsers(entry_params, target_brand, entry_table_data)

    if not parsers:
        return jsonify({'error': ERROR_UNKNOWN_DATA_SOURCE}), 400

    _cleanup_jobs()
    job_id = secrets.token_urlsafe(18)
    now = time.time()
    with _jobs_lock:
        job = {'status': 'queued', 'created_at': now, 'updated_at': now}
        _jobs[job_id] = job
        _save_job(job_id, job)

    _executor.submit(_search_job,
                     job_id,
                     parsers,
                     entry_key_qty_list,
                     total_table,
                     single_item_search,
                     offer_mode)
    return jsonify({'job_id': job_id, 'status': 'queued'}), 202


@params.route('/process_status/<job_id>', methods=['GET'])
def process_status(job_id: str):
    _cleanup_jobs()
    job = _load_job(job_id)
    if job is None:
        # Keep compatibility with jobs seeded directly by older integrations.
        with _jobs_lock:
            job = dict(_jobs.get(job_id) or {})

    if not job:
        return jsonify({'error': 'Задача не найдена или уже удалена'}), 404

    job.pop('created_at', None)
    job.pop('updated_at', None)
    return jsonify(job)
