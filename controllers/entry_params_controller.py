from flask import Flask, Blueprint, request, jsonify, render_template
from utils.validators import allowed_file_type
from services.parse_pdf import pdf_parser

params = Blueprint('pdf', __name__)


@params.route('/')
def index():
    return render_template('upload.html')


@params.route('/upload', methods=['POST'])
def upload_file():

    rating = float(request.form.get('rating', 4.0))
    availability = int(request.form.get('availability', 10))
    delivery_time = int(request.form.get('delivery_time', 7))
    data_source = request.form.get('data_source', 'emex.ru')

    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not allowed_file_type(file.filename):
        return jsonify({'error': 'Only PDF files are allowed'}), 400

    results = pdf_parser(file=file,
                         rating=rating,
                         availability=availability,
                         delivery_time=delivery_time,
                         data_source=data_source
                         )

    return results
