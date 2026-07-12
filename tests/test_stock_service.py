from __future__ import annotations

import unittest
from unittest.mock import patch

import myService


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeSession:
    def __init__(self, payload: object) -> None:
        self.response = FakeResponse(payload)
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def make_quote(target: myService.StockTarget) -> myService.StockQuote:
    return {
        "code": target.code,
        "kind": target.kind,
        "isKRW": target.kind == "domestic",
        "name": target.code,
        "value": 100.0,
        "rate": 1.0,
        "sign": "+",
        "emoji": "🔺",
    }


class StockServiceTests(unittest.TestCase):
    def test_fetch_domestic_parses_and_normalizes_falling_quote(self) -> None:
        session = FakeSession(
            {
                "result": {
                    "areas": [
                        {
                            "datas": [
                                {
                                    "nm": "삼성전자",
                                    "nv": "74,200",
                                    "cr": "-1.25",
                                    "rf": "5",
                                }
                            ]
                        }
                    ]
                }
            }
        )

        quote = myService.fetch_domestic("005930", session=session)

        self.assertEqual(quote["name"], "삼성전자")
        self.assertEqual(quote["value"], 74_200.0)
        self.assertEqual(quote["rate"], 1.25)
        self.assertEqual(quote["sign"], "-")
        self.assertEqual(quote["emoji"], "🔻")
        self.assertEqual(
            session.calls[0]["params"],
            {"query": "SERVICE_ITEM:005930"},
        )
        self.assertEqual(session.calls[0]["timeout"], myService.REQUEST_TIMEOUT)

    def test_fetch_world_parses_index_quote(self) -> None:
        session = FakeSession(
            {
                "datas": [
                    {
                        "indexName": "S&P 500",
                        "closePriceRaw": "6,250.50",
                        "fluctuationsRatioRaw": "0.75",
                        "compareToPreviousPrice": {"name": "RISING"},
                    }
                ]
            }
        )

        quote = myService.fetch_world(".INX", "index", session=session)

        self.assertEqual(quote["name"], "S&P 500")
        self.assertEqual(quote["value"], 6_250.5)
        self.assertEqual(quote["sign"], "+")
        self.assertIn("/index/.INX", str(session.calls[0]["url"]))

    def test_fetch_usd_krw_parses_comma_separated_value(self) -> None:
        session = FakeSession(
            {
                "country": [
                    {"value": "1"},
                    {"value": "1,382.40"},
                ]
            }
        )

        self.assertEqual(myService.fetch_usd_krw(session=session), 1_382.4)

    def test_malformed_response_raises_stock_fetch_error(self) -> None:
        session = FakeSession({"result": {"areas": []}})

        with self.assertRaises(myService.StockFetchError):
            myService.fetch_domestic("005930", session=session)

    def test_fetch_quotes_keeps_input_order_and_collects_failures(self) -> None:
        targets = (
            myService.StockTarget("first", "domestic"),
            myService.StockTarget("broken", "stock"),
            myService.StockTarget("third", "etf"),
        )

        def fake_fetch(target: myService.StockTarget) -> myService.StockQuote:
            if target.code == "broken":
                raise myService.StockFetchError("test failure")
            return make_quote(target)

        with patch.object(myService, "_fetch_target", side_effect=fake_fetch):
            quotes, failures = myService.fetch_quotes(targets, max_workers=3)

        self.assertEqual([quote["code"] for quote in quotes], ["first", "third"])
        self.assertEqual([failure.target.code for failure in failures], ["broken"])
        self.assertEqual(failures[0].reason, "test failure")

    def test_invalid_world_kind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            myService.fetch_world("BTC", "crypto")


if __name__ == "__main__":
    unittest.main()
