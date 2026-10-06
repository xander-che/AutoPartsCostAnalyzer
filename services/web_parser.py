import json

import requests
from bs4 import BeautifulSoup

from services.base_parser import BaseParser
from static.constants import BASE_PVZ, EMEX_BASE_URL, TARGET_JSON_KEYS


class EMEXParser(BaseParser):
    """Парсер emex.ru."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://emex.ru/",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://emex.ru"
    }

    def __init__(self, entry_params: dict, pvz: str = BASE_PVZ, brand: str = '', data: list = None):
        super().__init__(entry_params, pvz, brand, data)
        print(__name__, data)

    def fetch_offers(self, session: requests.Session, item: list) -> list:

        url = f'{EMEX_BASE_URL}/{item[1]}/{self.brand}/{self.pvz}'

        response = session.get(url, headers=self.HEADERS, proxies=self.proxies, timeout=10)

        soup = BeautifulSoup(response.text, 'html.parser')

        raw_data = json.loads(soup.find(id='__NEXT_DATA__').prettify()[51:-10])

        return self.__parse_data(raw_data, item[1])

    @staticmethod
    def __initial_state(raw_data: dict) -> dict:
        """emex отдаёт initialState и объектом, и JSON-строкой — поддерживаем оба варианта."""

        initial_state = raw_data['props']['initialState']

        if isinstance(initial_state, str):
            initial_state = json.loads(initial_state)

        return initial_state

    @staticmethod
    def __parse_data(raw_data: dict, key_number: str) -> list:

        result_table = list()
        raw_json = EMEXParser.__initial_state(raw_data)['details']

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
                                                    'link': f'{EMEX_BASE_URL}/{detail_num}/{make_name}/{BASE_PVZ}'.replace(
                                                        ' ', '%20')}
                                    if key3 == 'rating' and len(item) > 0:
                                        item['rating'] = value3
                                    if len(item) == 10:
                                        result_table.append([item])

        return result_table
