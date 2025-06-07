from flask import Blueprint, request, jsonify, render_template
from services.prepare_data import get_target_table
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

    results = upload_data().get_json()

    entry_params = results[0]
    raw_entry_tables = results[1:]

    if len(raw_entry_tables) == 0:
        return jsonify({'error': ERROR_EMPTY_TABLES}), 400

    print(__name__, entry_params['availability'])

    target_table_data = get_target_table(raw_entry_tables)

    print(__name__, target_table_data)

    return results
