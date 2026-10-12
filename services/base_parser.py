import logging
import os
import re
from time import sleep
from types import SimpleNamespace
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from static.constants import BASE_PVZ, NO, YES
from static.messages import ERROR_NOT_PROXY_ENABLED, NO_DATA_FOUND


logger = logging.getLogger(__name__)


class SourceAccessError(RuntimeError):
    """Источник отклонил автоматический запрос или изменил формат ответа."""


class BaseParser:
    """Общая логика парсеров: прокси, обход позиций и отбор предложений."""

    apply_rating_filter = True
    requires_proxy = True
    source_error_message = NO_DATA_FOUND

    def __init__(self, entry_params: dict, pvz: str = BASE_PVZ, brand: str = '', data: list = None):
        self.entry_params = entry_params
        self.pvz = entry_params.get('pvz_code') or pvz
        self.brand = brand
        self.data = data if data is not None else []
        self.proxies = {}

    def build_proxies(self) -> dict:
        proxy_url = self.build_proxy_url(self.entry_params)
        return {'http': proxy_url, 'https': proxy_url} if proxy_url else {}

    @staticmethod
    def build_proxy_url(entry_params: dict) -> str:
        """Принимает host + port или полный URL в поле адреса."""

        entered_address = str(entry_params.get('proxy_ip') or '').strip()
        raw_address = entered_address or os.getenv('PROXY_URL', '').strip()

        if not raw_address:
            return ''

        scheme = str(entry_params.get('proxy_scheme') or 'http').lower()
        if scheme not in {'http', 'https'}:
            raise ValueError('протокол прокси должен быть http или https')

        if '://' not in raw_address:
            raw_address = f'{scheme}://{raw_address}'

        parsed = urlsplit(raw_address)
        hostname = parsed.hostname

        if not hostname:
            raise ValueError('не указан адрес прокси')

        try:
            parsed_port = parsed.port
        except ValueError as error:
            raise ValueError('указан неверный порт прокси') from error

        port = parsed_port or str(entry_params.get('proxy_port') or '').strip()
        if not port or not str(port).isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError('не указан или неверно указан порт прокси')

        parsed_username = unquote(parsed.username or '')
        parsed_password = unquote(parsed.password or '')
        username = str(entry_params.get('proxy_user') or parsed_username).strip()
        password = str(entry_params.get('proxy_password') or parsed_password)

        # Переменные окружения относятся только к серверному PROXY_URL.
        if not entered_address:
            username = username or os.getenv('PROXY_USER', '')
            password = password or os.getenv('PROXY_PASSWORD', '')

        auth = ''
        if username:
            auth = quote(username, safe='')
            if password:
                auth += f':{quote(password, safe="")}'
            auth += '@'

        host = f'[{hostname}]' if ':' in hostname else hostname
        return urlunsplit((parsed.scheme, f'{auth}{host}:{port}', '', '', ''))

    def prepare_session(self, session: requests.Session, proxies: dict) -> None:
        session.trust_env = False
        session.proxies.update(proxies)

        retries = Retry(total=2,
                        connect=2,
                        read=1,
                        backoff_factor=0.35,
                        status_forcelist=(429, 500, 502, 503, 504),
                        allowed_methods=frozenset({'GET'}))
        adapter = HTTPAdapter(max_retries=retries, pool_connections=4, pool_maxsize=4)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

    def search_data(self) -> list:
        try:
            self.proxies = self.build_proxies()
        except ValueError as error:
            logger.warning('Неверные параметры прокси: %s', error)
            return [ERROR_NOT_PROXY_ENABLED]

        if not self.proxies and self.requires_proxy:
            return [ERROR_NOT_PROXY_ENABLED]

        session = requests.Session()
        self.prepare_session(session, self.proxies)
        result_table = []
        failed_requests = 0
        delay = max(float(os.getenv('PARSER_REQUEST_DELAY', '0.2')), 0)

        try:
            for index, item in enumerate(self.data):
                try:
                    result_table.append(self.fetch_offers(session, item))
                except (requests.exceptions.ConnectionError,
                        requests.exceptions.SSLError) as error:
                    if self.proxies:
                        logger.warning('Ошибка прокси: %s', error)
                        return [ERROR_NOT_PROXY_ENABLED]

                    logger.warning('Ошибка соединения с источником: %s', error)
                    return [self.source_error_message]
                except SourceAccessError as error:
                    logger.warning('Источник недоступен: %s', error)
                    return [self.source_error_message]
                except (requests.RequestException, KeyError, ValueError, TypeError, AttributeError) as error:
                    failed_requests += 1
                    result_table.append([])
                    logger.warning('Не удалось получить позицию %s: %s', item[1], error)

                if delay and index + 1 < len(self.data):
                    sleep(delay)
        finally:
            session.close()

        if failed_requests == len(self.data) and self.data:
            return [self.source_error_message]

        return self.analyze_offers(result_table)

    def fetch_offers(self, session: requests.Session, item: list) -> list:
        raise NotImplementedError

    def passes_filters(self, delivery_time: float, max_qty: int, rating: float) -> bool:
        if delivery_time > self.entry_params['delivery_time']:
            return False
        if max_qty < self.entry_params['availability']:
            return False
        if self.apply_rating_filter and rating < self.entry_params['rating']:
            return False
        return True

    @staticmethod
    def normalize_part_number(value) -> str:
        return re.sub(r'[^0-9A-ZА-Я]', '', str(value or '').upper())

    def analyze_offers(self, search_table: list) -> list:
        result = []

        for items in search_table:
            offers = [wrapped[0] for wrapped in items if wrapped and isinstance(wrapped[0], dict)]

            for offer in sorted(offers, key=lambda value: float(value.get('price') or 0)):
                if not self.passes_filters(float(offer.get('delivery_time') or 0),
                                           int(offer.get('max_qty') or 0),
                                           float(offer.get('rating') or 0)):
                    continue

                is_original = (self.normalize_part_number(offer.get('key_number')) ==
                               self.normalize_part_number(offer.get('detail_num')))

                if self.entry_params['strict_compliance'] == 'on' and not is_original:
                    continue

                selected = dict(offer)
                selected['is_original'] = YES if is_original else NO
                result.append(SimpleNamespace(**selected))
                break

        return result
