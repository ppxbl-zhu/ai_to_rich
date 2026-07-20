from __future__ import annotations

from datetime import date, datetime

from .tushare_client import TushareClient


def build_liquid_universe(client: TushareClient, trade_date: str, size: int = 100, minimum_listing_days: int = 120) -> list[dict]:
    basics = client.query("stock_basic", {"exchange": "", "list_status": "L"}, "ts_code,name,industry,list_date,list_status")
    st_codes = {row["ts_code"] for row in client.query("stock_st", {"trade_date": trade_date}, "ts_code")}
    quotes = client.query("daily", {"trade_date": trade_date}, "ts_code,amount,vol,close")
    quote_map = {row["ts_code"]: row for row in quotes}
    as_of = datetime.strptime(trade_date, "%Y%m%d").date()
    eligible = []
    for stock in basics:
        code = stock["ts_code"]
        name = str(stock.get("name") or "")
        quote = quote_map.get(code)
        listed = datetime.strptime(stock["list_date"], "%Y%m%d").date() if stock.get("list_date") else date.max
        if code in st_codes or "ST" in name.upper() or "退" in name or not quote:
            continue
        if (as_of - listed).days < minimum_listing_days or float(quote.get("amount") or 0) <= 0:
            continue
        eligible.append({"ts_code": code, "name": name, "industry": stock.get("industry") or "未分类", "amount": float(quote["amount"])})
    eligible.sort(key=lambda row: row["amount"], reverse=True)
    return eligible[:size] if size > 0 else eligible
