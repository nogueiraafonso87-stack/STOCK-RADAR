"""Distinguish failed code/data collection from an unconfigured optional source."""
import os
from pathlib import Path
from common import now,read,write


def assess(statuses):
    sources={};fatal=False
    for source,status in statuses.items():
        if source=='sec' and status.get('state')=='configuration_required':
            state='configuration_required'
        elif status.get('ok'):
            state='partial' if status.get('errors') or status.get('warnings') else 'ok'
        else:
            state='failed';fatal=True
        sources[source]={'state':state,'last_attempt_at_utc':status.get('generated_at_utc'),
                         'last_success_at_utc':status.get('last_success_at_utc'),
                         'successes':status.get('successes',0),'errors':len(status.get('errors',{}))}
    return {'generated_at_utc':now(),'state':'failed' if fatal else ('degraded' if any(s['state']!='ok' for s in sources.values()) else 'ok'), 'sources':sources},fatal


def main():
    health,fatal=assess({name:read(name+'_status.json',{}) for name in ('market','sec')})
    write('health.json',health)
    lines=['## STOCK-RADAR — estado da recolha','',f'Estado global: **{health["state"]}**','', '| Fonte | Estado | Empresas recolhidas | Falhas |','|---|---|---:|---:|']
    for name,item in health['sources'].items():
        lines.append(f'| {name} | {item["state"]} | {item["successes"]} | {item["errors"]} |')
        if item['state']=='configuration_required':
            print('::warning title=SEC por configurar::Definir SEC_USER_AGENT em Actions secrets com identificação e contacto válido. Recolha SEC não executada; dados anteriores preservados.')
        elif item['state']=='failed':
            print(f'::error title={name} indisponível::A recolha falhou. Verificar os relatórios e os registos; os dados anteriores foram preservados.')
        elif item['state']=='partial':
            print(f'::warning title={name} parcial::Alguns pedidos à fonte falharam; consultar datas e relatórios.')
    lines+=['','`configuration_required` não significa uma recolha bem-sucedida. O mercado continua independente da configuração SEC.']
    report='\n'.join(lines)+'\n'
    summary=os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a',encoding='utf-8') as f:f.write(report)
    print(report)
    if fatal: raise SystemExit(1)

if __name__=='__main__':main()
