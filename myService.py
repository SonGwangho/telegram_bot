import requests

def fetch_domestic(code: str) -> dict:
    url = f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}'
    res = requests.get(url, timeout=10)
    res.raise_for_status()

    json_data = res.json()
    data = json_data["result"]["areas"][0]["datas"][0]

    rate = float(data["cr"])
    return {
        "name": data["nm"],
        "value": float(str(data["nv"]).replace(",", "")),
        "rate": rate,
        "sign": "+" if rate > 0 else "-" if rate < 0 else "",
        "emoji": "🔺" if rate > 0 else "🔻" if rate < 0 else "➖",
    }

def fetch_world_index(code: str) -> dict:
    url = f"https://polling.finance.naver.com/api/realtime/worldstock/index/{code}"
    res = requests.get(url, timeout=10)
    res.raise_for_status()

    json_data = res.json()
    data = json_data["datas"][0]

    status = data["compareToPreviousPrice"]["name"]
    rate = float(data["fluctuationsRatioRaw"])

    return {
        "name": data["indexName"],
        "value": float(data["closePriceRaw"]),
        "rate": rate,
        "sign": "+" if status == "RISING" else "-" if status == "FALLING" else "",
        "emoji": "🔺" if status == "RISING" else "🔻" if status == "FALLING" else "➖",
    }

def fetch_world_stock(code: str) -> dict:
    url = f"https://polling.finance.naver.com/api/realtime/worldstock/stock/{code}"
    res = requests.get(url, timeout=10)
    res.raise_for_status()

    json_data = res.json()
    data = json_data["datas"][0]

    status = data["compareToPreviousPrice"]["name"]
    rate = float(data["fluctuationsRatioRaw"])

    return {
        "name": data["stockName"],
        "value": float(data["closePriceRaw"]),
        "rate": rate,
        "sign": "+" if status == "RISING" else "-" if status == "FALLING" else "",
        "emoji": "🔺" if status == "RISING" else "🔻" if status == "FALLING" else "➖",
    }
