import json
import math
import re
from urllib.parse import quote

import requests

from services.base_parser import BaseParser
from static.constants import (BASE_PVZ,
                              EXIST_BASE_URL,
                              EXIST_CATALOG_LINK_PATTERN,
                              EXIST_CHECK_NUMBER,
                              EXIST_DATA_PATTERN,
                              EXIST_DEFAULT_MIN_QTY,
                              EXIST_HIDDEN_FIELDS,
                              EXIST_MINUTES_PER_DAY,
                              EXIST_PRICE_URL,
                              EXIST_QUERY_URL,
                              EXIST_SEARCH_URL,
                              EXIST_TIMEOUT,
                              EXIST_UNLIMITED_QTY)
from static.messages import ERROR_EXIST_UNAVAILABLE


class ExistParser(BaseParser):
    """Парсер exist.ru. Формат результата совпадает с EMEXParser.

    У exist.ru нет рейтинга поставщика на предложение: на странице цен есть
    только «Надёжность» позиции каталога (0..5), поэтому порог рейтинга из формы
    к exist.ru не применяется, а значение выводится в колонку «Рейтинг».
    Предложения сторонних магазинов («В других магазинах») не учитываются.
    """

    apply_rating_filter = False

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    QUERY_HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": EXIST_BASE_URL
    }

    def __init__(self, entry_params: dict, pvz: str = BASE_PVZ, brand: str = '', data: list = None):
        super().__init__(entry_params, pvz, brand, data)
        print(__name__, data)

    def prepare_session(self, session: requests.Session, proxies: dict) -> None:
        session.proxies.update(proxies)

    def search_data(self) -> list:

        result = super().search_data()

        # Пустой результат уточняем: возможно, источник вообще не отдал данные текущему IP
        if not result and not self.__source_available():
            return [ERROR_EXIST_UNAVAILABLE]

        return result

    def __source_available(self) -> bool:
        """exist.ru отдаёт цены не всем: страница открывается, но данных нет.

        Проверяем эталонным номером, который заведомо есть в каталогах.
        """

        session = requests.Session()
        self.prepare_session(session, self.proxies)

        try:
            available = bool(self.__catalog_ids(session, EXIST_CHECK_NUMBER))
        finally:
            session.close()

        print(__name__, 'источник доступен:', available)

        return available

    # --- обход одной позиции прайс-листа ---

    def fetch_offers(self, session: requests.Session, item: list) -> list:

        key_number = item[1]
        offers = list()
        parsed_products = set()
        parsed_offers = set()

        for catalog_id in self.__catalog_ids(session, key_number):

            page = self.__price_page(session, catalog_id)

            if page is None:
                continue

            products, query_context = page

            for product in products:
                product_id = product.get('ProductIdEnc') or ''

                if not product_id or product_id in parsed_products:
                    continue

                parsed_products.add(product_id)

                for raw_offer in self.__product_offers(session, product, query_context):
                    offer_id = raw_offer.get('InlineProductId')

                    if offer_id:
                        if offer_id in parsed_offers:
                            continue
                        parsed_offers.add(offer_id)

                    offer = self.__build_offer(key_number, product, raw_offer)

                    if offer is not None:
                        offers.append([offer])

        print(__name__, key_number, len(offers))

        return offers

    # --- страница поиска по номеру ---

    def __catalog_ids(self, session: requests.Session, key_number: str) -> list:

        url = f'{EXIST_SEARCH_URL}?pcode={quote(str(key_number), safe="")}'

        response = self.__request(session, 'get', url)

        if response is None:
            return []

        catalog_ids = re.findall(EXIST_CATALOG_LINK_PATTERN, response.text, re.IGNORECASE)

        if not catalog_ids:
            # Сайт мог сразу открыть страницу цен вместо выбора каталога
            product_id = self.__hidden_value(response.text, EXIST_HIDDEN_FIELDS['pid'])
            catalog_ids = [product_id] if product_id else []

        return list(dict.fromkeys(catalog_ids))

    # --- страница цен каталога ---

    def __price_page(self, session: requests.Session, catalog_id: str):

        url = f'{EXIST_PRICE_URL}?pid={catalog_id}'

        response = self.__request(session, 'get', url)

        if response is None:
            return None

        text = response.text
        marker = re.search(EXIST_DATA_PATTERN, text)

        if marker is None:
            return None

        try:
            products, _ = json.JSONDecoder().raw_decode(text[marker.end():].lstrip())
        except ValueError as e:
            print(__name__, 'не удалось разобрать данные страницы цен:', e)
            return None

        query_context = {key: self.__hidden_value(text, field) for key, field in EXIST_HIDDEN_FIELDS.items()}

        return products, query_context

    # --- предложения позиции ---

    def __product_offers(self, session: requests.Session, product: dict, query_context: dict) -> list:

        offers = list(product.get('AggregatedParts') or [])

        # На странице отдаются только самые дешёвые предложения позиции.
        # Если ни одно из них не проходит фильтры, запрашиваем полный список.
        if product.get('MoreOffers', 0) > 0 and not any(self.__offer_passes(product, offer) for offer in offers):
            more_offers = self.__more_offers(session, product, query_context)
            if more_offers:
                offers = more_offers

        # DirectOffers («В других магазинах») — предложения сторонних магазинов-партнёров,
        # а не самого exist.ru, поэтому в результат не попадают.
        return offers

    def __more_offers(self, session: requests.Session, product: dict, query_context: dict) -> list:

        if not query_context.get('pid') or not query_context.get('hash'):
            return []

        payload = {
            'ProductID': product.get('ProductIdEnc'),
            'OriginalProductID': query_context['pid'],
            'textValue': query_context['hash'],
            'srcId': query_context.get('src') or 'RawPartNumber'
        }

        response = self.__request(session, 'post', EXIST_QUERY_URL,
                                  headers={**self.QUERY_HEADERS,
                                           'Referer': f'{EXIST_PRICE_URL}?pid={product.get("ProductIdEnc")}'},
                                  json=payload)

        if response is None:
            return []

        try:
            data = response.json()
        except ValueError as e:
            print(__name__, 'не удалось разобрать список предложений:', e)
            return []

        if not isinstance(data, dict):
            return []

        raw_offers = data.get('d')

        if isinstance(raw_offers, str):
            raw_offers = json.loads(raw_offers) if raw_offers else []

        if not isinstance(raw_offers, list):
            return []

        return raw_offers

    # --- сборка предложения ---

    def __build_offer(self, key_number: str, product: dict, raw_offer: dict):

        price = raw_offer.get('price')

        if price in (None, ''):
            return None

        product_id = product.get('ProductIdEnc') or ''

        return {'key_number': key_number,
                'detail_num': str(product.get('PartNumber') or '').strip(),
                'detail_name': self.__clean_text(product.get('Description')),
                'delivery_time': self.__delivery_days(raw_offer.get('minutes')),
                'price': float(price),
                'min_qty': EXIST_DEFAULT_MIN_QTY,
                'max_qty': self.__max_qty(raw_offer),
                'make_name': str(product.get('CatalogName') or '').strip(),
                'link': f'{EXIST_PRICE_URL}?pid={product_id}'.replace(' ', '%20'),
                'rating': self.__rating(product)}

    def __offer_passes(self, product: dict, raw_offer: dict) -> bool:

        return self.passes_filters(self.__delivery_days(raw_offer.get('minutes')),
                                   self.__max_qty(raw_offer),
                                   self.__rating(product))

    # --- поля предложения ---

    @staticmethod
    def __delivery_days(minutes) -> int:

        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            return 0

        return int(math.ceil(max(minutes, 0) / EXIST_MINUTES_PER_DAY))

    @staticmethod
    def __max_qty(raw_offer: dict) -> int:
        """avail = 0 означает «Склад поставщика. Заказывайте в необходимом количестве»."""

        try:
            available = int(raw_offer.get('avail') or 0)
        except (TypeError, ValueError):
            available = 0

        return available if available > 0 else EXIST_UNLIMITED_QTY

    @staticmethod
    def __rating(product: dict) -> float:
        """«Надёжность» позиции по шкале 0..5, у exist.ru — строка с одним знаком."""

        try:
            return float(product.get('AbsoluteRatingString') or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def __clean_text(value) -> str:

        return re.sub(r'\s+', ' ', str(value or '')).strip()

    @staticmethod
    def __hidden_value(html: str, field_id: str) -> str:

        match = re.search(rf'id="{field_id}"[^>]*value="([^"]*)"', html)

        return match.group(1) if match else ''

    @staticmethod
    def __request(session: requests.Session, method: str, url: str, headers: dict = None, **kwargs):

        request_headers = {**ExistParser.HEADERS, **(headers or {})}

        try:
            response = getattr(session, method)(url, headers=request_headers, timeout=EXIST_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            print(__name__, f'ошибка запроса {url}: {e}')
            return None

        if response.status_code != 200:
            print(__name__, f'статус {response.status_code} для {url}')
            return None

        return response
