"""SEC official submissions and XBRL, with explicitly unverified document candidates."""
import argparse
import os
import time
from datetime import date, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from common import event, merge_events, now, read, watchlist, write

SESSION=requests.Session()
SESSION.mount('https://',HTTPAdapter(max_retries=Retry(total=3,backoff_factor=1,status_forcelist=[429,500,502,503,504])))


def get_json(url):
    time.sleep(.12)
    response=SESSION.get(url,timeout=30)
    response.raise_for_status()
    return response.json()


def classify(form, items=''):
    if form.removesuffix('/A') in ('10-Q','10-K','20-F','40-F'):
        return ['earnings','risk','dilution']
    if form in ('S-1','S-1/A','S-3','S-3ASR','F-3','F-3ASR','424B5'):
        return ['dilution']
    if form in ('8-K','8-K/A'):
        codes={c.strip() for c in items.split(',')}
        tags=[]
        if '2.02' in codes: tags.append('earnings')
        if codes & {'1.01','1.02','7.01','8.01'}: tags.append('contracts')
        if '3.02' in codes: tags.append('dilution')
        if codes & {'2.03','2.04','1.03'}: tags.append('risk')
        return tags
    if form in ('6-K','6-K/A'):
        return ['earnings','contracts']  # foreign issuer metadata lacks 8-K item codes
    return []


def metric(facts, tags, unit, duration):
    """Select a comparable annual period or instant; never mix quarterly and YTD."""
    rows=[]
    for namespace in ('us-gaap','ifrs-full','dei'):
        for tag in tags:
            for item in facts.get('facts',{}).get(namespace,{}).get(tag,{}).get('units',{}).get(unit,[]):
                allowed=('10-K','10-K/A','20-F','20-F/A','40-F') if duration is True else ('10-Q','10-Q/A','10-K','10-K/A','20-F','20-F/A','40-F','6-K')
                if item.get('form') not in allowed:
                    continue
                if duration:
                    if not item.get('start'): continue
                    days=(date.fromisoformat(item['end'])-date.fromisoformat(item['start'])).days
                    if duration=='quarter':
                        if not 70<=days<=110: continue
                    elif not 330<=days<=380: continue
                elif item.get('start'): continue
                rows.append(dict(item,tag=tag,unit=unit))
    if not rows: return None
    # Prefer first available taxonomy tag at the latest period.
    rows.sort(key=lambda x:(x['end'],x.get('filed','')),reverse=True)
    latest=rows[0]
    prior=[r for r in rows if r['tag']==latest['tag'] and 330<=(date.fromisoformat(latest['end'])-date.fromisoformat(r['end'])).days<=400]
    result={k:latest.get(k) for k in ('val','start','end','filed','accn','tag','unit')}
    result['previous']=({k:prior[0].get(k) for k in ('val','start','end','accn')} if prior else None)
    p=result['previous']
    result['yoy_pct']=100*(latest['val']/p['val']-1) if p and p['val']>0 else None
    return result


def extract_metrics(facts):
    specs={
        'revenue':(['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','Revenue'],'USD',True),
        'eps':(['EarningsPerShareDiluted','DilutedEarningsLossPerShare'],'USD/shares',True),
        'cash':(['CashAndCashEquivalentsAtCarryingValue','CashAndCashEquivalents'],'USD',False),
        'operating_cashflow':(['NetCashProvidedByUsedInOperatingActivities','CashFlowsFromUsedInOperatingActivities'],'USD',True),
        'debt_long_term':(['LongTermDebtCurrent','LongTermDebtNoncurrent'],'USD',False),
        'shares':(['CommonStockSharesOutstanding','EntityCommonStockSharesOutstanding'],'shares',False)}
    values={k:metric(facts,*v) for k,v in specs.items()}
    # Long-term debt components are kept separate; a single tag is never total debt.
    values['debt_current']=metric(facts,['LongTermDebtCurrent'],'USD',False)
    values['debt_noncurrent']=metric(facts,['LongTermDebtNoncurrent'],'USD',False)
    values.pop('debt_long_term')
    cash,flow=values['cash'],values['operating_cashflow']
    values['runway_months']=None
    if cash and flow and flow['val']<0 and cash['end']==flow['end']:
        values['runway_months']=12*cash['val']/abs(flow['val'])
    values['quarterly_revenue']=metric(facts,specs['revenue'][0],'USD','quarter')
    values['quarterly_eps']=metric(facts,specs['eps'][0],'USD/shares','quarter')
    values['method']='Receita, EPS e fluxo anual USD; receita e EPS trimestrais separados; balanço da última divulgação disponível. Comparação anual de períodos equivalentes; autonomia indicativa = caixa / consumo operacional anual × 12. Exclui investimentos, novo financiamento e caixa restrita; não é previsão.'
    values['guidance']='N/D — exige leitura do comunicado oficial; não extraído automaticamente.'
    values['analyst_consensus']='N/D — sem fonte de consenso validada; beat/miss não calculado.'
    return values


