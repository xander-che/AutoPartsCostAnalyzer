import random
from time import sleep

import pandas as pd
import requests

from models.data_models import ItemDict
from static.constants import BASE_PVZ, NO, PROXY_PASS, PROXY_USER, YES
from static.messages import ERROR_NOT_PROXY_ENABLED
from utils.validators import get_my_ip, get_proxy_ip


class BaseParser:
    """Общая логика парсеров источников данных: прокси, обход позиций, отбор предложений."""

    # У exist.ru рейтинг («Надёжность») считается по другой шкале,
    # поэтому порог рейтинга из формы к нему не применяется.
    apply_rating_filter = True

    def __init__(self, entry_params: dict, pvz: str = BASE_PVZ, brand: str = '', data: list = None):
        self.entry_params = entry_params
        self.pvz = pvz
        self.brand = brand
        self.data = data if data is not None else []
        self.proxies = {}

    # --- прокси ---

    def build_proxies(self) -> dict:
        proxy_ip = self.entry_params['proxy_ip']
        proxy_port = self.entry_params['proxy_port']

        proxies = {
            'http': f'http://{PROXY_USER}:{PROXY_PASS}@{proxy_ip}:{proxy_port}',
            'https': f'http://{PROXY_USER}:{PROXY_PASS}@{proxy_ip}:{proxy_port}'
        }
        print(__name__, proxies)

        return proxies

    @staticmethod
    def proxy_is_available(proxies: dict) -> bool:
        my_ip = get_my_ip()
        proxy_ip = get_proxy_ip(proxies)

        return len(my_ip) > 0 and len(proxy_ip) > 0 and my_ip != proxy_ip

    def prepare_session(self, session: requests.Session, proxies: dict) -> None:
        """Настройка сессии перед обходом позиций (переопределяется в парсерах)."""

    # --- обход позиций ---

    def search_data(self) -> list:

        result_table = list()

        self.proxies = self.build_proxies()

        if not self.proxy_is_available(self.proxies):
            result_table.append(ERROR_NOT_PROXY_ENABLED)
            return result_table

        session = requests.Session()
        self.prepare_session(session, self.proxies)

        try:
            for item in self.data:
                result_table.append(self.fetch_offers(session, item))
                sleep(random.choice([1, 2, 3]))

        except Exception as e:
            print(f"Ошибка соединения: {e}")

        finally:
            session.close()

        return self.analyze_offers(result_table)

    def fetch_offers(self, session: requests.Session, item: list) -> list:
        """Возвращает список предложений позиции в виде [[{...}], [{...}], ...]."""
        raise NotImplementedError

    # --- отбор предложений ---

    def passes_filters(self, delivery_time: float, max_qty: int, rating: float) -> bool:

        if delivery_time > self.entry_params['delivery_time']:
            return False

        if max_qty < self.entry_params['availability']:
            return False

        if self.apply_rating_filter and rating < self.entry_params['rating']:
            return False

        return True

    def analyze_offers(self, search_table: list) -> list:

        result = list()

        for items in search_table:
            item_dict = ItemDict.get_dict()
            for item in items:
                offer = item[0]
                item_dict['key_number'].append(offer['key_number'])
                item_dict['detail_num'].append(offer['detail_num'])
                if offer['key_number'] == offer['detail_num']:
                    item_dict['is_original'].append(YES)
                else:
                    item_dict['is_original'].append(NO)
                item_dict['detail_name'].append(offer['detail_name'])
                item_dict['delivery_time'].append(offer['delivery_time'])
                item_dict['price'].append(offer['price'])
                item_dict['min_qty'].append(offer['min_qty'])
                item_dict['max_qty'].append(offer['max_qty'])
                item_dict['make_name'].append(offer['make_name'])
                item_dict['link'].append(offer['link'])
                item_dict['rating'].append(offer.get('rating', 0))

            df = pd.DataFrame(item_dict).sort_values(by='price')

            for row in df.itertuples():
                if not self.passes_filters(row.delivery_time, row.max_qty, row.rating):
                    continue

                if self.entry_params['strict_compliance'] == 'on':
                    if row.key_number == row.detail_num:
                        result.append(row)
                        break
                else:
                    result.append(row)
                    break

        return result
