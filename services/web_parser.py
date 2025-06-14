import json
from time import sleep
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import jsonify
from models.data_models import ItemDict
from static.constants import EMEX_BASE_URL, BASE_PVZ, TARGET_JSON_KEYS


class EMEXParser:
    def __init__(self, entry_params: dict, pvz: str, brand: str, data: list):
        self.entry_params = entry_params
        self.pvz = pvz
        self.brand = brand
        self.data = data


    def search_data(self) -> list:

        result_table = list()

        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://emex.ru/",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://emex.ru"
        }

        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )

        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=retries))

        try:
            for item in self.data:
                url = f'{EMEX_BASE_URL}/{item[1]}/{self.brand}/{self.pvz}'

                response = session.get(url, headers=header, timeout=10)

                soup = BeautifulSoup(response.text, 'html.parser')

                raw_data = json.loads(soup.find(id='__NEXT_DATA__').prettify()[51:-10])
                result_table.append(self.__parse_data(raw_data, item[1]))
                sleep(2)

        except Exception as e:
            print(f"Ошибка соединения: {e}")

        session.close()

        return self.__analyzing(self.entry_params, result_table)


    @staticmethod
    def __parse_data(raw_data: dict, key_number: str) -> list:

        result_table = list()
        raw_json = jsonify(raw_data).get_json()['props']['initialState']['details']

        for key1, value1 in raw_json.items():
            if key1 in TARGET_JSON_KEYS:
                for item in value1:
                    for key2, value2 in item.items():
                        if key2 == 'offers':
                            for i in value2:
                                for key3, value3 in i.items():
                                    if key3 == 'data':
                                        if not value3['notAvailable']:
                                            detail_num = value3['detailNum']
                                            detail_name = value3['detailName']
                                            delivery_time = value3['delivery']['value']
                                            price = value3['displayPrice']['value']
                                            min_qty = value3['lotQuantity']['value']
                                            max_qty = value3['maxQuantity']['value']
                                            make_name = value3['makeName']
                                            item = {'key_number': key_number,
                                                    'detail_num': detail_num,
                                                    'detail_name': detail_name,
                                                    'delivery_time': int(delivery_time),
                                                    'price': float(price),
                                                    'min_qty': min_qty,
                                                    'max_qty': int(max_qty),
                                                    'make_name': make_name,
                                                    'link': f'{EMEX_BASE_URL}/{detail_num}/{make_name}/{BASE_PVZ}'.replace(' ', '%20')}
                                    if key3 == 'rating' and len(item) > 0:
                                        item['rating'] = value3
                                    if len(item) == 10:
                                        result_table.append([item])

        return result_table


    @staticmethod
    def __analyzing(entry_params: dict, search_table: list) -> list:

        result = list()
        # pd.set_option('display.max_rows', 500)
        # pd.set_option('display.max_columns', 500)
        # pd.set_option('display.width', 1000)

        for items in search_table:
            item_dict = ItemDict.get_dict()
            for item in items:
                item_dict['key_number'].append(item[0]['key_number'])
                item_dict['detail_num'].append(item[0]['detail_num'])
                item_dict['detail_name'].append(item[0]['detail_name'])
                item_dict['delivery_time'].append(item[0]['delivery_time'])
                item_dict['price'].append(item[0]['price'])
                item_dict['min_qty'].append(item[0]['min_qty'])
                item_dict['max_qty'].append(item[0]['max_qty'])
                item_dict['make_name'].append(item[0]['make_name'])
                item_dict['link'].append(item[0]['link'])
                item_dict['rating'].append(item[0]['rating'])

            df = pd.DataFrame(item_dict).sort_values(by='price')
            print(__name__, entry_params)

            for row in df.itertuples():
                if row.delivery_time <= entry_params['delivery_time'] and \
                    row.max_qty >= entry_params['availability'] and \
                        row.rating >= entry_params['rating']:
                    if entry_params['strict_compliance'] == 'on':
                            if row.key_number == row.detail_num:
                                result.append(row)
                                break
                    else:
                        result.append(row)
                        break

        return result




