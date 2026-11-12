# Validação — 12 de novembro de 2026

## Resultado observado

- Aplicação pública reativada e operacional: https://stock-radar-afonso.streamlit.app/ . Reiniciada após corrigir incompatibilidade de instalação pandas 2.2.3 / Python 3.14. A publicação final foi observada com os gráficos e os cinco separadores existentes.
- 18 testes passaram localmente. O teste integral Streamlit (`AppTest`) não registou exceções nem erros, incluindo pandas 3.1.1.
- Monitor de mercado executado com sucesso para as 19 ações, com sessão de 11-11-2026. Relatório JSON e Markdown gerados. Foram observados três movimentos >5% e o cruzamento MA50 de SOFI.
- Monitor SEC executado neste ambiente para as 19 empresas, com recolha de metadados e XBRL sem erros. Dados com período, unidade, tag e accession guardados. Valores trimestrais não são misturados com YTD nem anuais. Dados antigos estão sinalizados; receitas bancárias usam conceitos apropriados.
- O filtro público Categoria = Movimentos relevantes reduziu o painel a três acontecimentos. Empresa, relevância e intervalo de datas presentes. Captura em `validation.jpg`.

## GitHub Actions

Execução mais recente de validação: https://github.com/nogueiraafonso87-stack/STOCK-RADAR/actions/runs/43215519803

Os testes, recolha de mercado, geração do resumo, commit dos relatórios e upload de artefactos completaram-se. A consulta SEC devolveu HTTP 403 no runner GitHub para os 19 símbolos. O workflow terminou em falha explícita na verificação final; não deve ser descrito como aprovado integralmente. Foram inspecionados também os logs das duas execuções anteriores. Os dados SEC recolhidos neste ambiente estão preservados; a execução falhada não os substitui por listas vazias. O estado no dashboard evidencia a fonte indisponível.

Agendamento configurado: todos os dias às 23:15 UTC. A recolha de mercado foi validada no runner; a recolha SEC agendada permanece bloqueada. Não foram contratados serviços pagos nem executadas operações financeiras.

## Ainda por concluir

1. Resolver acesso permitido aos endpoints SEC a partir do executor diário. Identificação/contacto SEC configurável por secret; não há garantia de que só essa alteração resolva uma restrição do runner.
2. Extrair e validar guidance e termos de contratos, cancelamentos, ATM e marcos regulatórios. Atualmente, os metadados geram candidatos que exigem revisão.
3. Integrar consenso verificável de analistas; enquanto faltar, não se calcula beat/miss.
4. Recolha sistemática de comunicados de relações com investidores e taxonomias XBRL personalizadas.
5. Favoritos alterados na interface são de sessão; a monitorização usa a lista persistente `watchlist.json`.
6. Yahoo devolveu 401/429 em alguns pedidos de fundamentais do alojamento. Os campos indisponíveis ficam N/D; os gráficos e os relatórios de fecho continuaram disponíveis.
