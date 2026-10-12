import json
import logging
import re
from urllib.parse import quote

import requests

from services.base_parser import BaseParser, SourceAccessError
from static.messages import ERROR_AUTOPITER_UNAVAILABLE


logger = logging.getLogger(__name__)


class AutopiterParser(BaseParser):
    """Поиск предложений Автопитера по артикулу из публичных страниц каталога."""

    requires_proxy = False
    source_name = 'autopiter.ru'
    source_error_message = ERROR_AUTOPITER_UNAVAILABLE
    BASE_URL = 'https://autopiter.ru'
    MAX_CATALOGS_PER_PART = 3
    MAX_OFFERS_PER_PART = 500
    HEADERS = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/124.0.0.0 Safari/537.36'),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.7',
    }

    def fetch_offers(self, session: requests.Session, item: list) -> list:
        key_number = str(item[1] or '').strip()
        search_url = f'{self.BASE_URL}/goods/{quote(key_number, safe="")}'
        search_page = self._load_page(session, search_url)
        state = self._read_state(search_page.text)
        catalogs = state.get('appraiseCatalogs', {}).get('items') or []

        normalized_number = self.normalize_part_number(key_number)
        catalogs = sorted(
            (catalog for catalog in catalogs
             if catalog.get('brandUrl') and
             (catalog.get('articleId') or catalog.get('uid'))),
            key=lambda catalog: (
                self.normalize_part_number(catalog.get('article')) != normalized_number,
                not bool(catalog.get('bestPrice')),
            ),
        )

        if not catalogs:
            logger.info('Автопитер: каталоги не найдены для %s', key_number)
            return []

        offers = []
        for catalog in catalogs[:self.MAX_CATALOGS_PER_PART]:
            article = str(catalog.get('article') or key_number).strip()
            brand_slug = quote(str(catalog['brandUrl']), safe='')
            article_id = quote(str(catalog.get('articleId') or catalog.get('uid')), safe='')
            product_url = (f'{self.BASE_URL}/goods/{quote(article, safe="")}/'
                           f'{brand_slug}/id{article_id}')

            try:
                product_state = self._read_state(self._load_page(session, product_url).text)
            except SourceAccessError:
                # Другая карточка артикула ещё может открываться без ограничений.
                logger.info('Автопитер: карточка каталога временно недоступна: %s', product_url)
                continue

            products = product_state.get('appraiseProduct', {}).get('items') or []
            for product in products:
                offer = self._normalize_offer(product, key_number, product_url)
                if offer is None or not self.passes_filters(
                        offer['delivery_time'], offer['max_qty'], offer['rating']):
                    continue

                if (self.entry_params.get('strict_compliance') == 'on' and
                        self.normalize_part_number(offer['detail_num']) != normalized_number):
                    continue

                offers.append([offer])

            if offers:
                break

        offers.sort(key=lambda wrapped: wrapped[0]['price'])
        logger.info('Автопитер: для %s найдено %s предложений', key_number, len(offers))
        return offers[:self.MAX_OFFERS_PER_PART]

    def _load_page(self, session: requests.Session, url: str) -> requests.Response:
        try:
            response = session.get(url, headers=self.HEADERS, timeout=30)
        except requests.RequestException as error:
            logger.warning('Ошибка запроса Автопитера %s: %s', url, error)
            raise

        if response.status_code == 407:
            raise requests.exceptions.ProxyError('прокси отклонил авторизацию')
        if response.status_code in {403, 429, 503}:
            raise SourceAccessError(f'Автопитер вернул HTTP {response.status_code}')
        response.raise_for_status()
        return response

    @staticmethod
    def _read_state(html: str) -> dict:
        marker = "window['__INITIAL_STATE__'] = "
        start = html.find(marker)
        if start < 0:
            if re.search(r'captcha|проверка безопасности|доступ ограничен', html, re.IGNORECASE):
                raise SourceAccessError('Автопитер запросил проверку безопасности')
            raise SourceAccessError('Автопитер не вернул данные каталога')

        start += len(marker)
        try:
            state, _ = json.JSONDecoder().raw_decode(html[start:])
        except (TypeError, ValueError) as error:
            raise SourceAccessError('Автопитер вернул неверный формат каталога') from error

        if not isinstance(state, dict):
            raise SourceAccessError('Автопитер вернул неверный формат каталога')
        return state

    @staticmethod
    def _number(value, default=0):
        try:
            return float(str(value or '').replace('\xa0', '').replace(' ', '').replace(',', '.'))
        except (TypeError, ValueError):
            return default

    @classmethod
    def _normalize_offer(cls, product: dict, key_number: str, product_url: str):
        price = cls._number(product.get('price')) or cls._number(product.get('priceNet'))
        detail_number = str(product.get('shortName') or product.get('article') or '').strip()
        if price <= 0 or not detail_number:
            return None

        raw_rating = cls._number(product.get('rating')) or cls._number(product.get('rank'))
        rating = raw_rating / 2 if raw_rating > 5 else raw_rating
        return {
            'key_number': key_number,
            'detail_num': detail_number,
            'detail_name': str(product.get('name') or product.get('shortName') or '').strip(),
            'delivery_time': max(0, int(cls._number(product.get('deliveryDays')))),
            'price': price,
            'min_qty': max(1, int(cls._number(product.get('minimumSaleSize'), 1))),
            'max_qty': max(0, int(cls._number(product.get('quantity')))),
            'make_name': str(product.get('catalogName') or product.get('brandName') or '').strip(),
            'link': product_url,
            'rating': rating,
        }
