import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os

st.set_page_config(page_title="STOCK RADAR",page_icon="📈",layout="wide")
st.title("📈 STOCK RADAR")
st.caption("Análise de ações • dados de mercado sujeitos a atraso e disponibilidade da fonte")
if "tickers" not in st.session_state:
    st.session_state.tickers=["NFLX","SE","LULU","OKLO","AEVA"]
with st.sidebar:
    st.header("Ações")
    symbol=st.text_input("Adicionar ticker",placeholder="Ex.: ADUR").strip().upper()
    if st.button("Adicionar") and symbol and symbol not in st.session_state.tickers:
        st.session_state.tickers.append(symbol)
    ticker=st.selectbox("Selecionar",st.session_state.tickers)
    if st.button("Remover") and len(st.session_state.tickers)>1:
        st.session_state.tickers.remove(ticker)
        st.rerun()
    if st.button("Atualizar"):
        st.cache_data.clear()
        st.rerun()
    st.caption("A lista é mantida durante a sessão. Não introduzas chaves secretas em repositórios públicos.")

@st.cache_data(ttl=600)
def load(symbol):
    t=yf.Ticker(symbol)
    return t.info,t.history(period="10y",auto_adjust=True),t.financials,t.balance_sheet,t.cashflow

try:
    info,hist,financials,balance,cashflow=load(ticker)
except Exception as e:
    st.error(f"Erro ao obter dados: {e}")
    st.stop()
if hist.empty:
    st.error("Histórico indisponível para este ticker.")
    st.stop()

def num(v,d=2):
    try: return f"{float(v):,.{d}f}"
    except (ValueError,TypeError): return "N/D"
def big(v):
    try:
        v=float(v)
        if abs(v)>=1e9:return num(v/1e9)+" mil M"
        if abs(v)>=1e6:return num(v/1e6)+" M"
        return num(v)
    except (ValueError,TypeError):return "N/D"
def pct(v):
    try:return num(float(v)*100)+"%"
    except (ValueError,TypeError):return "N/D"

close=hist["Close"]
last=float(close.iloc[-1])
st.subheader(f'{info.get("longName",ticker)} ({ticker})')
st.caption(f'Último fecho disponível: {hist.index[-1].date()} • {info.get("currency","USD")} • fonte Yahoo Finance via yfinance; não é uma cotação garantida em tempo real')
a,b,c,d=st.columns(4)
a.metric("Último fecho",num(last))
b.metric("Capitalização",big(info.get("marketCap")))
c.metric("PER TTM",num(info.get("trailingPE")))
d.metric("P/S TTM",num(info.get("priceToSalesTrailing12Months")))

historico,fundamentais,tecnica,avaliacao,risco,resumo=st.tabs(["Histórico e volumes","Fundamentais","Análise técnica","Avaliação","Risco Kraken","Resumo"])
with historico:
    st.line_chart(close)
    periods={"1 semana":5,"1 mês":21,"3 meses":63,"6 meses":126,"1 ano":252,"2 anos":504,"3 anos":756,"5 anos":1260}
    changes={}
    for name,n in periods.items():
        changes[name]=f"{(last/float(close.iloc[-n-1])-1)*100:+.2f}%" if len(close)>n else "N/D"
    st.dataframe(pd.DataFrame(changes.items(),columns=["Período","Variação"]),hide_index=True)
    st.bar_chart(hist["Volume"])
    v=hist["Volume"]
    st.write("Volume da última sessão:",big(v.iloc[-1]),"| Média 20 sessões:",big(v.tail(20).mean()),"| Volume relativo:",num(v.iloc[-1]/v.tail(20).mean()) if v.tail(20).mean()>0 else "N/D")
    peak=float(close.max())
    st.metric("Queda desde máximo de fecho disponível",f"{(last/peak-1)*100:.1f}%")
    earlier=close.iloc[:-21]
    comparable=earlier[(earlier>=last*0.99)&(earlier<=last*1.01)]
    if not comparable.empty:
        st.info(f"Fecho anterior próximo do atual (±1%): {comparable.index[-1].date()}. Esta data não significa necessariamente que seja um mínimo plurianual.")
    else: st.info("Não foi encontrado um fecho anterior próximo do atual (±1%) no histórico disponível.")
    st.caption("Preços ajustados por desdobramentos e outros ajustes do fornecedor. Comparações históricas não são prova de subavaliação.")
