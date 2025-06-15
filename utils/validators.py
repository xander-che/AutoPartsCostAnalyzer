from typing import Any

import requests
from static.constants import ALLOWED_EXTENSIONS


def allowed_file_type(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_entry_qty(entry_key_qty_list: list, key: str) -> int:
    entry_qty = 0
    for item in entry_key_qty_list:
        if item[0] == key:
            entry_qty = item[1]
            break

    if not entry_qty:
        entry_qty = 1

    return entry_qty

def get_my_ip() -> str:
    my_ip = ''
    try:
        response = requests.get("https://api.ipify.org?format=json", timeout=3)
        my_ip = response.json()["ip"]
        print("Ваш IP:", response.json()["ip"])
        response.close()
    except Exception as e:
        print("Ошибка при определении собственного IP:", e)

    return my_ip


def get_proxy_ip(proxies: dict) -> tuple[str | Any, dict[str, str]]:

    proxy_ip = ''
    try:
        response = requests.get(
            "https://api.ipify.org?format=json",
            proxies=proxies,
            timeout=10
        )
        proxy_ip = response.json()["ip"]
        print("Ваш IP через прокси:", proxy_ip, ' статус ', response.status_code)
        if len(proxy_ip) > 0:
            response.close()
    except Exception as e:
        print("Ошибка функционирования стороннего прокси:", e)

    return proxy_ip
