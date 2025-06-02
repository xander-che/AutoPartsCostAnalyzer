from dataclasses import dataclass
from typing import List

@dataclass
class EntryParams:
    rating: float
    availability: int
    delivery_time: int
    data_source: str

    def params_to_dict(self):
        return {'params': [{'rating': self.rating,
                            'availability': self.availability,
                            'delivery_time': self.delivery_time,
                            'data_source': self.data_source}]
        }


@dataclass
class RawTables:
    page: int
    table: List[List[str]]

    def tables_to_dict(self):
        return {'tables': [{'page': self.page,
                            'table': self.table}]
        }