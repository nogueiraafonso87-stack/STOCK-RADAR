# STOCK-RADAR — monitorização

Aplicação: https://stock-radar-afonso.streamlit.app/

## Operação

- `watchlist.json` é a lista persistente usada pelo dashboard e pelos monitores. Os favoritos acrescentados na interface são apenas da sessão; editar este ficheiro para alterar a recolha diária.
- `python scripts/daily_monitor.py`: fechos ajustados Yahoo Finance, apenas sessões completas; movimento absoluto >5% e volume >2× a média das 20 sessões anteriores (excluindo a própria sessão). Notícias próximas são contexto secundário, nunca prova de causalidade. Preserva o último valor com `stale=true` quando uma ação falha. Mantém cruzamentos de MA50 em `technical_alerts`.
- `python scripts/sec_monitor.py`: metadados oficiais EDGAR, classificação de relatórios, possíveis emissões, acordos e eventos regulatórios. O mapa `sec_tickers.json` guarda CIK oficiais verificados, evitando consultas diárias desnecessárias ao mapa geral. Os candidatos ficam marcados **requer revisão**, sem afirmar que um prospeto confirma uma emissão ou que um 8-K confirma um contrato.
- As métricas XBRL extraídas incluem receita e EPS trimestrais separados, bem como dados anuais em USD: receita, EPS diluído, caixa, fluxo operacional, componentes corrente e não corrente da dívida de longo prazo e ações em circulação. Cada valor inclui período, tag e accession. Comparações usam o mesmo tag e intervalo anual comparável. Caixa e fluxo só produzem autonomia indicativa quando o fim de período coincide. As componentes de dívida não representam dívida total. Dados de bancos usam receita líquida de juros quando disponível; receita parcial de contratos não é apresentada como receita total. Alertas de caixa/dívida genéricos são suprimidos para instituições financeiras. Métricas cujo período termina há mais de 550 dias são sinalizadas e não originam novos alertas de resultados.
- Alertas numéricos: caixa cai >25%; componente de dívida aumenta >20%; consumo operacional anual aumenta >25%; ações aumentam >2% (requer revisão de desdobramentos e outras alterações). Estas regras são triagem quantitativa, não uma avaliação de solvência.
- `python scripts/build_summary.py`: resumo em português dos acontecimentos detetados no dia UTC, com fontes e falhas de recolha. O resumo destaca documentos dos últimos sete dias detetados na data; o histórico conserva os restantes.

## Histórico e dashboard

`data/events.json` mantém IDs determinísticos: repetições não duplicam alertas, e execuções vazias não apagam os anteriores. Relatórios diários ficam em `data/history/`. O dashboard lê os ficheiros locais do checkout, sem depender de uma segunda consulta a raw.githubusercontent.com. Filtra empresa, categoria, datas e relevância; permite descarregar o histórico. Mostra explicitamente o estado e as falhas de cada fonte.

GitHub Actions: diariamente às **23:15 UTC**, incluindo fins de semana; também manualmente e após alterações de código. As execuções podem atrasar. Cada fonte corre independentemente. Falhas reais de recolha fazem o workflow terminar com erro. Uma SEC sem contacto configurado produz estado explícito `configuration_required`/`degraded` e um aviso no resumo da execução, permitindo manter a recolha de mercado; não é considerada uma recolha SEC bem-sucedida. Há commits de histórico e artefactos por 30 dias. Conflitos de push falham visivelmente, sem forçar ou apagar alterações alheias.

SEC: é obrigatório definir `SEC_USER_AGENT` em **Settings → Secrets and variables → Actions → New repository secret**, com nome do projeto e contacto de email válido do responsável. Não colocar o contacto no código, em variables públicas, nos relatórios ou nos Issues. Sem esse secret, o monitor não envia pedidos e conserva os dados anteriores. A SEC recomenda identificar o cliente por nome e contacto no User-Agent: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data . O antigo fallback com URL do projeto foi removido. A configuração correta não garante, por si só, que um executor tenha acesso à SEC; qualquer 403 continua a ser comunicado.

## Limitações explícitas

