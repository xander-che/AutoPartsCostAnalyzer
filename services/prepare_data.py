import re
import logging
from typing import Any
from flask import jsonify, Response
from models.data_models import OutTables
from static.constants import BAD_VALUES, BRAND_DETECT, DOMAIN_PATTERN, ENTRY_REQUIRED_COLUMNS
from static.messages import ERROR_NO_TABLES


logger = logging.getLogger(__name__)


def normalize_header_cell(value) -> str:
    """Название колонки в виде, пригодном для сравнения."""

    return re.sub(r'\s+', ' ', str(value or '')).strip().lower()


def parse_number(value) -> float:
    """Преобразует PDF-число с пробелами, NBSP и десятичной запятой."""

    normalized = str(value or '').replace('\xa0', '').replace(' ', '').replace(',', '.')
    return float(normalized)


def is_price_column(title: str) -> bool:
    """Цена детали: «Цена, рубли», «Цена, руб.», «Стоимость детали, руб.»,

    но не «Источник цены» и не «Стоимость с учётом износа».
    """

    if title.startswith('цена'):
        return True

    return title.startswith('стоимость') and 'износ' not in title


def resolve_entry_columns(header: list) -> dict | None:
    """Определяет колонки таблицы запчастей по названиям заголовков.

    Страховые компании оформляют таблицу по-разному: меняют порядок и названия
    колонок, добавляют свои («Источник цены» у РГС), переносят текст по строкам
    («Кол-во» как «Кол-\\nво»). Поэтому ориентируемся на названия, а не на позиции.
    """

    columns = dict()

    for index, cell in enumerate(header or []):
        title = normalize_header_cell(cell)

        if not title:
            continue

        if 'position' not in columns and title.startswith('№'):
            columns['position'] = index
        elif 'key_number' not in columns and title.startswith('кат'):
            columns['key_number'] = index
        elif 'name' not in columns and title.startswith('наименован'):
            columns['name'] = index
        elif 'price' not in columns and is_price_column(title):
            columns['price'] = index
        elif 'wear' not in columns and title.startswith('износ'):
            columns['wear'] = index
        elif 'quantity' not in columns and title.startswith('кол'):
            columns['quantity'] = index
        elif 'total_with_wear' not in columns and title.startswith('сумма') and 'износом' in title:
            columns['total_with_wear'] = index
        elif 'total' not in columns and title.startswith('сумма'):
            columns['total'] = index

    if not ENTRY_REQUIRED_COLUMNS <= set(columns):
        return None

    return columns


def normalize_entry_row(row: list, columns: dict) -> list:
    """Строка таблицы запчастей в едином порядке колонок.

    Порядок совпадает с TERGET_HEADER: №, номер, наименование, цена, износ,
    количество, сумма, сумма с износом.
    """

    def cell(field: str, default_index: int = None) -> str:
        index = columns.get(field, default_index)

        if index is None or index >= len(row):
            return ''

        return row[index] or ''

    price = cell('price')
    quantity = cell('quantity') or '1'

    return [cell('position', 0),
            cell('key_number'),
            cell('name'),
            price,
            cell('wear'),
            quantity,
            cell('total'),
            cell('total_with_wear')]


def get_tables_data(raw_data: dict) -> tuple[Response, int] | tuple[list[Any], list[Any], list[Any]]:

    # Один акт может содержать одну и ту же калькуляцию дважды: в основном отчёте
    # и в приложении. Храним лучший вариант строки и не отправляем дубли на сайты.
    rows_by_identity = {}
    row_order = []

    for items in raw_data:
        table = items.get('table') or []

        if not table:
            continue

        columns = resolve_entry_columns(table[0])

        if columns is None:
            continue

        position_index = columns.get('position', 0)
        row_score = (1 if 'quantity' in columns else 0,
                     1 if 'total' in columns else 0)

        for item in table[1:]:
            if not item or position_index >= len(item):
                continue

            # В некоторых актах номер позиции имеет вид "12." или "12)".
            if not re.fullmatch(r'\d+[.)]?', str(item[position_index] or '').strip()):
                continue

            row = normalize_entry_row(item, columns)
            identity = (str(row[0]).strip(),
                        re.sub(r'[^0-9A-ZА-Я]', '', str(row[1]).upper()),
                        normalize_header_cell(row[2]))

            target_row = None
            try:
                price = parse_number(row[3])
                quantity = int(parse_number(row[5]))
                if quantity < 1:
                    raise ValueError('количество должно быть больше нуля')

                if row[1] not in BAD_VALUES:
                    target_row = [row[0], row[1], row[2], price, quantity]
            except (TypeError, ValueError) as error:
                logger.info('Пропущена строка PDF с неверными числами: %s', error)
                continue

            previous = rows_by_identity.get(identity)
            if previous is None:
                row_order.append(identity)

            if previous is None or row_score > previous['score']:
                rows_by_identity[identity] = {
                    'row': row,
                    'target': target_row,
                    'score': row_score
                }

    entry_table_data = []
    target_table_data = []
    raw_key_list = []

    for identity in row_order:
        candidate = rows_by_identity[identity]
        row = candidate['row']
        raw_key_list.append(row[1])
        entry_table_data.append(row)

        if candidate['target'] is not None:
            target_table_data.append(candidate['target'])

    if len(target_table_data) == 0:
        return jsonify({'error': ERROR_NO_TABLES}), 400

    return target_table_data, raw_key_list, entry_table_data


