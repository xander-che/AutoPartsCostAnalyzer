from typing import Any
from flask import jsonify, Response

from models.data_models import OutTables
from static.constants import NUMBERS, BAD_VALUES, BRAND_DETECT
from static.messages import ERROR_NO_TABLES
from utils.validators import get_entry_qty


def get_tables_data(raw_data: dict) -> tuple[Response, int] | tuple[list[Any], list[Any], list[Any]]:

    entry_table_data = list()
    raw_target_table = list()
    target_table_data = list()
    raw_key_list = list()
    entry_header = list()

    for items in raw_data:
        for item in items['table']:
            if item[0] in NUMBERS:
                raw_key_list.append(item[1])
                entry_table_data.append(item)
                if item[1] not in BAD_VALUES:
                    if len(entry_header) == 0:
                        entry_header.append(items['table'][0])
                    raw_target_table.append(item)

    print(__name__ , entry_header)
    # print(__name__, raw_key_list)

    if len(raw_target_table) == 0:
        return jsonify({'error': ERROR_NO_TABLES}), 400

    for item in raw_target_table:
        if len(item) == len(entry_header[0]):
            target_table_data.append([item[0], item[1], item[2], float(item[3].replace(' ', '')), int(item[5])])

    del raw_target_table

    return target_table_data, raw_key_list, entry_table_data


def get_brand(raw_data: dict) -> str:
    brand = 'FORD' # default brand
    for items in raw_data:
        for item in items['table']:
            split_text = item[0].split(',')
            for word in split_text:
                if word.lower() in BRAND_DETECT:
                    brand = ''.join(item[1].replace(' ', '%20')).upper()
                    break
            break
        break

    return brand


def get_out_tables(found_result: list,
                   entry_key_qty_list: list,
                   found_header: list,
                   total_table: list,
                   not_found_header: list) -> OutTables:
    # ['Номер', 'Наименование', 'Продавец', 'Рейтинг', 'Срок доставки (дн.)', 'Цена (руб.)', 'Кол-во', 'Сумма (руб.)', 'Ссылка']
    found_rows = list()
    not_found_rows = list()
    found_keys_list = list()
    found_total_sum = 0
    not_found_total_sum = 0
    initial_sum = 0
    final_sum = 0

    if len(found_result) > 0:
        for item in found_result:
            found_keys_list.append(item.key_number)
            entry_qty = get_entry_qty(entry_key_qty_list, item.key_number)
            found_total_sum += int(item.price*entry_qty)
            found_rows.append([item.key_number,
                         item.detail_name,
                         item.make_name,
                         item.rating,
                         item.delivery_time,
                         item.price,
                         str(entry_qty),
                         str(int(item.price*entry_qty)),
                         {'text': 'ссылка', 'url': f'{item.link}'}])

    # ['Кат. номер', 'Наименование', 'Цена, руб.', 'Кол-во', 'Сумма, руб.']
    for item in total_table:
        initial_sum += float(item[3].replace(' ', ''))
        if item[1] not in found_keys_list:
            price = float(item[3].replace(' ', ''))
            not_found_total_sum += int(price*int(item[5]))
            not_found_rows.append([item[1], item[2], str(int(price)), str(item[5]), str(int(price*int(item[5])))])

    if initial_sum == 0:
        initial_sum += 1

    final_sum += found_total_sum + not_found_total_sum
    percentage = final_sum/initial_sum

    if percentage < 1:
        returned_percentage = f'{100 - int(percentage*100)}'
    else:
        returned_percentage = f'-{int(percentage*100-100)}'

    return OutTables(found_header,
                     found_rows,
                     found_total_sum,
                     not_found_header,
                     not_found_rows,
                     not_found_total_sum,
                     initial_sum,
                     final_sum,
                     returned_percentage)