import os
import tempfile
import logging
import pdfplumber
from models.data_models import EntryParams, RawTables
from flask import jsonify, request
from static.constants import DATA_SOURCES, DATA_SOURCE_EMEX
from static.messages import ERROR_INVALID_PARAMS, ERROR_PDF_PROCESSING


logger = logging.getLogger(__name__)


def get_params_dict() -> EntryParams:
    try:
        rating = float(request.form.get('rating') or 4.0)
        availability = int(request.form.get('availability') or 1)
        delivery_time = int(request.form.get('delivery_time') or 7)
    except (TypeError, ValueError) as error:
        raise ValueError(ERROR_INVALID_PARAMS) from error

    if not 0 <= rating <= 5 or not 1 <= availability <= 9999 or not 1 <= delivery_time <= 365:
        raise ValueError(ERROR_INVALID_PARAMS)

    data_sources = request.form.getlist('data_sources')
    if not data_sources:
        legacy_source = request.form.get('data_source', DATA_SOURCE_EMEX)
        data_sources = [legacy_source] if legacy_source else []
    data_sources = list(dict.fromkeys(source for source in data_sources if source in DATA_SOURCES))
    if not data_sources:
        raise ValueError('Выберите хотя бы один сайт для поиска')
    data_source = data_sources[0]
    pvz_code = request.form.get('pvz_code', '38140')
    strict_compliance = request.form.get('strict_match', 'off')
    proxy_ip = request.form.get('proxy_ip', '').strip()
    proxy_port = request.form.get('proxy_port', '').strip()
    proxy_scheme = request.form.get('proxy_scheme', 'http').strip().lower()
    proxy_user = request.form.get('proxy_user', '').strip()
    proxy_password = request.form.get('proxy_password', '')

    return EntryParams(rating=rating,
                       availability=availability,
                       delivery_time=delivery_time,
                       data_source=data_source,
                       pvz_code=pvz_code,
                       strict_compliance=strict_compliance,
                       proxy_ip=proxy_ip,
                       proxy_port=proxy_port,
                       proxy_scheme=proxy_scheme,
                       proxy_user=proxy_user,
                       proxy_password=proxy_password,
                       data_sources=data_sources)


def pdf_parser(file):
    results = list()

    try:
        results.append(get_params_dict())

        with tempfile.NamedTemporaryFile(delete=False, prefix='.pdf') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        with pdfplumber.open(tmp_path) as pdf:
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                for j, table in enumerate(tables):
                    results.append(RawTables(
                        page=i+1,
                        table=table
                    ))

        return jsonify(results)

    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception:
        logger.exception('Ошибка разбора PDF')
        return jsonify({'error': ERROR_PDF_PROCESSING}), 500
    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


