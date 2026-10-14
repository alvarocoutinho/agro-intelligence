#!/usr/bin/env python3
"""Check V8 output ZIP without modifying any source files or making internet calls."""
from __future__ import annotations
import argparse,csv,io,json,sqlite3,tempfile,zipfile
from collections import Counter
from pathlib import Path

REQUIRED = [
    'resumo_v8.json', 'fao_precos_normalizados_v8.csv',
    'fao_series_classificadas_v8.csv', 'fao_pares_atacado_varejo_v8.csv',
    'alertas_qualidade_v8.csv', 'agro_integrado_v8.sqlite',
]
def csv_rows(z, name):
    return list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig'))))

def audit(path):
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist()); missing=set(REQUIRED)-names
        if missing: raise ValueError('Arquivos ausentes: '+', '.join(sorted(missing)))
        s=json.loads(z.read('resumo_v8.json'))
        precos=csv_rows(z, 'fao_precos_normalizados_v8.csv')
        series=csv_rows(z, 'fao_series_classificadas_v8.csv')
        pares=csv_rows(z, 'fao_pares_atacado_varejo_v8.csv')
        alertas=csv_rows(z, 'alertas_qualidade_v8.csv')
        uuids=[(r['uuid'],r['data']) for r in precos]
        pairs_key=[(r['produto'],r['regiao'],r['data']) for r in pares]
        violations=[]
        if len(uuids)!=len(set(uuids)): violations.append('cotações duplicadas por UUID/data')
        if len(pairs_key)!=len(set(pairs_key)): violations.append('pares duplicados por produto/região/data')
        if len(precos)!=int(s['observacoes']): violations.append('n_observacoes difere do resumo')
        if len(series)!=int(s['series']): violations.append('n_series difere do resumo')
        if len(pares)!=int(s['pares_completos']): violations.append('n_pares difere do resumo')
        tipos=Counter(r['tipo_preco'] for r in precos)
        if set(tipos)-{'ATACADO','VAREJO'}: violations.append('tipo de preço desconhecido')
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'db.sqlite';db.write_bytes(z.read('agro_integrado_v8.sqlite'))
            cn=sqlite3.connect(str(db))
            try:
                integrity=cn.execute('PRAGMA integrity_check').fetchone()[0]
                tables={a for (a,) in cn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                ndb=cn.execute('SELECT COUNT(*) FROM fao_precos_normalizados_v8').fetchone()[0]
            finally:cn.close()
        if integrity!='ok':violations.append(f'SQLite integrity: {integrity}')
        if ndb!=len(precos):violations.append('banco difere do CSV normalizado')
        return {
            'resultado':'APROVADO_ESTRUTURALMENTE' if not violations else 'REVISAR',
            'observacoes':len(precos),'series':len(series),'pares':len(pares),
            'atacado':tipos['ATACADO'],'varejo':tipos['VAREJO'],
            'pares_varejo_menor_atacado':sum(1 for r in pares if float(r['diferenca_pct_sobre_atacado'])<0),
            'series_defasadas_4m':sum(int(r['serie_defasada_4m']) for r in series),
            'alertas_por_tipo':dict(Counter(r['tipo'] for r in alertas)),
            'sqlite_integrity':integrity,'tabelas_sqlite':len(tables),
            'falhas':violations,'advertencia':'Validação estrutural, não valida preços, metodologia, representatividade ou licença.'
        }

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--json-output')
    args=ap.parse_args()
    result=audit(args.input)
    result_json=json.dumps(result,ensure_ascii=False,indent=2)
    if args.json_output:Path(args.json_output).write_text(result_json,encoding='utf-8')
    print(result_json)
    raise SystemExit(0 if result['resultado']=='APROVADO_ESTRUTURALMENTE' else 1)
