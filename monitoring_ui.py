"""Monitoring view kept independent of price charts for offline rendering and testing."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st
from scripts.common import CATEGORIES
from datetime import date


def render_monitoring(root=None):
    root=Path(root) if root is not None else Path(__file__).resolve().parent/'data'
    def load(name,default):
        path=root/name
        try:
            value=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value,type(default)): raise ValueError('Formato inválido')
            return value
        except FileNotFoundError:
            return default
        except (OSError,ValueError):
            st.warning(f'O relatório {name} está indisponível ou inválido. Os restantes relatórios continuam acessíveis.')
            return default
    with st.expander('🔔 Monitorização automática e resumo diário',expanded=False):
        st.caption('Dados de fecho. Favoritos automáticos definidos em watchlist.json; adicionar ações à sessão não altera o agendamento.')
        for source in ('market','sec'):
            status=load(source+'_status.json',{})
            snapshot=load('latest.json' if source=='market' else 'sec_events.json',{})
            label='recolha parcial' if status.get('errors') and status.get('ok') else ('dados recolhidos' if status.get('ok') else 'atualização indisponível')
            st.caption(f'{source.upper()} · última tentativa UTC: {status.get("generated_at_utc","N/D")} · {label}')
            last_good=status.get('last_success_at_utc') or snapshot.get('generated_at_utc')
            if last_good: st.caption('Última recolha válida UTC: '+last_good)
            if status.get('errors'):
                if status.get('state')=='configuration_required':
                    st.warning('SEC: falta configurar o contacto de identificação nas definições privadas do repositório. Os dados anteriores foram preservados.')
                else:
                    st.warning(f'{source.upper()}: atualização indisponível para {len(status["errors"])} consultas. São mantidos os últimos dados válidos; verifica a data.')
                with st.expander('Detalhes da recolha '+source.upper()):
                    st.json(status['errors'])
            if status.get('warnings'):
                st.caption(f'Fundamentais parcialmente indisponíveis para {len(status["warnings"])} ações; valores guardados conservam a data original.')
        summary=root/'summary.md'
        if summary.exists():
            try: st.markdown(summary.read_text(encoding='utf-8'))
            except (OSError,UnicodeError): st.warning('Resumo diário indisponível; consulta os acontecimentos abaixo.')
        raw_events=load('events.json',{'events':[]}).get('events',[])
        events=[]
        if not isinstance(raw_events,list):
            st.warning('Histórico de acontecimentos inválido. Não foi interpretado como ausência de alertas.')
            raw_events=[]
        for e in raw_events:
            try:
                if not isinstance(e,dict) or not all(k in e for k in ('ticker','category','date','title','relevance','status','source_url')): continue
                if e['category'] not in CATEGORIES: continue
                if not all(isinstance(e[k],str) for k in ('ticker','date','title','relevance','status','source_url')): continue
                date.fromisoformat(e['date'])
                events.append(e)
            except (ValueError,TypeError): continue
        if len(events)<len(raw_events): st.warning('Alguns acontecimentos têm formato inválido e não são apresentados.')
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
        saved_companies=sec.get('companies',{})
        if not isinstance(saved_companies,dict):
            st.warning('Métricas financeiras guardadas com formato inválido.')
            saved_companies={}
        for symbol,company in sorted(saved_companies.items()):
            if not isinstance(company,dict) or not isinstance(company.get('metrics'),dict):
                st.warning(f'Métricas de {symbol} indisponíveis.');continue
            with st.expander(f'{symbol} — métricas oficiais SEC'):
                st.caption('Recolha UTC: '+company.get('updated_at','N/D'))
                metrics=company['metrics']
                labels={'revenue':'Receita anual','eps':'EPS diluído anual','quarterly_revenue':'Receita trimestral','quarterly_eps':'EPS diluído trimestral','cash':'Caixa','operating_cashflow':'Fluxo operacional anual','debt_current':'Dívida de longo prazo — parcela corrente','debt_noncurrent':'Dívida de longo prazo — não corrente','shares':'Ações em circulação'}
                table=[]
                for key,label in labels.items():
                    value=metrics.get(key)
                    if not isinstance(value,dict) or not isinstance(value.get('val'),(int,float)): value=None
                    table.append({'Indicador':label,'Valor':f'{value["val"]:,.2f}' if value else 'N/D','Unidade':value.get('unit','') if value else '', 'Fim do período':value.get('end','') if value else '', 'Estado':'Desatualizado' if value and value.get('stale') else ('Disponível' if value else 'N/D')})
                st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
                st.caption(metrics.get('method',''))
                st.caption(metrics.get('guidance',''))
                st.caption(metrics.get('analyst_consensus',''))
                st.json(metrics,expanded=False)
                if company.get('source_url'): st.link_button('XBRL oficial',company['source_url'])
