from flask import Blueprint, request, jsonify, render_template
from services.prepare_data import get_brand, get_tables_data, get_out_tables
from services.web_parser import EMEXParser
from static.constants import BASE_PVZ, FOUND_TABLE_HEADER, NOT_FOUND_TABLE_HEADER
from static.messages import ERROR_EMPTY_TABLES, ERROR_FILE_TYPE, ERROR_NO_SELECTED_FILE, ERROR_NOT_FILE_PART, \
    ERROR_NOT_PROXY_ENABLED, NO_DATA_FOUND
from utils.validators import allowed_file_type
from services.entry_data_processing import pdf_parser

params = Blueprint('pdf', __name__)


@params.route('/')
def index():
    return render_template('upload.html')


@params.route('/upload_data', methods=['GET'])
def upload_data():

    if 'file' not in request.files:
        return jsonify({'error': ERROR_NOT_FILE_PART}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': ERROR_NO_SELECTED_FILE}), 400

    if not allowed_file_type(file.filename):
        return jsonify({'error': ERROR_FILE_TYPE}), 400


    results = pdf_parser(file=file)

    return results


@params.route('/run_process', methods=['POST'])
def run_process():

    raw_results = upload_data().get_json()

    entry_params = raw_results[0]
    print(__name__, entry_params)
    raw_entry_tables = raw_results[1:]

    if len(raw_entry_tables) == 0:
        return jsonify({'error': ERROR_EMPTY_TABLES}), 400

    entry_table_data, raw_key_list, total_table = get_tables_data(raw_entry_tables)
    entry_key_qty_list = [(item[1], item[4]) for item in entry_table_data]
    print(__name__, entry_key_qty_list)
    target_brand = get_brand(raw_entry_tables)

    print(__name__, entry_table_data)
    print(__name__, target_brand)

    emex_parser = EMEXParser(entry_params, BASE_PVZ, target_brand, entry_table_data)
    result = emex_parser.search_data()

    if result[0] == ERROR_NOT_PROXY_ENABLED:
        return jsonify({'error': ERROR_NOT_PROXY_ENABLED}), 305
    elif len(result) == 0:
        return jsonify({'error': NO_DATA_FOUND}), 200


    result_table = get_out_tables(result,
                                  entry_key_qty_list,
                                  FOUND_TABLE_HEADER,
                                  total_table,
                                  NOT_FOUND_TABLE_HEADER)
    print(__name__, result_table)
    print(__name__, jsonify(result_table.get_out_tables()))

    return jsonify(result_table.get_out_tables())