ALLOWED_EXTENSIONS = ['pdf']
NUMBERS = [str(i) for i in range(500)]
BAD_VALUES = ['БН', 'БН'.lower(), 'Б/Н', 'Б/Н'.lower(), 'Б.Н.', 'Б.Н.'.lower(), '', '-', '—', ' ']
TERGET_HEADER = ['№\nп/п', 'Кат. номер', 'Наименование', 'Цена, рубли', 'Износ, %', 'Кол-во', 'Сумма, Рубли', 'Сумма с\nизносом, Рубли']
EMEX_BASE_URL = 'https://emex.ru/products'
DOMAIN_PATTERN = r'https?://([^/]+)'
BASE_PVZ = '38140'
DATA_SOURCE_EMEX = 'emex.ru'
DATA_SOURCE_EXIST = 'exist.ru'
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

# --- exist.ru ---
EXIST_BASE_URL = 'https://exist.ru'
# Страница поиска по каталожному номеру: отдаёт список каталогов (pid), в которых он встречается
EXIST_SEARCH_URL = f'{EXIST_BASE_URL}/price/'
# Страница цен и заменителей конкретного каталога
EXIST_PRICE_URL = f'{EXIST_BASE_URL}/Price/'
# Метод страницы цен, возвращающий полный список предложений по позиции
EXIST_QUERY_URL = f'{EXIST_BASE_URL}/Price/Default.aspx/GetQuery'
EXIST_TIMEOUT = 30
# Ссылки на каталоги в результатах поиска по номеру: /Price/?pid=37213473
EXIST_CATALOG_LINK_PATTERN = r'/Price/\?pid=([0-9A-Fa-f]+)'
# Данные страницы цен: var _data = [ ... ];
EXIST_DATA_PATTERN = r'var\s+_data\s*=\s*'
# Скрытые поля страницы цен, нужные для запроса полного списка предложений
EXIST_HIDDEN_FIELDS = {'pid': 'hdnPid', 'hash': 'hfPidHash', 'src': 'hfSrcId'}
EXIST_MINUTES_PER_DAY = 24 * 60
EXIST_DEFAULT_MIN_QTY = 1
# «Склад поставщика. Заказывайте в необходимом количестве» — количество не ограничено
EXIST_UNLIMITED_QTY = 9999
# Эталонный номер для проверки доступности: встречается в каталогах exist.ru всегда.
# С дата-центров и зарубежных IP сайт открывается, но данных не отдаёт.
EXIST_CHECK_NUMBER = 'OC90'
YES = 'Да'
NO = 'Нет'
