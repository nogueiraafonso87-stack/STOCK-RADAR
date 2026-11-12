"""Shared, deterministic event storage. No credentials or brokerage access."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('STOCK_RADAR_DATA', ROOT / 'data'))
CATEGORIES = {'earnings':'Resultados financeiros','volume':'Volume anormal','movement':'Movimentos relevantes','risk':'Risco financeiro','dilution':'Diluição','contracts':'Contratos e projetos'}

def now():
    return datetime.now(timezone.utc).isoformat()

def read(name, default=None):
    path = DATA / name
    if not path.exists():
        return default
    # A corrupt history must never silently be overwritten.
    return json.loads(path.read_text(encoding='utf-8'))

def write(name, payload):
    path = DATA / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(path)

def watchlist():
    return json.loads((ROOT / 'watchlist.json').read_text())['tickers']

def event(ticker, category, date, title, source_url, identity, **extra):
    return dict(id=hashlib.sha256(f'{ticker}:{category}:{identity}'.encode()).hexdigest()[:24], ticker=ticker,
                category=category, date=date, title=title, source_url=source_url,
                relevance='média', status='confirmado', detected_at=now(), **extra)

def merge_events(events):
    history = read('events.json', {'events':[]})
    merged = {e['id']: e for e in history['events']}
    for e in events:
        if e['id'] in merged:
            e['detected_at'] = merged[e['id']]['detected_at']
        merged[e['id']] = e
    rows = sorted(merged.values(), key=lambda e:(e['date'],e['id']), reverse=True)
    write('events.json', {'generated_at_utc':now(), 'events':rows})
    return rows
