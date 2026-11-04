import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import altair as alt

st.set_page_config(page_title="STOCK RADAR",page_icon="📈",layout="wide")
st.title("📈 STOCK RADAR")
st.caption("Análise de ações • dados de mercado sujeitos a atraso e disponibilidade da fonte")
DEFAULT_TICKERS=["NFLX","SE","LULU","OKLO","AEVA","FIG","RIVN","KULR","NKE","ASTS"]
WATCHLIST_VERSION=3
if "tickers" not in st.session_state:
    st.session_state.tickers=DEFAULT_TICKERS.copy()
if st.session_state.get("watchlist_version",0)<WATCHLIST_VERSION:
    st.session_state.tickers=list(dict.fromkeys(st.session_state.tickers+DEFAULT_TICKERS))
    st.session_state.watchlist_version=WATCHLIST_VERSION
XTB_CATALOG_URL="https://www.xtb.com/web-api/v3/languages/pt/branches/pt/instrument-specification"

@st.cache_data(ttl=86400,show_spinner="A carregar catálogo oficial da XTB...")
def xtb_catalog():
    from concurrent.futures import ThreadPoolExecutor
    import math
    def page(number):
        response=requests.get(XTB_CATALOG_URL,params={"typeSlug":"cashstocks","pageSize":1000,"page":number},timeout=30)
        response.raise_for_status()
        return response.json()
    first=page(1)
    total=int(first["instrumentCounts"]["cashstocks"])
    items=first["items"]
    size=len(items)
    if not size:
        raise ValueError("Catálogo vazio")
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(page,range(2,math.ceil(total/size)+1)):
            items.extend(result["items"])
    items=[item for item in items if item.get("typeSlug")=="cashstocks"]
    unique={item["symbol"]:item for item in items}
    if len(unique)!=total:
        raise ValueError("O catálogo mudou durante a consulta. Tenta novamente.")
    return sorted(unique.values(),key=lambda item:(item.get("companyName") or item["symbol"]).casefold())

def yahoo_symbol(xtb_symbol):
    base,market=xtb_symbol.rsplit(".",1)
    suffixes={"US":"","DE":".DE","FR":".PA","NL":".AS","BE":".BR","ES":".MC","PT":".LS","IT":".MI","UK":".L","PL":".WA","CH":".SW","SE":".ST","DK":".CO","FI":".HE","NO":".OL","CZ":".PR"}
    overrides={"SE1.US":"SE","BRKB.US":"BRK-B","BRKA.US":"BRK-A","BF.B.US":"BF-B"}
    if xtb_symbol in overrides:
        return overrides[xtb_symbol]
    if market not in suffixes:
        return None
    if market=="US":
        base=base.replace(".","-")
    elif market in ("SE","DK"):
        base=base.replace(" ","-").replace(".","-")
    return base+suffixes[market]

def search_xtb(items,query,country="Todos"):
    import re
    candidates=[item for item in items if country=="Todos" or (item.get("instrumentCountryName") or "Outro")==country]
    query=query.strip().casefold()
    if not query:
        return candidates,False
    def rank(item):
        symbol=item["symbol"].rsplit(".",1)[0].casefold()
        name=(item.get("companyName") or "").casefold()
        standard=(yahoo_symbol(item["symbol"]) or "").casefold()
        if query in (symbol,item["symbol"].casefold(),standard):
            return -1
        if symbol.startswith(query) or standard.startswith(query):
            return 0
        if name.startswith(query):
            return 1
        if any(word.startswith(query) for word in re.split(r"[^\w]+",name)):
            return 2
        if len(query)>=3 and query in name:
            return 3
        return 99
    results=[item for item in candidates if rank(item)<99]
    return sorted(results,key=lambda item:(rank(item),not item["symbol"].endswith(".US"),(item.get("companyName") or "").casefold(),item["symbol"])),False

