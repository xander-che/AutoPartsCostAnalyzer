NUMBERS = [str(i) for i in range(200)]
BAD_VALUES = ['БН', 'БН'.lower(), 'Б/Н', 'Б/Н'.lower(), 'Б.Н.', 'Б.Н.'.lower(), '', '-', '—']
EMEX_BASE_URL = 'https://emex.ru/products'
BASE_PVZ = '38140'
BRAND_DETECT = ['марка', 'модель']
TARGET_JSON_KEYS = ['originals', 'analogs']