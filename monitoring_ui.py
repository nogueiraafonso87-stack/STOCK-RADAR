"""Monitoring view kept independent of price charts for offline rendering and testing."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from scripts.common import CATEGORIES


def render_monitoring():
    root=Path(__file__).resolve().parent/'data'
    def load(name,default):
        try: return json.loads((root/name).read_text(encoding='utf-8'))
        except (OSError,ValueError): return default
    with st.expander('🔔 Monitorização automática e resumo diário',expanded=False):
        st.caption('Dados de fecho. Favoritos automáticos definidos em watchlist.json; adicionar ações à sessão não altera o agendamento.')
        for source in ('market','sec'):
            status=load(source+'_status.json',{})
            st.caption(f'{source.upper()} · execução UTC: {status.get("generated_at_utc","N/D")} · '+('dados recolhidos' if status.get('ok') else 'sem recolha validada'))
            if status.get('errors'):
                st.warning(f'{source.upper()}: '+json.dumps(status['errors'],ensure_ascii=False))
        summary=root/'summary.md'
        if summary.exists(): st.markdown(summary.read_text(encoding='utf-8'))
        events=load('events.json',{'events':[]})['events']
        if events:
            a,b,c=st.columns(3)
            companies=a.multiselect('Empresa',sorted({e['ticker'] for e in events}))
            categories=b.multiselect('Categoria',list(CATEGORIES),format_func=CATEGORIES.get)
            relevance=c.multiselect('Relevância',['alta','média','baixa'])
            dates=sorted({e['date'] for e in events})
            start,end=st.slider('Intervalo de datas',min_value=pd.Timestamp(dates[0]).date(),max_value=pd.Timestamp(dates[-1]).date(),value=(pd.Timestamp(dates[0]).date(),pd.Timestamp(dates[-1]).date())) if len(dates)>1 else (pd.Timestamp(dates[0]).date(),pd.Timestamp(dates[0]).date())
            rows=[e for e in events if (not companies or e['ticker'] in companies) and (not categories or e['category'] in categories) and (not relevance or e['relevance'] in relevance) and str(start)<=e['date']<=str(end)]
            st.caption(f'{len(rows)} acontecimentos; documentos por rever não são acontecimentos confirmados.')
            for e in rows[:100]:
                with st.expander(f'{e["ticker"]} · {e["date"]} · {CATEGORIES[e["category"]]} · {e["title"]}'):
                    st.write(f'Estado: {e["status"]} · Relevância: {e["relevance"]}')
                    st.json(e.get('details',{}))
                    st.link_button('Consultar fonte',e['source_url'])
            st.download_button('Descarregar histórico completo',json.dumps(events,ensure_ascii=False,indent=2),'stock-radar-events.json','application/json')
        else: st.info('Ainda não existem alertas recolhidos. Verifica o estado das fontes acima.')
        market=load('latest.json',{})
        technical=[]
        for symbol,item in market.get('stocks',{}).items():
            for alert in item.get('technical_alerts',[]):
                technical.append({'Empresa':symbol,'Sessão':item['asof'],'Alerta técnico':alert['message']})
        if technical:
            st.write('Cruzamentos da média móvel de 50 sessões')
            st.dataframe(pd.DataFrame(technical),hide_index=True,width='stretch')
        sec=load('sec_events.json',{})
        for symbol,company in sorted(sec.get('companies',{}).items()):
            with st.expander(f'{symbol} — métricas oficiais SEC'):
                st.caption('Recolha UTC: '+company['updated_at'])
                metrics=company['metrics']
                labels={'revenue':'Receita anual','eps':'EPS diluído anual','quarterly_revenue':'Receita trimestral','quarterly_eps':'EPS diluído trimestral','cash':'Caixa','operating_cashflow':'Fluxo operacional anual','debt_current':'Dívida de longo prazo — parcela corrente','debt_noncurrent':'Dívida de longo prazo — não corrente','shares':'Ações em circulação'}
                table=[]
                for key,label in labels.items():
                    value=metrics.get(key)
                    table.append({'Indicador':label,'Valor':f'{value["val"]:,.2f}' if value else 'N/D','Unidade':value.get('unit','') if value else '', 'Fim do período':value.get('end','') if value else '', 'Estado':'Desatualizado' if value and value.get('stale') else ('Disponível' if value else 'N/D')})
                st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
                st.caption(metrics.get('method',''))
                st.caption(metrics.get('guidance',''))
                st.caption(metrics.get('analyst_consensus',''))
                st.json(metrics,expanded=False)
                st.link_button('XBRL oficial',company['source_url'])