@st.dialog("Pesquisar ações",width="large",on_dismiss="rerun")
def stock_search():
    try:
        catalog=xtb_catalog()
    except Exception:
        st.error("Não foi possível carregar o catálogo. Tenta novamente.")
        return
    query=st.text_input("Símbolo ou nome da empresa",placeholder="Pesquisar: SE, Nike, Rivian...",key="symbol_search_query")
    st.markdown("**Ações** · Catálogo XTB Portugal")
    countries=sorted({item.get("instrumentCountryName") or "Outro" for item in catalog})
    country=st.selectbox("País / mercado",["Todos"]+countries,key="symbol_search_country")
    matches,_=search_xtb(catalog,query,country)
    st.caption(f"{len(matches):,} resultados · correspondências exatas primeiro")
    if not matches:
        st.info("Nenhum resultado. Tenta outro símbolo ou nome.")
        return
    limit=st.session_state.get("symbol_search_limit",20)
    with st.container(height=470,border=False):
        for item in matches[:limit]:
            symbol=yahoo_symbol(item["symbol"]) or item["symbol"]
            company=item.get("companyName") or symbol
            market=item.get("stockMarket") or item.get("instrumentCountryName") or ""
            with st.container(border=True):
                name,exchange,favorite,action=st.columns([4.5,1.8,2.2,1.2],vertical_alignment="center")
                with name:
                    st.markdown(f":blue[**{symbol}**]  \n{company}")
                with exchange:
                    st.caption(f'{market} · {item.get("currencyCode","")}  \n{item["symbol"]}')
                with favorite:
                    favorite_symbol=yahoo_symbol(item["symbol"])
                    saved=favorite_symbol in st.session_state.tickers
                    if st.button("★ Nos favoritos" if saved else "☆ Adicionar aos favoritos",key=f'favorite_stock_{item["symbol"]}',disabled=saved or favorite_symbol is None,use_container_width=True):
                        st.session_state.tickers.append(favorite_symbol)
                        st.toast(f"{favorite_symbol} adicionado aos favoritos",icon="⭐")
                        st.rerun(scope="fragment")
                with action:
                    if st.button("Abrir",key=f'open_stock_{item["symbol"]}',use_container_width=True):
                        st.session_state.selected_xtb=item
                        st.session_state.pending_catalog=True
                        st.rerun()
    if len(matches)>limit and st.button("Mostrar mais resultados"):
        st.session_state.symbol_search_limit=limit+20
        st.rerun(scope="fragment")

if st.session_state.pop("pending_catalog",False):
    st.session_state.stock_universe="Catálogo XTB"
if st.button("Pesquisar ações",icon=":material/search:",use_container_width=True):
    stock_search()

selected_xtb=None
with st.sidebar:
    st.header("Ações")
    symbol=st.text_input("Adicionar ticker",placeholder="Ex.: ADUR").strip().upper()
    if st.button("Adicionar") and symbol and symbol not in st.session_state.tickers:
        st.session_state.tickers.append(symbol)
    universe=st.radio("Lista de ações",["Favoritos","Catálogo XTB"],horizontal=True,key="stock_universe")
    if universe=="Favoritos":
        ticker=st.selectbox("Selecionar",st.session_state.tickers)
    else:
        selected_xtb=st.session_state.get("selected_xtb")
        if selected_xtb is None:
            st.caption("Usa Pesquisar ações no topo da página.")
            ticker=None
        else:
            ticker=yahoo_symbol(selected_xtb["symbol"])
            st.markdown(selected_xtb.get("companyName") or selected_xtb["symbol"])
            st.caption(f'{selected_xtb["symbol"]} · {selected_xtb.get("stockMarket","")}')
            if ticker is None:
                ticker=st.text_input("Símbolo Yahoo Finance",key="xtb_manual_symbol").strip().upper() or None
            if selected_xtb.get("closeOnly"):
                st.warning("Apenas fecho de posições na XTB.")
            if ticker and st.button("Guardar nos favoritos") and ticker not in st.session_state.tickers:
                st.session_state.tickers.append(ticker)
    if st.button("Remover",disabled=ticker not in st.session_state.tickers) and len(st.session_state.tickers)>1:
        st.session_state.tickers.remove(ticker)
        st.rerun()
    if st.button("Atualizar"):
        st.cache_data.clear()
        st.rerun()
    st.caption("A lista é mantida durante a sessão. Não introduzas chaves secretas em repositórios públicos.")

if not ticker:
    st.info("Clica em Pesquisar ações, escreve um símbolo ou nome e escolhe Abrir.")
    st.stop()

@st.cache_data(ttl=600)
def load(symbol):
    t=yf.Ticker(symbol)
    hist=t.history(period="10y",auto_adjust=True)
    unavailable=[]
    def optional(name,empty):
        try:
            value=getattr(t,name)
            if value is None or (isinstance(value,dict) and not value) or (isinstance(value,pd.DataFrame) and value.empty):
                unavailable.append(name)
                return empty
            return value
        except Exception:
            unavailable.append(name)
            return empty
    info=optional("info",{})
    financials=optional("financials",pd.DataFrame())
    balance=optional("balance_sheet",pd.DataFrame())
    cashflow=optional("cashflow",pd.DataFrame())
    return info,hist,financials,balance,cashflow,unavailable

try:
    info,hist,financials,balance,cashflow,unavailable=load(ticker)
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

if unavailable:
    st.warning("O fornecedor não disponibilizou alguns dados fundamentais nesta consulta. Os campos em falta aparecem como N/D; o histórico e a análise técnica continuam disponíveis. Tenta Atualizar mais tarde.")
