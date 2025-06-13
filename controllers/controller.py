from flask import Blueprint, request, jsonify, render_template
from services.prepare_data import get_target_table, get_brand
from services.web_parser import EMEXParser
from static.constants import BASE_PVZ
from static.messages import ERROR_EMPTY_TABLES, ERROR_FILE_TYPE, ERROR_NO_SELECTED_FILE, ERROR_NOT_FILE_PART
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
    raw_entry_tables = raw_results[1:]

    if len(raw_entry_tables) == 0:
        return jsonify({'error': ERROR_EMPTY_TABLES}), 400

    entry_table_data = get_target_table(raw_entry_tables)
    target_brand = get_brand(raw_entry_tables)

    print(__name__, entry_table_data)
    tmp_list = list()
    not_found_list = list()
    print(__name__, target_brand)

    emex_parser = EMEXParser(entry_params, BASE_PVZ, target_brand, entry_table_data)
    result = emex_parser.search_data()
    print(__name__, result)

    price_total = 0
    not_found = 0
    for item in result:
        price_total += item.price
        tmp_list.append(item.key_number)
    for item in entry_table_data:
        if item[1] not in tmp_list:
            not_found += 1
            not_found_list.append(item[1])
    print(__name__, not_found_list)
    print(__name__, price_total)
    print(__name__, not_found)

    return jsonify(result).get_json()
