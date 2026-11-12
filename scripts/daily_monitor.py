"""Daily end-of-day STOCK-RADAR monitor. Not trading advice."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

WATCHLIST = ["NFLX","SE","NKE","AEVA","KULR","OKLO","FIG","RIVN","BIDU","ASTS","AAOI","LULU","SOFI","UBER","SYF","CROX","PYPL","DECK"]
OUT = Path("data")
OUT.mkdir(exist_ok=True)
LATEST = OUT / "latest.json"
PREVIOUS = {}
if LATEST.exists():
    try:
        PREVIOUS = json.loads(LATEST.read_text(encoding="utf-8")).get("stocks", {})
    except (ValueError, OSError):
        pass

def number(value):
    try:
        v = float(value)
        return round(v, 4) if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None

def analyze(symbol):
    hist = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True)
    if hist.empty or len(hist) < 21:
        raise ValueError("Fewer than 21 daily candles")
    hist = hist.dropna(subset=["Close", "Volume"])
    close = hist["Close"].astype(float)
    vol = hist["Volume"].astype(float)
    last = float(close.iloc[-1])
    prior = float(close.iloc[-2])
    avg_vol = float(vol.iloc[-21:-1].mean())
    last_vol = float(vol.iloc[-1])
    change = 100 * (last / prior - 1) if prior else None
    relative_volume = last_vol / avg_vol if avg_vol > 0 else None
    ma20 = float(close.tail(20).mean())
    ma50 = float(close.tail(50).mean()) if len(close) >= 50 else None
    asof = str(hist.index[-1].date())
    alerts = []
    if change is not None and abs(change) >= 5:
        alerts.append({"type": "price_move", "message": f"Variação diária {change:+.1f}%"})
    if relative_volume is not None and relative_volume >= 2:
        alerts.append({"type": "unusual_volume", "message": f"Volume {relative_volume:.1f}× média 20 sessões"})
    prev = PREVIOUS.get(symbol, {})
    # Prevent re-alerting the same candle on weekends and holidays.
    is_new = prev.get("asof") != asof
    if ma50 is not None and is_new and len(close) >= 51:
        yesterday_ma50 = float(close.iloc[-51:-1].mean())
        yesterday_close = float(close.iloc[-2])
        if (yesterday_close - yesterday_ma50) * (last - ma50) < 0:
            direction = "acima" if last > ma50 else "abaixo"
            alerts.append({"type": "ma50_cross", "message": f"Cruzou para {direction} da média móvel de 50 sessões"})
    return {
        "asof": asof, "currency": "USD (verificar moeda da bolsa)",
        "close": number(last), "change_pct": number(change),
        "volume": int(last_vol), "relative_volume_20d": number(relative_volume),
        "ma20": number(ma20), "ma50": number(ma50),
        "alerts": alerts if is_new else [],
        "data_source": "Yahoo Finance / yfinance; daily close; may be delayed or revised",
    }

stocks = {}
errors = {}
for symbol in WATCHLIST:
    try:
        stocks[symbol] = analyze(symbol)
        print(f"OK {symbol}: {stocks[symbol]['asof']}")
    except Exception as exc:
        errors[symbol] = str(exc)[:250]
        print(f"ERROR {symbol}: {exc}")

if not stocks:
    raise SystemExit("No usable market data; refusing to replace prior snapshot.")

payload = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "stocks": stocks,
    "errors": errors,
    "method": "End-of-day monitoring, not realtime, not an investment recommendation.",
}
LATEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
lines = [
    "# STOCK-RADAR — Monitorização diária",
    "",
    f"Atualizado (UTC): {payload['generated_at_utc']}",
    "",
    "> Dados de fecho Yahoo Finance; não são preços em tempo real. Alertas quantitativos, não sinais de compra/venda.",
    "",
    "| Ação | Sessão | Fecho | Variação | Vol. relativo | Alertas novos |",
    "|---|---|---:|---:|---:|---|",
]
for symbol, item in stocks.items():
    notes = "; ".join(a["message"] for a in item["alerts"]) or "—"
    rv = item["relative_volume_20d"]
    lines.append(f"| {symbol} | {item['asof']} | {item['close']:.2f} | {item['change_pct']:+.2f}% | {rv:.2f}× | {notes} |" if rv is not None else f"| {symbol} | {item['asof']} | {item['close']:.2f} | {item['change_pct']:+.2f}% | — | {notes} |")
if errors:
    lines.extend(["", "## Dados indisponíveis", ""])
    lines.extend(f"- {k}: {v}" for k, v in errors.items())
(OUT / "daily_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Wrote data/latest.json and data/daily_report.md")
