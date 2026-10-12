import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, render_template, request
from werkzeug.wrappers import Response

from services.entry_data_processing import pdf_parser
from services.exist_parser import ExistParser
from services.prepare_data import get_brand, get_out_tables, get_tables_data
from services.web_parser import EMEXParser
from static.constants import (BASE_PVZ,
                              DATA_SOURCE_EMEX,
                              DATA_SOURCE_EXIST,
                              FOUND_TABLE_HEADER,
                              NOT_FOUND_TABLE_HEADER)
from static.messages import (ERROR_EMEX_UNAVAILABLE,
                             ERROR_EMPTY_TABLES,
                             ERROR_EXIST_UNAVAILABLE,
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
    return None


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


def _search_job(job_id: str,
                parser,
                entry_key_qty_list: list,
                total_table: list) -> None:
    _update_job(job_id, status='running')

    try:
        result = parser.search_data()

        known_errors = {ERROR_NOT_PROXY_ENABLED, ERROR_EXIST_UNAVAILABLE, ERROR_EMEX_UNAVAILABLE}
        if len(result) == 1 and isinstance(result[0], str) and result[0] in known_errors:
            _update_job(job_id, status='completed', result={'error': result[0]})
            return

        if not result:
            _update_job(job_id, status='completed', result={'error': NO_DATA_FOUND})
            return

        result_table = get_out_tables(result,
                                      entry_key_qty_list,
                                      FOUND_TABLE_HEADER,
                                      total_table,
                                      NOT_FOUND_TABLE_HEADER)
        _update_job(job_id, status='completed', result=result_table.get_out_tables())
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
    parser = get_parser(entry_params, target_brand, entry_table_data)

    if parser is None:
        return jsonify({'error': ERROR_UNKNOWN_DATA_SOURCE}), 400

    _cleanup_jobs()
    job_id = secrets.token_urlsafe(18)
    now = time.time()
    with _jobs_lock:
        job = {'status': 'queued', 'created_at': now, 'updated_at': now}
        _jobs[job_id] = job
        _save_job(job_id, job)

    _executor.submit(_search_job, job_id, parser, entry_key_qty_list, total_table)
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
