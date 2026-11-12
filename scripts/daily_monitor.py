"""Daily completed-session market monitor; Yahoo data is secondary and may be delayed."""
import argparse
import math
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf
from common import DATA, ROOT, event, merge_events, now, read, watchlist, write

sys.path.insert(0,str(ROOT))
from market_data import save_cache


def analyze(symbol, hist, clock=None):
    clock = clock or datetime.now(ZoneInfo('America/New_York'))
    # Exclude today's candle before 16:15 New York (conservative closing buffer).
    dates = pd.to_datetime(hist.index).date
    keep = [(d < clock.date()) or (d == clock.date() and (clock.hour,clock.minute) >= (16,15)) for d in dates]
    hist = hist.loc[keep].dropna(subset=['Close','Volume'])
    if len(hist) < 21:
        raise ValueError('São necessárias 21 sessões completas válidas')
    close, volume = hist['Close'].astype(float), hist['Volume'].astype(float)
    if not all(math.isfinite(x) for x in close) or not all(math.isfinite(x) for x in volume) or (close <= 0).any() or (volume < 0).any():
        raise ValueError('Preços ou volumes inválidos')
    change = 100 * (close.iloc[-1]/close.iloc[-2]-1)
    avg = float(volume.iloc[-21:-1].mean())
    ratio = float(volume.iloc[-1]/avg) if avg > 0 else None
    date = str(hist.index[-1].date())
    alerts=[]
    url=f'https://finance.yahoo.com/quote/{symbol}/history/'
    if abs(change)>5 and not math.isclose(abs(change),5,abs_tol=1e-9):
        alerts.append(event(symbol,'movement',date,f'Variação diária {change:+.2f}%',url,date,
                            details={'change_pct':float(change), 'context':'Sem causa confirmada; consultar documentos oficiais e notícias associadas.'}))
    if ratio is not None and ratio>2:
        alerts.append(event(symbol,'volume',date,f'Volume {ratio:.2f}× a média das 20 sessões anteriores',url,date,
                            details={'relative_volume':ratio,'average_volume':avg}))
    technical=[]
    if len(close)>=51:
        ma50=float(close.tail(50).mean())
        prior_ma50=float(close.iloc[-51:-1].mean())
        if (float(close.iloc[-2])-prior_ma50)*(float(close.iloc[-1])-ma50)<0:
            technical=[{'type':'ma50_cross','message':'Cruzou a média móvel de 50 sessões para '+('cima' if close.iloc[-1]>ma50 else 'baixo')}]
    for alert in alerts:
        alert['relevance']='alta' if abs(change)>10 or (ratio or 0)>4 else 'média'
    return dict(asof=date,close=float(close.iloc[-1]),change_pct=float(change),volume=int(volume.iloc[-1]),
                relative_volume_20d=ratio,ma20=float(close.tail(20).mean()),
                ma50=float(close.tail(50).mean()) if len(close)>=50 else None,
                alerts=alerts,technical_alerts=technical,data_source='Yahoo Finance / yfinance; fecho ajustado; dados secundários'), alerts


def main(symbols=None):
    previous=read('latest.json',{}).get('stocks',{})
    stocks,errors,events={}, {}, []
    warnings={}
    for symbol in symbols or watchlist():
        try:
            provider=yf.Ticker(symbol)
            history=provider.history(period='1y',interval='1d',auto_adjust=True)
            item,alerts=analyze(symbol,history)
            try:
                info=provider.info
                if not isinstance(info,dict): info={}
                if not info.get('marketCap'): warnings[symbol]='Fundamentais Yahoo parciais ou indisponíveis; valores anteriores válidos preservados.'
            except Exception:
                info={};warnings[symbol]='Fundamentais Yahoo indisponíveis; valores anteriores válidos preservados.'
            try:
                save_cache(symbol,history.loc[pd.to_datetime(history.index).date<=pd.Timestamp(item['asof']).date()],info,DATA/'market_cache')
            except Exception:
                warnings[symbol]='Não foi possível atualizar a cópia local; os preços recolhidos continuam disponíveis.'
            if any(e['category']=='movement' for e in alerts):
                try:
                    articles=[]
                    for news in yf.Ticker(symbol).news or []:
                        content=news.get('content',news)
                        published=content.get('pubDate','')
                        link=(content.get('canonicalUrl') or {}).get('url')
                        if link and published and abs((pd.Timestamp(published).date()-pd.Timestamp(item['asof']).date()).days)<=2:
                            articles.append({'title':content.get('title'),'published_at':published,'url':link})
                    for alert in alerts:
                        if alert['category']=='movement':
                            alert['details']['related_news']=articles[:5]
                            alert['details']['context']='Notícias próximas da sessão; relação causal não confirmada.' if articles else 'Sem notícia próxima disponível; causa não confirmada.'
                except Exception:
                    for alert in alerts:
                        if alert['category']=='movement': alert['details']['news_error']='Consulta de notícias indisponível'
            stocks[symbol]=item
            events.extend(alerts)
            print(f'OK {symbol}: {item["asof"]}',flush=True)
        except Exception as exc:
            errors[symbol]=str(exc)[:250]
            if symbol in previous:
                stocks[symbol]={**previous[symbol], 'stale':True}
            print(f'ERROR {symbol}: {exc}',flush=True)
    successes=len(stocks)-sum(bool(x.get('stale')) for x in stocks.values())
    last_success=now() if successes else read('market_status.json',{}).get('last_success_at_utc')
    write('market_status.json',dict(generated_at_utc=now(),ok=successes>0,successes=successes,errors=errors,warnings=warnings,last_success_at_utc=last_success))
    if successes==0:
        raise SystemExit('Sem dados novos utilizáveis; relatório anterior preservado.')
    if symbols:
        stocks={**{s:v for s,v in previous.items() if s not in symbols},**stocks}
    payload=dict(generated_at_utc=now(),stocks=stocks,errors=errors)
    write('latest.json',payload)
    write(f'history/market/{now()[:10]}.json',payload)
    merge_events(events)
    lines=['# STOCK-RADAR — Monitorização diária','',f'Execução UTC: {now()}','', 'Dados de fecho Yahoo Finance; podem sofrer atrasos ou revisões.','', '| Ação | Sessão | Fecho | Variação | Volume relativo | Estado |','|---|---|---:|---:|---:|---|']
    for symbol,item in stocks.items():
        rv=item.get('relative_volume_20d')
        lines.append(f'| {symbol} | {item["asof"]} | {item["close"]:.2f} | {item["change_pct"]:+.2f}% | '+(f'{rv:.2f}×' if rv is not None else 'N/D')+' | '+('Último dado válido — falha na recolha' if item.get('stale') else 'Recolhido')+' |')
    (DATA/'daily_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbols',nargs='+')
    main(parser.parse_args().symbols)
