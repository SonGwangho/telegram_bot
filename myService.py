import requests

def fetch_domestic(code: str) -> dict:
    url = f'https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}'
    res = requests.get(url, timeout=10)
    res.raise_for_status()

    json_data = res.json()
    data = json_data["result"]["areas"][0]["datas"][0]

    rate = float(data["cr"])

    sign = 1 if data["rf"] == "2" else -1 if data["rf"] == "5" else 0
    return {
        "isKRW": True,
        "name": data["nm"],
        "value": float(str(data["nv"]).replace(",", "")),
        "rate": rate,
        "sign": "+" if sign > 0 else "-" if sign < 0 else "",
        "emoji": "🔺" if sign > 0 else "🔻" if sign < 0 else "-",
    }

def fetch_world(code: str, kind: str) -> dict:
    url = f"https://polling.finance.naver.com/api/realtime/worldstock/{kind}/{code}"
    res = requests.get(url, timeout=10)
    res.raise_for_status()

    json_data = res.json()
    data = json_data["datas"][0]
    # print(data)

    status = data["compareToPreviousPrice"]["name"]
    rate = float(data["fluctuationsRatioRaw"])
    rate = rate if rate > 0 else rate * -1
    name = "indexName" if kind == "index" else "stockName"

    return {
        "isKRW": False,
        "name": data[f"{name}"],
        "value": float(data["closePriceRaw"]),
        "rate": rate,
        "sign": "+" if status == "RISING" else "-" if status == "FALLING" else "",
        "emoji": "🔺" if status == "RISING" else "🔻" if status == "FALLING" else "-",
    }
