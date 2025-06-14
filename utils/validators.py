ALLOWED_EXTENSIONS = ['pdf']

def allowed_file_type(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_entry_qty(entry_key_qty_list: list, key: str) -> int:
    entry_qty = 0
    for item in entry_key_qty_list:
        if item[0] == key:
            entry_qty = item[1]
            break

    if not entry_qty:
        entry_qty = 1

    return entry_qty
