# STOCK-RADAR — monitorização

Aplicação: https://stock-radar-afonso.streamlit.app/

## Operação

- `watchlist.json` é a lista persistente usada pelo dashboard e pelos monitores. Os favoritos acrescentados na interface são apenas da sessão; editar este ficheiro para alterar a recolha diária.
- `python scripts/daily_monitor.py`: fechos ajustados Yahoo Finance, apenas sessões completas; movimento absoluto >5% e volume >2× a média das 20 sessões anteriores (excluindo a própria sessão). Notícias próximas são contexto secundário, nunca prova de causalidade. Preserva o último valor com `stale=true` quando uma ação falha. Mantém cruzamentos de MA50 em `technical_alerts`.
- `python scripts/sec_monitor.py`: metadados oficiais EDGAR, classificação de relatórios, possíveis emissões, acordos e eventos regulatórios. Os candidatos ficam marcados **requer revisão**, sem afirmar que um prospeto confirma uma emissão ou que um 8-K confirma um contrato.
- As métricas XBRL extraídas incluem receita e EPS trimestrais separados, bem como dados anuais em USD: receita, EPS diluído, caixa, fluxo operacional, componentes corrente e não corrente da dívida de longo prazo e ações em circulação. Cada valor inclui período, tag e accession. Comparações usam o mesmo tag e intervalo anual comparável. Caixa e fluxo só produzem autonomia indicativa quando o fim de período coincide. As componentes de dívida não representam dívida total. Dados de bancos exigem interpretação específica.
- Alertas numéricos: caixa cai >25%; componente de dívida aumenta >20%; consumo operacional anual aumenta >25%; ações aumentam >2% (requer revisão de desdobramentos e outras alterações). Estas regras são triagem quantitativa, não uma avaliação de solvência.
- `python scripts/build_summary.py`: resumo em português dos acontecimentos detetados no dia UTC, com fontes e falhas de recolha.

## Histórico e dashboard

`data/events.json` mantém IDs determinísticos: repetições não duplicam alertas, e execuções vazias não apagam os anteriores. Relatórios diários ficam em `data/history/`. O dashboard lê os ficheiros locais do checkout, sem depender de uma segunda consulta a raw.githubusercontent.com. Filtra empresa, categoria, datas e relevância; permite descarregar o histórico. Mostra explicitamente o estado e as falhas de cada fonte.

GitHub Actions: diariamente às **23:15 UTC**, incluindo fins de semana; também manualmente e após alterações de código. As execuções podem atrasar. Cada fonte corre independentemente; as falhas são guardadas antes de o workflow terminar com erro. Há commits de histórico e artefactos por 30 dias. Conflitos de push falham visivelmente, sem forçar ou apagar alterações alheias.

SEC: a identificação por omissão usa o nome do projeto e o respetivo canal público de contacto (Issues do repositório), sem contactos fictícios ou dados pessoais. Foi aceite nas consultas reais de validação. Pode definir `SEC_USER_AGENT` como secret de Actions com contacto do responsável se a SEC o exigir posteriormente. Falhas HTTP são visíveis e preservam o relatório anterior.

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
