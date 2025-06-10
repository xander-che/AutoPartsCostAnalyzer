from bs4 import BeautifulSoup
import requests
from static.constants import EMEX_BASE_URL


class EMEXParser:
    def __init__(self, pvz: str, brand: str, data: list):
        self.pvz = pvz
        self.brand = brand
        self.data = data

    def search_data(self):
        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://emex.ru/",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://emex.ru"
        }

        session = requests.Session()

        url = f'{EMEX_BASE_URL}/{self.data[0][1]}/{self.brand}/{self.pvz}'
        response = session.get(url, headers=header)
        soup = BeautifulSoup(response.text, 'html.parser')

        return soup.prettify()