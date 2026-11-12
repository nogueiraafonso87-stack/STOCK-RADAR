"""Portuguese daily digest, including collection failures rather than fabricated news."""
from common import CATEGORIES, DATA, now, read, write

def main():
    day=now()[:10]
    events=read('events.json',{'events':[]})['events']
    # Prefer today's first detections, including filings published earlier.
    rows=[e for e in events if e['detected_at'][:10]==day]
    rows.sort(key=lambda e:e['date'],reverse=True)
    rows.sort(key=lambda e:({'alta':0,'média':1,'baixa':2}.get(e['relevance'],3)))
    lines=['# Resumo diário — STOCK-RADAR', '', f'Data: {day} (UTC)', '']
    if not rows: lines.append('Sem novos acontecimentos recolhidos nesta data. Consultar o estado das fontes abaixo; isto não garante ausência de notícias.')
    if len(rows)>20: lines.append(f'{len(rows)} acontecimentos detetados; apresentam-se os 20 prioritários. Histórico completo no painel de alertas.')
    for e in rows[:20]:
        lines.append(f'- **{e["ticker"]} · {CATEGORIES[e["category"]]}** ({e["date"]}): {e["title"]}. Estado: {e["status"]}. [Fonte]({e["source_url"]})')
    lines+=['','## Estado das fontes','']
    for name in ('market','sec'):
        status=read(name+'_status.json',{})
        lines.append(f'- {name}: '+('consulta com dados' if status.get('ok') else 'indisponível')+f'; execução {status.get("generated_at_utc","N/D")}; falhas: {len(status.get("errors",{}))}.')
    lines+=['','Guidance e consenso: N/D quando não há extração ou fonte validada. Documentos SEC classificados automaticamente exigem revisão. Notícias associadas não demonstram a causa de um movimento.']
    DATA.mkdir(parents=True,exist_ok=True)
    content='\n'.join(lines)+'\n'
    (DATA/'summary.md').write_text(content,encoding='utf-8')
    write(f'history/summary/{day}.json',dict(generated_at_utc=now(),event_ids=[e['id'] for e in rows],summary=content))
    print(content)

if __name__=='__main__': main()
