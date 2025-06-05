from models.entry_data_model import EntryParams


def get_params_dict(rating: float,
                    availability: int,
                    delivery_time: int,
                    data_source: str) -> EntryParams:
    return EntryParams(rating=rating,
                       availability=availability,
                       delivery_time=delivery_time,
                       data_source=data_source)
