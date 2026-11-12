# STOCK-RADAR: monitorização automática

O GitHub Actions executa `scripts/daily_monitor.py` de segunda a sexta às 23:15 UTC e pode ser iniciado manualmente em **Actions → STOCK-RADAR daily market monitor → Run workflow**.

**Saídas:** `data/latest.json` (dados estruturados) e `data/daily_report.md` (relatório legível). São atualizados por commit automático quando a execução consegue recolher dados. O relatório contém preços de fecho, variação diária, volume relativo à média das 20 sessões anteriores, cruzamentos da média de 50 sessões e erros de recolha.

**Alertas atuais:** movimento diário absoluto ≥5%, volume relativo ≥2× e cruzamento da média de 50 sessões. O sistema só sinaliza uma sessão nova; não envia notificações externas. Um alerta não implica compra ou venda.

**Limitações:** Yahoo Finance pode atrasar, bloquear ou corrigir dados; os dados são diários e não em tempo real. As execuções agendadas podem atrasar ou falhar, e o GitHub pode desativar agendamentos de repositórios públicos inativos. Verificar o separador Actions e o carimbo temporal antes de confiar num relatório. A lista de ações está definida no script; não recolhe resultados financeiros nem notícias nesta fase. Para empresas cotadas fora dos EUA, confirmar moeda e símbolo.

**Segurança:** não há chaves de API nem operações de corretagem. Nunca adicionar tokens ou credenciais ao código público.
