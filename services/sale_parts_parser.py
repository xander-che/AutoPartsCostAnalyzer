from services.base_parser import BaseParser, SourceAccessError
from static.messages import ERROR_SALE_PARTS_UNAVAILABLE


class SalePartsParser(BaseParser):
    """Заготовка до подключения разрешённого API Sale-Parts."""

    requires_proxy = False
    source_name = 'sale-parts.ru'
    source_error_message = ERROR_SALE_PARTS_UNAVAILABLE

    def fetch_offers(self, session, item):
        # Публичный robots.txt Sale-Parts запрещает автоматические запросы к
        # /price_items/search и /products/price.json. Не отправляем такие запросы
        # без официального API или отдельного разрешённого интерфейса.
        raise SourceAccessError(ERROR_SALE_PARTS_UNAVAILABLE)