with fundamentais:
    metrics={
        "Receitas TTM":big(info.get("totalRevenue")),
        "Crescimento receitas":pct(info.get("revenueGrowth")),
        "Lucro líquido":big(info.get("netIncomeToCommon")),
        "Margem operacional":pct(info.get("operatingMargins")),
        "Margem líquida":pct(info.get("profitMargins")),
        "PER futuro":num(info.get("forwardPE")),
        "EV/EBITDA":num(info.get("enterpriseToEbitda")),
        "P/FCF":num(info.get("marketCap")/info.get("freeCashflow")) if info.get("marketCap") and info.get("freeCashflow") and info.get("freeCashflow")>0 else "N/D",
        "Dívida total":big(info.get("totalDebt")),
        "Caixa":big(info.get("totalCash")),
        "Fluxo de caixa livre":big(info.get("freeCashflow")),
        "EPS futuro":num(info.get("forwardEps")),
    }
    st.dataframe(pd.DataFrame(metrics.items(),columns=["Indicador","Valor"]),hide_index=True)
    for title,df in [("Resultados",financials),("Balanço",balance),("Cash flow",cashflow)]:
        with st.expander(title):
            if df is not None and not df.empty:st.dataframe(df)
            else:st.write("N/D")
with tecnica:
    df=pd.DataFrame({"Fecho":close})
    for n in (20,50,200):df[f"SMA {n}"]=close.rolling(n).mean()
    st.line_chart(df)
    delta=close.diff()
    up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-100/(1+up/down.replace(0,np.nan))
    macd=close.ewm(span=12,adjust=False).mean()-close.ewm(span=26,adjust=False).mean()
    signal=macd.ewm(span=9,adjust=False).mean()
    st.metric("RSI 14",num(rsi.iloc[-1]))
    st.line_chart(pd.DataFrame({"MACD":macd,"Sinal":signal}))
    st.caption("Indicadores sobre fechos diários, não dados intradiários.")
with avaliacao:
    sector=(info.get("sector") or "").lower()
    prerevenue=not info.get("totalRevenue") or info.get("totalRevenue",0)<1e7
    if prerevenue:
        st.warning("Empresa sem receitas relevantes: PER e P/S podem não ser úteis. Analisar caixa, consumo de caixa, contratos, execução e diluição.")
    elif sector=="financial services":
        st.info("Serviços financeiros: considerar P/B, ROE, qualidade de crédito, capital e regulação; P/S isolado pode ser enganador.")
    else:
        st.info("A avaliação deve ser adaptada ao modelo de negócio. Um PER adequado à Netflix não é necessariamente adequado à OKLO.")
    eps=info.get("forwardEps")
    if eps and eps>0:
        chosen_pe=st.slider("PER hipotético",5,50,20)
        target=float(eps)*chosen_pe
        st.metric("Preço implícito",num(target),f"{(target/last-1)*100:+.1f}%")
        st.caption("Cenário matemático, não preço-alvo nem previsão.")
    else:st.write("EPS positivo indisponível. Avaliação por PER não aplicável.")
with risco:
    eur=st.number_input("Exposição em EUR",0.0,100000.0,400.0,50.0)
    fx=st.number_input("EUR/USD hipotético",0.1,3.0,1.16,0.01)
    limit=st.number_input("Drawdown restante em USD",0.0,5000.0,150.0,10.0)
    drop=st.slider("Queda hipotética (%)",0,70,15)
    loss=eur*fx*drop/100
    st.metric("Perda hipotética em USD",num(loss))
    st.metric("Drawdown remanescente",num(limit-loss))
    st.caption("Simulação simplificada. Não substitui regras da plataforma, câmbio real, comissões, perdas de outras posições nem liquidação intradiária.")
with resumo:
    st.write("**Contexto:**",info.get("longBusinessSummary","Descrição indisponível.")[:1300])
    st.write("**Preço e risco:**",f"Fecho {num(last)}; variação 1 ano {changes['1 ano']}; drawdown histórico de fechos {(last/peak-1)*100:.1f}%.")
    st.write("**Valuation:**",f"PER {num(info.get('trailingPE'))}; P/S {num(info.get('priceToSalesTrailing12Months'))}; margem operacional {pct(info.get('operatingMargins'))}.")
    st.warning("Resumo quantitativo automático, não investigação qualitativa por IA. Verificar relatórios oficiais, notícias, diluição, guidance e riscos antes de investir.")