- Guidance, consenso, beat/miss e extração de termos contratuais/ATM **não estão implementados**; são N/D. A classificação documental não os substitui.
- Não há parser geral de comunicados de relações com investidores, nem extração de factos de taxonomias personalizadas. Moedas diferentes de USD não são convertidas. Receita e EPS trimestrais só aparecem quando existe um facto trimestral comparável na taxonomia suportada; fluxo de caixa permanece anual.
- A ausência de um alerta não significa ausência de risco, notícia ou emissão. 6-K pode conter outros assuntos, pelo que os candidatos exigem revisão.
- Histórico inicial de metadados SEC: últimos 45 dias; execuções seguintes preservam acontecimentos recolhidos. Não é arquivo completo retroativo.
- Yahoo pode falhar ou rever preços e notícias. Não são cotações garantidas em tempo real. Autonomia é uma estimativa mecânica que exclui capex e futuras operações de financiamento.
- Streamlit gratuito pode adormecer por inatividade. O agendamento de recolha é independente da aplicação.

## Verificação

`python -m pytest -q` cobre limites estritos, sessão incompleta, dados em falta, persistência e deduplicação, classificação SEC, períodos anuais comparáveis, risco e estado de possível diluição, e renderização do painel Streamlit. Os dados artificiais dos testes não são publicados como relatórios reais.

Sem operações financeiras, subscrições ou chaves de serviços pagos.

Compatibilidade validada localmente com pandas 2.2.3 e 3.1.1. O ambiente Streamlit observado usa Python 3.14; pandas não fica fixado em 2.2.3, que não fornece wheel compatível. PyArrow é limitado a <25 conforme a mitigação de compatibilidade aplicada pelo próprio alojamento.

## Bloqueio observado no GitHub Actions (12-11-2026)

A recolha Yahoo funciona no runner GitHub. Nas duas primeiras execuções, a SEC devolveu HTTP 403 no runner hospedado: primeiro no mapa geral, depois também nos endpoints `data.sec.gov/submissions`. A consulta dos mesmos dados funcionou neste ambiente de desenvolvimento para as 19 empresas, e os resultados reais estão guardados. Isto **não valida a recolha SEC diária no GitHub**. O workflow conserva os dados oficiais anteriores, publica o erro no painel e termina com falha explícita. O mapa local resolve apenas a dependência do mapa geral; não resolve uma restrição HTTP aos dados individuais. Não são usados proxies de contorno, credenciais inventadas ou fontes apresentadas falsamente como oficiais. É necessário validar um contacto SEC adequado e/ou um executor com acesso permitido para concluir esta automatização.

## Correções de estabilidade — 12-11-2026

- `market_data.py` guarda preços e campos fundamentais Yahoo com timestamps individuais, durante no máximo sete dias. Se o alojamento receber 401/429 ou dados vazios, o dashboard usa a cópia válida e identifica explicitamente a sua data. Atualizar preços não renova artificialmente a data dos fundamentais. Campos sem dados válidos continuam N/D. O histórico de recurso pode ser mais curto do que os dez anos consultados normalmente.
- O monitor diário mantém os símbolos que não foram solicitados em execuções `--symbols`; relatórios assinalam valores anteriores preservados após uma falha. Dados infinitos/negativos são rejeitados antes de gerar JSON.
- RSI: séries só de subidas dão 100; só de descidas dão 0; séries constantes dão 50, após o período mínimo.
- SEC: campos opcionais em falta deixam de eliminar documentos; comparações homólogas requerem durações equivalentes e o mesmo conceito/taxonomia. Contactos privados não são incluídos em mensagens de erro. Após um 403, deixam de ser feitos pedidos adicionais nessa execução.
- O painel distingue última tentativa e última recolha válida; detalhes técnicos ficam recolhidos num expansor. Relatórios inválidos não fazem cair o resto da aplicação.
- `scripts/check_health.py` publica `data/health.json` e uma tabela no resumo do GitHub Actions. A distinção entre `ok`, `partial`, `configuration_required` e `failed` é mantida também quando o job termina com sucesso parcial.
