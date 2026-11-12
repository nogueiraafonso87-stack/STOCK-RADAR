"""Dated Yahoo cache; provider failures never turn missing values into zeroes."""
import json
import math
from datetime import datetime, timezone, timedelta
from io import StringIO
from pathlib import Path
import pandas as pd
import yfinance as yf

INFO_FIELDS = ('longName','currency','marketCap','trailingPE','priceToSalesTrailing12Months',
               'totalRevenue','revenueGrowth','netIncomeToCommon','operatingMargins','profitMargins',
               'forwardPE','enterpriseToEbitda','freeCashflow','totalDebt','totalCash','forwardEps',
               'trailingEps','sector','longBusinessSummary')
CACHE=Path(__file__).resolve().parent/'data'/'market_cache'


def usable(value):
    return value is not None and (not isinstance(value,(float,int)) or math.isfinite(value))


def cache_path(symbol,directory):
    # Symbols from UI never become arbitrary filesystem paths.
    import hashlib
    return Path(directory)/(hashlib.sha256(symbol.encode()).hexdigest()[:20]+'.json')


def read_cache(symbol,directory=CACHE,clock=None):
    clock=clock or datetime.now(timezone.utc)
    try:
        payload=json.loads(cache_path(symbol,directory).read_text(encoding='utf-8'))
        timestamp=datetime.fromisoformat(payload['fetched_at'])
        if timestamp.tzinfo is None: return {}
        if timestamp>clock+timedelta(minutes=5) or clock-timestamp>timedelta(days=7): return {}
        return payload if payload.get('symbol')==symbol else {}
    except (OSError,ValueError,KeyError,TypeError):
        return {}


def save_cache(symbol,history,info,directory=CACHE):
    from scripts.common import now
    fetched=now()
    old=read_cache(symbol,directory)
    fields=dict(old.get('info',{}))
    dates=dict(old.get('field_dates',{}))
    for key in INFO_FIELDS:
        if usable(info.get(key)):
            fields[key]=info[key]
            dates[key]=fetched
    # Individual info fields keep their own timestamps; a price refresh does not refresh old ratios.
    cutoff=datetime.now(timezone.utc)-timedelta(days=7)
    fields={k:v for k,v in fields.items() if k in dates and datetime.fromisoformat(dates[k])>=cutoff}
    payload={'symbol':symbol,'fetched_at':fetched,'source':'Yahoo Finance / yfinance',
             'info':fields,'field_dates':{k:dates[k] for k in fields},
             'history':json.loads(history.to_json(orient='split',date_format='iso'))}
    path=cache_path(symbol,directory);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8');temp.replace(path)


def load_data(symbol,directory=CACHE,ticker_factory=None):
    provider=(ticker_factory or yf.Ticker)(symbol)
    cache=read_cache(symbol,directory)
    unavailable=[];provenance={}
    try:
        history=provider.history(period='10y',auto_adjust=True)
    except Exception:
        history=pd.DataFrame()
    if not isinstance(history,pd.DataFrame) or history.empty or not {'Close','Volume'}.issubset(history.columns):
        unavailable.append('history')
        saved=cache.get('history')
        history=pd.read_json(StringIO(json.dumps(saved)),orient='split') if saved else pd.DataFrame()
        if not history.empty: provenance['history']=cache['fetched_at']
    try:
        raw=provider.info
        info=raw if isinstance(raw,dict) else {}
    except Exception:
        info={}
    cached_fields={}
    for key,value in cache.get('info',{}).items():
        timestamp=cache.get('field_dates',{}).get(key)
        try: fresh=timestamp and datetime.now(timezone.utc)-datetime.fromisoformat(timestamp)<=timedelta(days=7)
        except (ValueError,TypeError): fresh=False
        if not usable(info.get(key)) and fresh:
            info[key]=value;cached_fields[key]=timestamp
    if cached_fields: provenance['info']=cached_fields
    if not all(usable(info.get(k)) for k in ('marketCap','trailingPE','priceToSalesTrailing12Months')):
        unavailable.append('info (parcial ou indisponível)')
    frames=[]
    for name in ('financials','balance_sheet','cashflow'):
        try:
            frame=getattr(provider,name)
            if not isinstance(frame,pd.DataFrame) or frame.empty:
                unavailable.append(name);frame=pd.DataFrame()
        except Exception:
            unavailable.append(name);frame=pd.DataFrame()
        frames.append(frame)
    return info,history,*frames,unavailable,provenance