def metric_alerts(ticker, metrics, source_url):
    alerts=[]
    for key,label in (('quarterly_revenue','Receita trimestral'),('quarterly_eps','EPS diluído trimestral')):
        m=metrics.get(key)
        if m:
            comparison=f'; variação homóloga {m["yoy_pct"]:+.1f}%' if m.get('yoy_pct') is not None else '; comparação homóloga N/D'
            alerts.append(event(ticker,'earnings',m['filed'],f'{label}: {m["val"]:,.2f} {m["unit"]} (fim {m["end"]})'+comparison,source_url,str(m['accn'])+key,details=m))
    for key,label,category,threshold in (
        ('cash','Redução da caixa','risk',-25),
        ('debt_current','Aumento da componente corrente da dívida de longo prazo','risk',20),
        ('debt_noncurrent','Aumento da dívida de longo prazo não corrente','risk',20),
        ('shares','Alteração do número de ações; verificar emissões e desdobramentos','dilution',2)):
        m=metrics.get(key)
        if not m or m.get('yoy_pct') is None: continue
        change=m['yoy_pct']
        if (threshold<0 and change<threshold) or (threshold>0 and change>threshold):
            e=event(ticker,category,m['filed'],f'{label}: {change:+.1f}% face ao período anual comparável',source_url,str(m['accn'])+key,details={'metric':key,**m})
            e['relevance']='alta'
            if category=='dilution': e['status']='requer revisão'
            alerts.append(e)
    cashflow=metrics.get('operating_cashflow')
    if cashflow and cashflow['val']<0:
        previous=cashflow.get('previous')
        if previous and previous['val']<0 and abs(cashflow['val'])>abs(previous['val'])*1.25:
            e=event(ticker,'risk',cashflow['filed'],'Consumo anual de caixa operacional aumentou mais de 25%',source_url,str(cashflow['accn'])+'burn',details=cashflow)
            e['relevance']='alta'; alerts.append(e)
    return alerts


def main(symbols=None):
    agent=os.getenv('SEC_USER_AGENT','').strip() or 'STOCK-RADAR/1.0 (project contact: https://github.com/nogueiraafonso87-stack/STOCK-RADAR/issues)'
    SESSION.headers.update({'User-Agent':agent,'Accept-Encoding':'gzip, deflate'})
    old=read('sec_events.json',{'events':[],'companies':{}})
    events=[]
    companies=dict(old.get('companies',{}))
    errors={}
    try:
        mapping={r['ticker'].upper():str(r['cik_str']).zfill(10) for r in get_json('https://www.sec.gov/files/company_tickers.json').values()}
    except Exception as exc:
        write('sec_status.json',dict(generated_at_utc=now(),ok=False,errors={'mapping':str(exc)[:200]}))
        raise
    cutoff=str(date.today()-timedelta(days=45))
    successes=0
    titles={'earnings':'Relatório ou comunicado financeiro — rever resultados e guidance','risk':'Documento com informação de risco financeiro — requer revisão','dilution':'Documento a rever para possível diluição; não confirma emissão','contracts':'Acordo ou comunicação relevante — termos e impacto por confirmar'}
    for ticker in symbols or watchlist():
        try:
            cik=mapping.get(ticker)
            if not cik: raise ValueError('Símbolo não encontrado no mapa oficial SEC')
            submissions=get_json(f'https://data.sec.gov/submissions/CIK{cik}.json')
            recent=submissions.get('filings',{}).get('recent',{})
            for i,accession in enumerate(recent.get('accessionNumber',[])):
                day=recent['filingDate'][i]
                if day<cutoff: continue
                form=recent['form'][i]
                items=(recent.get('items') or ['']*len(recent['form']))[i]
                url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{recent["primaryDocument"][i]}'
                for category in classify(form,items):
                    e=event(ticker,category,day,titles[category],url,accession,
                            details={'form':form,'items':items,'accession':accession,'note':'Classificação de metadados SEC; não confirma o conteúdo, a emissão, o contrato ou a sua materialidade.'})
                    e['status']='requer revisão'
                    events.append(e)
            successes+=1
            try:
                facts=get_json(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
                metrics=extract_metrics(facts)
                source=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
                companies[ticker]=dict(updated_at=now(),source_url=source,metrics=metrics)
                events.extend(metric_alerts(ticker,metrics,source))
            except Exception as exc:
                errors[ticker+':facts']=str(exc)[:200]
            print(f'OK SEC {ticker}',flush=True)
        except Exception as exc:
            errors[ticker]=str(exc)[:200]
            print(f'ERROR SEC {ticker}: {exc}',flush=True)
    write('sec_status.json',dict(generated_at_utc=now(),ok=successes>0,successes=successes,errors=errors))
    if not successes: raise SystemExit('Nenhuma empresa consultada; relatório anterior preservado.')
    history=merge_events(events)
    payload=dict(generated_at_utc=now(),events=[e for e in history if e['category'] not in ('volume','movement')],companies=companies,errors=errors)
    write('sec_events.json',payload)
    write(f'history/sec/{now()[:10]}.json',payload)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--symbols',nargs='+')
    main(p.parse_args().symbols)
