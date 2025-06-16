ALLOWED_EXTENSIONS = ['pdf']
NUMBERS = [str(i) for i in range(500)]
BAD_VALUES = ['БН', 'БН'.lower(), 'Б/Н', 'Б/Н'.lower(), 'Б.Н.', 'Б.Н.'.lower(), '', '-', '—', ' ']
TERGET_HEADER = ['№\nп/п', 'Кат. номер', 'Наименование', 'Цена, рубли', 'Износ, %', 'Кол-во', 'Сумма, Рубли', 'Сумма с\nизносом, Рубли']
EMEX_BASE_URL = 'https://emex.ru/products'
DOMAIN_PATTERN = r'https?://([^/]+)'
BASE_PVZ = '38140'
BRAND_DETECT = ['марка', 'модель']
TARGET_JSON_KEYS = ['originals', 'analogs']
FOUND_TABLE_HEADER = ['Номер (оригинал)',
                      'Номер (найден)',
                      'Оригинал',
                      'Наименование',
                      'Производитель',
                      'Рейтинг',
                      'Срок доставки (дн.)',
                      'Цена (руб.)',
                      'Кол-во',
                      'Сумма (руб.)',
                      'Источник']
NOT_FOUND_TABLE_HEADER = ['Кат. номер', 'Наименование', 'Цена, руб.', 'Кол-во', 'Сумма, руб.']
PROXY_USER = "P1vZXL"
PROXY_PASS = "IkL18ZoERM"
YES = 'Да'
NO = 'Нет'
