"""Regression tests for actual provider failures, malformed data and lost charts."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import pandas as pd
import pytest
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import common
import sec_monitor
from sec_monitor import metric,filing_rows,safe_error
from daily_monitor import analyze
from indicators import rsi
from market_data import save_cache,load_data,cache_path,read_cache


@pytest.mark.parametrize('prices,expected',[(list(range(30)),100),(list(range(30,0,-1)),0),([10]*30,50)])
def test_rsi_up_down_flat(prices,expected):
    assert rsi(pd.Series(prices)).iloc[-1]==expected


@pytest.mark.parametrize('column,value',[('Close',float('inf')),('Volume',float('inf'))])
def test_bad_market_numbers_fail_before_json_write(column,value):
    frame=pd.DataFrame({'Close':[100.]*21,'Volume':[100.]*21},index=pd.date_range('2026-01-01',periods=21))
    frame.loc[frame.index[-1],column]=value
    with pytest.raises(ValueError): analyze('X',frame,datetime(2026,2,1))


def test_sec_absent_optional_items_do_not_discard_filings():
    recent={'accessionNumber':['a','b'],'filingDate':['2026-11-01','2026-11-02'],'form':['10-Q','8-K'],'primaryDocument':['a.htm','b.htm'],'items':['2.02']}
    rows=list(filing_rows(recent))
    assert len(rows)==2 and rows[1][-1]==''


def test_comparison_rejects_different_length_quarters():
    rows=[dict(start='2026-07-01',end='2026-09-30',val=120,form='10-Q',filed='2026-11-01',accn='a'),dict(start='2025-07-20',end='2025-09-30',val=100,form='10-Q',filed='2025-11-01',accn='b')]
    facts={'facts':{'us-gaap':{'Revenues':{'units':{'USD':rows}}}}}
    assert metric(facts,['Revenues'],'USD','quarter')['yoy_pct'] is None


def test_equal_date_metric_prefers_configured_tag():
    base=dict(start='2026-07-01',end='2026-09-30',form='10-Q',filed='2026-11-01',accn='a')
    facts={'facts':{'us-gaap':{'Preferred':{'units':{'USD':[dict(base,val=120)]}},'Other':{'units':{'USD':[dict(base,val=10)]}}}}}
    assert metric(facts,['Preferred','Other'],'USD','quarter')['val']==120


def test_no_contact_does_not_make_requests_or_overwrite_last_good(tmp_path,monkeypatch):
    monkeypatch.delenv('SEC_USER_AGENT',raising=False)
    monkeypatch.setattr(common,'DATA',tmp_path)
    common.write('sec_events.json',{'generated_at_utc':'2026-11-01T00:00:00+00:00','events':[{'id':'kept'}]})
    monkeypatch.setattr(sec_monitor,'get_json',lambda url:pytest.fail('network call without contact'))
    with pytest.raises(SystemExit) as exc: sec_monitor.main(['NFLX'])
    assert exc.value.code==2
    assert common.read('sec_events.json')['events']==[{'id':'kept'}]
    status=common.read('sec_status.json')
    assert status['state']=='configuration_required'
    assert status['last_success_at_utc']=='2026-11-01T00:00:00+00:00'


def test_forbidden_stops_further_requests_and_preserves_history(tmp_path,monkeypatch):
    monkeypatch.setattr(common,'DATA',tmp_path)
    monkeypatch.setenv('SEC_USER_AGENT','TestSuite test@example.invalid')
    common.write('sec_events.json',{'generated_at_utc':'2026-11-01T00:00:00+00:00','events':[{'id':'kept'}]})
    calls=[]
    def fail(url):
        calls.append(url)
        response=requests.Response();response.status_code=403
        raise requests.HTTPError('Forbidden',response=response)
    monkeypatch.setattr(sec_monitor,'get_json',fail)
    with pytest.raises(SystemExit): sec_monitor.main(['NFLX','AEVA'])
    assert len(calls)==1
    assert common.read('sec_events.json')['events']==[{'id':'kept'}]
    assert len(common.read('sec_status.json')['errors'])==2


def test_private_contact_never_appears_in_error_report():
    exc=requests.exceptions.InvalidHeader('Secret User-Agent: private-contact@example.invalid')
    assert 'private-contact' not in safe_error(exc)


class FailedYahoo:
    def history(self,**kwargs): raise RuntimeError('provider unavailable')
    @property
    def info(self): return {'trailingPE':float('nan')}
    @property
    def financials(self): raise RuntimeError('provider unavailable')
    balance_sheet=financials
    cashflow=financials


def test_cached_data_preserves_charts_and_quotes_on_failure(tmp_path):
    frame=pd.DataFrame({'Close':[100.,101.],'Volume':[20,30]},index=pd.date_range('2026-11-10',periods=2))
    save_cache('X',frame,{'longName':'Example','marketCap':123,'trailingPE':10},tmp_path)
    info,hist,financials,balance,cashflow,unavailable,provenance=load_data('X',tmp_path,lambda s:FailedYahoo())
    assert hist.Close.iloc[-1]==101
    assert info['marketCap']==123 and info['trailingPE']==10
    assert provenance['history'] and provenance['info']['marketCap']
    assert financials.empty and unavailable


def test_repeated_price_updates_do_not_refresh_old_fundamentals(tmp_path):
    frame=pd.DataFrame({'Close':[100.],'Volume':[20]},index=pd.date_range('2026-11-10',periods=1))
    save_cache('X',frame,{'marketCap':123},tmp_path)
    path=cache_path('X',tmp_path);data=json.loads(path.read_text())
    data['field_dates']['marketCap']=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
    path.write_text(json.dumps(data))
    save_cache('X',frame,{},tmp_path)
    assert 'marketCap' not in read_cache('X',tmp_path)['info']


def test_expired_cache_is_not_used(tmp_path):
    frame=pd.DataFrame({'Close':[100.],'Volume':[20]},index=pd.date_range('2026-11-10',periods=1))
    save_cache('X',frame,{'marketCap':123},tmp_path)
    path=cache_path('X',tmp_path);data=json.loads(path.read_text())
    data['fetched_at']=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat();path.write_text(json.dumps(data))
    info,hist,*rest=load_data('X',tmp_path,lambda s:FailedYahoo())
    assert 'marketCap' not in info and hist.empty


def test_dashboard_survives_malformed_saved_reports(tmp_path):
    from streamlit.testing.v1 import AppTest
    (tmp_path/'events.json').write_text(json.dumps({'events':[{'ticker':'X','category':'earnings','date':'NaT','title':'bad','relevance':'alta','status':'confirmado','source_url':'https://example.invalid'}]}))
    (tmp_path/'sec_events.json').write_text(json.dumps({'companies':{'X':{'metrics':None}}}))
    (tmp_path/'market_status.json').write_text('{broken')
    app=AppTest.from_string(f'from monitoring_ui import render_monitoring\nrender_monitoring({str(tmp_path)!r})').run(timeout=30)
    assert not app.exception
    assert len(app.warning)>=2


def test_health_does_not_present_missing_configuration_as_success():
    from check_health import assess
    health,fatal=assess({'market':{'ok':True},'sec':{'ok':False,'state':'configuration_required'}})
    assert not fatal and health['state']=='degraded'
    assert health['sources']['sec']['state']=='configuration_required'


def test_health_does_not_hide_http_failure():
    from check_health import assess
    health,fatal=assess({'market':{'ok':True},'sec':{'ok':False,'state':'unavailable','errors':{'X':'HTTP 403'}}})
    assert fatal and health['state']=='failed'


def test_full_dashboard_works_when_yahoo_is_unavailable(tmp_path,monkeypatch):
    import market_data
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    history=pd.DataFrame({'Close':[100.+i for i in range(252)],'Volume':[100.]*252},index=pd.date_range('2026-01-01',periods=252))
    save_cache('NFLX',history,{'marketCap':123,'trailingPE':10,'longName':'Cached Netflix'},tmp_path)
    original=market_data.load_data
    monkeypatch.setattr(market_data,'load_data',lambda symbol:original(symbol,tmp_path,lambda s:FailedYahoo()))
    st.cache_data.clear()
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=40)
    assert not app.exception and not app.error
    assert len(app.tabs)==5
    assert any('guardados' in x.value for x in app.info)
    assert next(m for m in app.metric if m.label=='Capitalização').value=='123.00'
    st.cache_data.clear()