close=hist["Close"]
last=float(close.iloc[-1])
st.subheader(f'{info.get("longName",ticker)} ({ticker})')
st.caption(f'Último fecho disponível: {hist.index[-1].date()} • {info.get("currency","USD")} • fonte Yahoo Finance via yfinance; não é uma cotação garantida em tempo real')
a,b,c,d=st.columns(4)
a.metric("Último fecho",num(last))
b.metric("Capitalização",big(info.get("marketCap")))
c.metric("PER TTM",num(info.get("trailingPE")))
d.metric("P/S TTM",num(info.get("priceToSalesTrailing12Months")))

historico,fundamentais,tecnica,avaliacao,resumo=st.tabs(["Histórico e volumes","Fundamentais","Análise técnica","Avaliação","Resumo"])
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
            if df is not None and not df.empty:
                priority=["Total Revenue","Cost Of Revenue","Gross Profit","Operating Income","EBIT","EBITDA","Net Income","Diluted EPS","Total Assets","Total Liabilities Net Minority Interest","Stockholders Equity","Operating Cash Flow","Capital Expenditure","Free Cash Flow"]
                ordered=[row for row in priority if row in df.index]
                ordered+= [row for row in df.index if row not in ordered]
                display=df.loc[ordered].copy()
                display.columns=[col.strftime("%Y-%m-%d") if hasattr(col,"strftime") else str(col) for col in display.columns]
                display.index.name="Indicador"
                st.dataframe(display.style.format(precision=2,thousands=" ",na_rep="N/D"))
                st.caption("Valores originais do fornecedor, na moeda da empresa (exceto rácios e valores por ação). 0 é o valor devolvido pelo Yahoo Finance, não uma validação independente dos relatórios oficiais; N/D indica dados indisponíveis. Rubricas técnicas, como Tax Effect Of Unusual Items, podem ser zero sem que as receitas ou os lucros sejam zero.")
            else:st.write("N/D")
def labelled_lines(frame,labels,colors,y_label):
    data=frame.copy()
    data.index.name="Data"
    data=data.reset_index().melt("Data",var_name="Indicador",value_name="Valor").dropna()
    chart=alt.Chart(data).mark_line().encode(
        x=alt.X("Data:T",title="Data"),
        y=alt.Y("Valor:Q",title=y_label,scale=alt.Scale(zero=False)),
        color=alt.Color("Indicador:N",scale=alt.Scale(domain=labels,range=colors),legend=alt.Legend(title="Legenda",orient="top")),
        tooltip=[alt.Tooltip("Data:T",title="Data"),"Indicador:N",alt.Tooltip("Valor:Q",format=",.2f")]
    ).properties(height=380).interactive()
    st.altair_chart(chart,use_container_width=True)

with tecnica:
    df=pd.DataFrame({"Fecho":close})
    for n in (20,50,200):df[f"SMA {n}"]=close.rolling(n).mean()
    st.subheader("Preço de fecho e médias móveis")
    labelled_lines(df,["Fecho","SMA 20","SMA 50","SMA 200"],["#1565c0","#f59e0b","#16a34a","#dc2626"],"Preço")
    st.caption("Azul: fecho diário · Laranja: média de 20 sessões · Verde: média de 50 sessões · Vermelho: média de 200 sessões. SMA significa média móvel simples.")
    delta=close.diff()
    up=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean()
    down=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-100/(1+up/down.replace(0,np.nan))
    macd=close.ewm(span=12,adjust=False).mean()-close.ewm(span=26,adjust=False).mean()
    signal=macd.ewm(span=9,adjust=False).mean()
    st.metric("RSI 14",num(rsi.iloc[-1]))
    st.subheader("MACD e linha de sinal")
    labelled_lines(pd.DataFrame({"MACD":macd,"Sinal":signal}),["MACD","Sinal"],["#1565c0","#dc2626"],"MACD")
    st.caption("Azul: MACD (média exponencial de 12 sessões menos a de 26) · Vermelho: sinal (média exponencial de 9 sessões do MACD).")
    st.caption("Indicadores sobre fechos diários, não dados intradiários.")
with avaliacao:
    sector=(info.get("sector") or "").lower()
    revenue=info.get("totalRevenue")
    prerevenue=revenue is not None and revenue<1e7
    if revenue is None:
        st.info("Receitas indisponíveis nesta consulta. Não é possível classificar a empresa pela receita nem concluir que não tem receitas.")
    elif prerevenue:
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
with resumo:
    st.write("**Contexto:**",(info.get("longBusinessSummary") or "Descrição indisponível.")[:1300])
    st.write("**Preço e risco:**",f"Fecho {num(last)}; variação 1 ano {changes['1 ano']}; drawdown histórico de fechos {(last/peak-1)*100:.1f}%.")
    st.write("**Valuation:**",f"PER {num(info.get('trailingPE'))}; P/S {num(info.get('priceToSalesTrailing12Months'))}; margem operacional {pct(info.get('operatingMargins'))}.")
    st.warning("Resumo quantitativo automático, não investigação qualitativa por IA. Verificar relatórios oficiais, notícias, diluição, guidance e riscos antes de investir.")