def get_brand(raw_data: dict) -> str:
    brand = 'FORD'  # default brand

    # Марка авто лежит в отдельной таблице, а перед ней могут идти данные страховщика,
    # поэтому просматриваем все таблицы, а не только первую
    for items in raw_data:
        for item in items.get('table') or []:
            if not item or len(item) < 2:
                continue

            title = normalize_header_cell(item[0])
            split_text = title.split(',')

            if not any(word.strip() in BRAND_DETECT for word in split_text):
                continue

            value = re.sub(r'\s+', ' ', str(item[1] or '')).strip().upper()
            if not value:
                continue

            # В строке «Марка, модель» значение имеет вид «CHERY TIGGO 8 ...».
            # Emex ожидает производителя, а не полное название автомобиля.
            if 'модель' in title:
                multi_word_brands = ('ALFA ROMEO', 'ASTON MARTIN', 'GREAT WALL',
                                     'LAND ROVER', 'MERCEDES BENZ', 'ROLLS ROYCE')
                value = next((brand for brand in multi_word_brands if value.startswith(brand)),
                             value.split(' ', 1)[0])

            return value.replace(' ', '%20')

    return brand


def get_out_tables(found_result: list,
                   entry_key_qty_list: list,
                   found_header: list,
                   total_table: list,
                   not_found_header: list) -> OutTables:
    # ['Номер (ориг)', 'Номер (найден)', 'Оригинал', 'Наименование', 'Производитель',  'Рейтинг', 'Срок доставки (дн.)', 'Цена (руб.)', 'Кол-во', 'Сумма (руб.)', 'Источник']
    found_rows = list()
    not_found_rows = list()
    found_prices_by_key = {}
    entry_quantities_by_key = {
        re.sub(r'[^0-9A-ZА-Я]', '', str(item[0] or '').upper()): 0
        for item in entry_key_qty_list
    }
    for key_number, quantity in entry_key_qty_list:
        normalized_key = re.sub(r'[^0-9A-ZА-Я]', '', str(key_number or '').upper())
        entry_quantities_by_key[normalized_key] += int(quantity or 1)
    found_total_sum = 0
    not_found_total_sum = 0
    initial_sum = 0
    final_sum = 0

    if len(found_result) > 0:
        for item in found_result:
            normalized_key = re.sub(r'[^0-9A-ZА-Я]', '', str(item.key_number or '').upper())
            offer_price = float(item.price or 0)
            current_best = found_prices_by_key.get(normalized_key)
            if current_best is None or offer_price < current_best:
                found_prices_by_key[normalized_key] = offer_price

            entry_qty = entry_quantities_by_key.get(normalized_key, 1)
            match = re.search(DOMAIN_PATTERN, item.link)
            found_rows.append([item.key_number,
                               item.detail_num,
                               item.is_original,
                               item.detail_name,
                               item.make_name,
                               item.rating,
                               item.delivery_time,
                               item.price,
                               str(entry_qty),
                               str(round(item.price * entry_qty, 2)),
                               {'text': match.group(1) if match else 'Источник', 'url': item.link}
                               ])

    found_total_sum = sum(
        round(price * entry_quantities_by_key.get(key, 1), 2)
        for key, price in found_prices_by_key.items()
    )

    # ['Кат. номер', 'Наименование', 'Цена, руб.', 'Кол-во', 'Сумма, руб.']
    for item in total_table:
        price = parse_number(item[3])
        quantity = int(parse_number(item[5]))
        initial_sum += price * quantity

        normalized_key = re.sub(r'[^0-9A-ZА-Я]', '', str(item[1] or '').upper())
        if normalized_key not in found_prices_by_key:
            not_found_total_sum += round(price * quantity, 2)
            not_found_rows.append([item[1], item[2], str(price), str(quantity),
                                   str(round(price * quantity, 2))])

    final_sum = round(found_total_sum + not_found_total_sum, 2)
    percentage = round((initial_sum - final_sum) / initial_sum * 100) if initial_sum else 0
    returned_percentage = str(percentage)

    return OutTables(found_header,
                     found_rows,
                     found_total_sum,
                     not_found_header,
                     not_found_rows,
                     not_found_total_sum,
                     initial_sum,
                     final_sum,
                     returned_percentage)
