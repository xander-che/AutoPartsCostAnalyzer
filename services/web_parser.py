import json
import logging
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from services.base_parser import BaseParser, SourceAccessError
from static.constants import BASE_PVZ, EMEX_BASE_URL, EMEX_TIMEOUT, TARGET_JSON_KEYS
from static.messages import ERROR_EMEX_UNAVAILABLE


logger = logging.getLogger(__name__)


class EMEXParser(BaseParser):
    """Парсер emex.ru с поддержкой страницы выбора производителя."""

    requires_proxy = False
    source_error_message = ERROR_EMEX_UNAVAILABLE

    HEADERS = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/124.0.0.0 Safari/537.36'),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.7',
        'Referer': 'https://emex.ru/'
    }

    def __init__(self, entry_params: dict, pvz: str = BASE_PVZ, brand: str = '', data: list = None):
        super().__init__(entry_params, pvz, brand, data)

    def fetch_offers(self, session: requests.Session, item: list) -> list:
        key_number = str(item[1]).strip()
        brand = str(self.brand or '').strip().replace('%20', ' ')

        # Сначала пробуем марку из PDF. Для оригинальных деталей это обычно
        # сразу открывает предложения.
        url = self.__product_url(key_number, brand) if brand else self.__search_url(key_number)
        response, details = self.__load_details(session, url)
        offers = self.__parse_data(details, key_number, response.url)

        if offers:
            return offers

        # Emex возвращает страницу выбора, если у артикула несколько производителей.
        maker = self.__choose_maker(details, brand)
        if maker is None:
            return []

        maker_path = maker.get('parsedUrl') or maker.get('url')
        if not maker_path:
            return []

        maker_url = f'{urljoin("https://emex.ru", maker_path).rstrip("/")}/{quote(str(self.pvz), safe="")}'
        response, details = self.__load_details(session, maker_url)
        return self.__parse_data(details, key_number, response.url)

    def __search_url(self, key_number: str) -> str:
        return f'{EMEX_BASE_URL}/{quote(key_number, safe="")}'

    def __product_url(self, key_number: str, brand: str) -> str:
        return (f'{EMEX_BASE_URL}/{quote(key_number, safe="")}/'
                f'{quote(brand, safe="")}/{quote(str(self.pvz), safe="")}')

    def __load_details(self, session: requests.Session, url: str):
        response = session.get(url, headers=self.HEADERS, timeout=EMEX_TIMEOUT)
        if response.status_code == 407:
            raise requests.exceptions.ProxyError('прокси отклонил авторизацию')
        if response.status_code in {403, 429, 503}:
            raise SourceAccessError(f'Emex вернул HTTP {response.status_code}')
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        script = soup.find(id='__NEXT_DATA__')

        if script is None:
            raise SourceAccessError('Emex не вернул данные товаров')

        raw_data = json.loads(script.string or script.get_text())
        initial_state = raw_data.get('props', {}).get('initialState', {})

        if isinstance(initial_state, str):
            initial_state = json.loads(initial_state)

        details = initial_state.get('details') if isinstance(initial_state, dict) else None
        if not isinstance(details, dict):
            raise SourceAccessError('Emex изменил формат страницы')

        return response, details

    @staticmethod
    def __choose_maker(details: dict, brand: str):
        makers = details.get('makes', {}).get('list', [])
        if not makers:
            return None

        normalized_brand = BaseParser.normalize_part_number(brand)
        if normalized_brand:
            for maker in makers:
                if BaseParser.normalize_part_number(maker.get('make')) == normalized_brand:
                    return maker

        # Без точного совпадения берём самый дешёвый товар без метки
        # "Только аналоги/замены": его страница даёт полный список предложений.
        preferred = [maker for maker in makers if not maker.get('tags')]
        candidates = preferred or makers

        def price(maker):
            return float((maker.get('bestPrice') or {}).get('value') or float('inf'))

        return min(candidates, key=price)

    @staticmethod
    def __parse_data(details: dict, key_number: str, page_url: str) -> list:
        result_table = []

        for category in TARGET_JSON_KEYS:
            for product in details.get(category) or []:
                for raw_offer in product.get('offers') or []:
                    offer_data = raw_offer.get('data') or {}
                    if offer_data.get('notAvailable', False):
                        continue

                    detail_num = str(offer_data.get('detailNum') or product.get('detailNum') or '').strip()
                    if not detail_num:
                        continue

                    delivery = offer_data.get('delivery') or raw_offer.get('delivery') or {}
                    display_price = offer_data.get('displayPrice') or raw_offer.get('displayPrice') or {}
                    lot_quantity = offer_data.get('lotQuantity') or raw_offer.get('lotQuantity') or {}
                    max_quantity = offer_data.get('maxQuantity') or {}

                    if not isinstance(lot_quantity, dict):
                        lot_quantity = {'value': lot_quantity}
                    if not isinstance(max_quantity, dict):
                        max_quantity = {'value': max_quantity}

                    offer = {
                        'key_number': key_number,
                        'detail_num': detail_num,
                        'detail_name': str(offer_data.get('detailName') or product.get('name') or '').strip(),
                        'delivery_time': int(delivery.get('value') or 0),
                        'price': float(display_price.get('value') or 0),
                        'min_qty': int(lot_quantity.get('value') or 1),
                        'max_qty': int(max_quantity.get('value') or raw_offer.get('quantity') or 0),
                        'make_name': str(offer_data.get('makeName') or product.get('make') or '').strip(),
                        'link': page_url,
                        'rating': float(raw_offer.get('rating') or 0)
                    }

                    if offer['price'] > 0:
                        result_table.append([offer])

        return result_table
