from datetime import datetime, timedelta
import requests

class MyUtils:

    @staticmethod
    def _get_datetime(date_str=None, fmt="%Y-%m-%d"):
        """
        내부 공용 메서드
        - date_str 없으면 오늘
        - 있으면 문자열 → datetime 변환
        """
        if date_str:
            return datetime.strptime(date_str, fmt)
        return datetime.now()

    @staticmethod
    def getToday(fmt="yyyy-mm-dd"):
        now = datetime.now()

        format_map = {
            "yyyy-mm-dd": "%Y-%m-%d",
            "yyyymmdd": "%Y%m%d",
            "yyyy.mm.dd": "%Y.%m.%d",
            "yyyy/mm/dd": "%Y/%m/%d",
            "hh:mm:ss": "%H:%M:%S",
            "full": "%Y-%m-%d %H:%M:%S"
        }

        if fmt in format_map:
            return now.strftime(format_map[fmt])

        return now.strftime(fmt)
    
    @staticmethod
    def getYesterday(fmt="yyyy-mm-dd"):
        yesterday = datetime.now() - timedelta(days=1)

        format_map = {
            "yyyy-mm-dd": "%Y-%m-%d",
            "yyyymmdd": "%Y%m%d",
            "yyyy.mm.dd": "%Y.%m.%d",
            "yyyy/mm/dd": "%Y/%m/%d",
            "hh:mm:ss": "%H:%M:%S",
            "full": "%Y-%m-%d %H:%M:%S"
        }

        if fmt in format_map:
            return yesterday.strftime(format_map[fmt])

        return yesterday.strftime(fmt)

    @staticmethod
    def getYear(date_str=None, fmt="%Y-%m-%d"):
        dt = MyUtils._get_datetime(date_str, fmt)
        return dt.year

    @staticmethod
    def getMonth(date_str=None, fmt="%Y-%m-%d"):
        dt = MyUtils._get_datetime(date_str, fmt)
        return dt.month

    @staticmethod
    def getDay(date_str=None, fmt="%Y-%m-%d"):
        dt = MyUtils._get_datetime(date_str, fmt)
        return dt.day
    
    @staticmethod
    def getUSD():
        url = f'https://m.search.naver.com/p/csearch/content/qapirender.nhn?key=calculator&pkid=141&q=%ED%99%98%EC%9C%A8&where=m&u1=keb&u6=standardUnit&u7=0&u3=USD&u4=KRW&u8=down&u2=1'
        res = requests.get(url, timeout=10)
        res.raise_for_status()

        json = res.json()
        usd = json["country"][1]["value"]
        return float(usd.replace(",", ""))