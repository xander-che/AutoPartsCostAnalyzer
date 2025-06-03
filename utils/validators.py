ALLOWED_EXTENSIONS = ['pdf']

def allowed_file_type(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS