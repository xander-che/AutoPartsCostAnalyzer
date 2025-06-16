from dataclasses import dataclass
from typing import List

@dataclass
class EntryParams:
    rating: float
    availability: int
    delivery_time: int
    data_source: str
    pvz_code: str
    strict_compliance: str
    proxy_ip: str
    proxy_port: str

    def params_to_dict(self):
        return {'params': [{'rating': self.rating,
                            'availability': self.availability,
                            'delivery_time': self.delivery_time,
                            'data_source': self.data_source,
                            'pvz_code': self.pvz_code,
                            'strict_compliance': self.strict_compliance,
                            'proxy_ip': self.proxy_ip,
                            'proxy_port': self.proxy_port}]
        }


@dataclass
class RawTables:
    page: int
    table: List[List[str]]

    def tables_to_dict(self):
        return {'tables': [{'page': self.page,
                            'table': self.table}]
        }


@dataclass
class ItemDict:

    @staticmethod
    def get_dict():
        return {
                'key_number': list(),
                'detail_num': list(),
                'is_original': list(),
                'detail_name': list(),
                'delivery_time': list(),
                'price': list(),
                'min_qty': list(),
                'max_qty': list(),
                'make_name': list(),
                'link': list(),
                'rating': list()
            }


@dataclass
class OutTables:
    found_header: list
    found_rows: list
    found_total_sum: int
    not_found_header: list
    not_found_rows: list
    not_found_total_sum: int
    initial_sum: int
    final_sum: int
    percentage: str

    def get_out_tables(self):
        return {
            'found': {
                'headers': self.found_header,
                'rows': self.found_rows,
                'total_sum': str(self.found_total_sum)
            },
            'not_found': {
                'headers': self.not_found_header,
                'rows': self.not_found_rows,
                'total_sum': str(self.not_found_total_sum)
            },
            'total_comparison': {
                'initial_sum': str(self.initial_sum),
                'final_sum': str(self.final_sum),
                'percentage': self.percentage
            }

        }