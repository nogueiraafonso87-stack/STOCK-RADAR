import json
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import common
from daily_monitor import analyze
from sec_monitor import classify, extract_metrics


def candles(change=5,volume=200):
    return pd.DataFrame({'Close':[100.]*20+[100+change],'Volume':[100.]*20+[volume]},index=pd.date_range('2026-01-01',periods=21))


def test_strict_thresholds_and_prior_twenty():
    clock=datetime(2026,2,1,tzinfo=ZoneInfo('America/New_York'))
    _,alerts=analyze('X',candles(5,200),clock)
    # Floating point representation of 5% should not create a boundary alert.
    assert not alerts
    item,alerts=analyze('X',candles(6,201),clock)
    assert item['relative_volume_20d']==2.01
    assert {e['category'] for e in alerts}=={'volume','movement'}


def test_intraday_exclusion_and_bad_data():
    clock=datetime(2026,1,21,15,tzinfo=ZoneInfo('America/New_York'))
    with pytest.raises(ValueError): analyze('X',candles(),clock)
    hist=candles();hist.loc[hist.index[-1],'Close']=float('nan')
    with pytest.raises(ValueError): analyze('X',hist,datetime(2026,2,1,tzinfo=clock.tzinfo))


def test_history_is_idempotent_and_survives_empty_run(tmp_path,monkeypatch):
    monkeypatch.setattr(common,'DATA',tmp_path)
    e=common.event('X','volume','2026-01-21','Test','https://example.org','session')
    common.merge_events([e]);common.merge_events([dict(e,detected_at='new')])
    rows=common.merge_events([])
    assert len(rows)==1 and rows[0]['detected_at']==e['detected_at']
    (tmp_path/'events.json').write_text('broken')
    with pytest.raises(json.JSONDecodeError): common.merge_events([])


@pytest.mark.parametrize('form,items,categories',[
    ('8-K','2.02',['earnings']),('8-K','1.01,3.02',['contracts','dilution']),
    ('8-K','2.03',['risk']),('424B5','',['dilution']),('6-K','',['earnings','contracts']),
    ('10-Q','',['earnings','risk','dilution']),('4','',[])])
def test_categories(form,items,categories):
    assert classify(form,items)==categories


def test_annual_comparison_ignores_quarters_and_ytd():
    rows=[dict(start='2024-01-01',end='2024-12-31',val=100,form='10-K',filed='2025-02-01',accn='a'),dict(start='2025-01-01',end='2025-12-31',val=120,form='10-K',filed='2026-02-01',accn='b'),dict(start='2026-01-01',end='2026-03-31',val=50,form='10-Q',filed='2026-05-01',accn='c')]
    facts={'facts':{'us-gaap':{'Revenues':{'units':{'USD':rows}}}}}
    metrics=extract_metrics(facts)
    assert metrics['revenue']['val']==120
    assert metrics['revenue']['yoy_pct']==pytest.approx(20)
    assert metrics['runway_months'] is None
    assert metrics['analyst_consensus'].startswith('N/D')


def test_monitoring_view_renders():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('from monitoring_ui import render_monitoring\nrender_monitoring()').run()
    assert not app.exception


def test_risk_and_shares_do_not_claim_confirmed_dilution():
    from sec_monitor import metric_alerts
    base=dict(val=120,previous={'val':100},yoy_pct=20,end='2025-12-31',filed='2026-02-01',accn='a')
    rows=metric_alerts('X',{'shares':base,'cash':dict(base,yoy_pct=-30)},'https://data.sec.gov/test')
    assert len(rows)==2
    assert next(e for e in rows if e['category']=='dilution')['status']=='requer revisão'
    assert all(e['relevance']=='alta' for e in rows)


def test_sec_pipeline_preserves_events_on_repeat(tmp_path,monkeypatch):
    import sec_monitor
    monkeypatch.setenv('SEC_USER_AGENT','TestSuite test@example.invalid')
    monkeypatch.setattr(common,'DATA',tmp_path)
    today=datetime.now().date().isoformat()
    def get(url):
        if 'company_tickers' in url: return {'0':{'ticker':'X','cik_str':1}}
        if 'submissions' in url:
            return {'filings':{'recent':{'accessionNumber':['1-26-1'],'form':['8-K'],'filingDate':[today],'primaryDocument':['filing.htm'],'items':['2.02,1.01']}}}
        return {'facts':{}}
    monkeypatch.setattr(sec_monitor,'get_json',get)
    sec_monitor.main(['X']);sec_monitor.main(['X'])
    rows=common.read('sec_events.json')['events']
    assert len(rows)==2
    assert {e['category'] for e in rows}=={'earnings','contracts'}
    assert all(e['status']=='requer revisão' for e in rows)


def test_filters_with_saved_events():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('from monitoring_ui import render_monitoring\nrender_monitoring()').run()
    if app.multiselect:
        first=app.multiselect[0].options[0]
        app.multiselect[0].select(first).run()
        assert not app.exception
        app.multiselect[1].select('volume').run()
        assert not app.exception


def test_quarter_metrics_exclude_ytd_and_annual():
    from sec_monitor import metric
    rows=[dict(start='2026-01-01',end='2026-09-30',val=300,form='10-Q',filed='2026-11-01',accn='a'),dict(start='2026-07-01',end='2026-09-30',val=120,form='10-Q',filed='2026-11-01',accn='a'),dict(start='2025-07-01',end='2025-09-30',val=100,form='10-Q',filed='2025-11-01',accn='b')]
    facts={'facts':{'us-gaap':{'Revenues':{'units':{'USD':rows}}}}}
    result=metric(facts,['Revenues'],'USD','quarter')
    assert result['val']==120 and result['yoy_pct']==pytest.approx(20)


def test_banking_revenue_does_not_use_partial_contract_revenue():
    row=dict(start='2026-07-01',end='2026-09-30',val=100,form='10-Q',filed='2026-11-01',accn='a')
    facts={'facts':{'us-gaap':{'RevenueFromContractWithCustomerExcludingAssessedTax':{'units':{'USD':[row]}}}}}
    metrics=extract_metrics(facts,financial=True)
    assert metrics['quarterly_revenue'] is None


def test_stale_earnings_are_not_new_financial_alerts():
    from sec_monitor import metric_alerts
    metrics={'quarterly_revenue':dict(val=100,unit='USD',end='2018-09-30',filed='2018-11-01',accn='old',stale=True)}
    assert not metric_alerts('X',metrics,'https://data.sec.gov/test')
