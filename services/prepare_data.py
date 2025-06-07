from typing import Any
from flask import jsonify, Response

from static.constants import NUMBERS, BAD_VALUES
from static.messages import ERROR_NO_TABLES


def get_target_table(raw_data: dict) -> tuple[Response, int] | list[Any]:

    raw_target_table = list()
    target_table_data = list()
    header = list()

    for items in raw_data:
        for item in items['table']:
            if item[0] in NUMBERS and item[1] not in BAD_VALUES:
                if len(header) == 0:
                    header.append(items['table'][0])
                raw_target_table.append(item)

    print(__name__ , header)
    print(__name__, raw_target_table)

    if len(raw_target_table) == 0:
        return jsonify({'error': ERROR_NO_TABLES}), 400

    for item in raw_target_table:
        if len(item) == len(header[0]):
            target_table_data.append(item)

    del raw_target_table

    return target_table_data