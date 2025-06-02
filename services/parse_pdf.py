import os
import tempfile
import pdfplumber
from models.entry_data_model import EntryParams, RawTables
from flask import request, jsonify


def pdf_parser(file: request.files, rating: float, availability: int, delivery_time: int, data_source: str):
    results = list()

    results.append(EntryParams(
        rating=rating,
        availability=availability,
        delivery_time=delivery_time,
        data_source=data_source
    ))

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
        return jsonify({'error': 'Only PDF files are allowed'}), 500

