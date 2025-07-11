import os
import tempfile
import pdfplumber
from models.data_models import EntryParams, RawTables
from flask import jsonify, request
from static.messages import ERROR_FILE_TYPE


def get_params_dict() -> EntryParams:

    rating = float(request.form.get('rating', 4.0))
    availability = int(request.form.get('availability', 10))
    delivery_time = int(request.form.get('delivery_time', 7))
    data_source = request.form.get('data_source', 'emex.ru')
    pvz_code = request.form.get('pvz_code', '38140')
    strict_compliance = request.form.get('strict_match', 'off')
    proxy_ip = request.form.get('proxy_ip', '192.168.1.1')
    proxy_port = request.form.get('proxy_port', '8080')

    return EntryParams(rating=rating,
                       availability=availability,
                       delivery_time=delivery_time,
                       data_source=data_source,
                       pvz_code=pvz_code,
                       strict_compliance=strict_compliance,
                       proxy_ip=proxy_ip,
                       proxy_port=proxy_port)


def pdf_parser(file):
    results = list()

    results.append(get_params_dict())

    try:
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

        os.unlink(tmp_path)

        return jsonify(results)

    except Exception as e:
        if tmp_path in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return jsonify({'error': ERROR_FILE_TYPE}), 500


