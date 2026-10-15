#!/usr/bin/env python3
# Pipeline Agro V8: consolidação reprodutível dos resultados da V7.
# Requisitos: somente biblioteca-padrão do Python.
from __future__ import annotations
import argparse, csv, io, json, os, shutil, sqlite3, statistics, zipfile
from collections import defaultdict, Counter
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

BASELINE_MANIFEST = Path(__file__).resolve().parents[2] / 'docs' / 'baseline_v8.json'
EXPECTED = ['fao_precos_auditados_v7.csv','fao_tipos_preco_e_fontes_v7.csv','fao_series_metadata_raw_v7.json','fao_cobertura_series_v7.csv','resumo_metadados_fao_v7.json','resumo_qualidade_v7.json']
PRODUTO = {
 'Wheat (flour)': 'Farinha de trigo',
 'Rice (milled, fine long-grain, type 1)': 'Arroz beneficiado tipo 1',
 'Beans (black)': 'Feijão-preto',
 'Maize (yellow)': 'Milho amarelo',
 'Wheat': 'Trigo em grão',
}
REGIAO = {'Federal District': 'Distrito Federal'}
PAIR_FIELDS = ['produto','regiao','data','uuid_atacado','uuid_varejo','atacado_brl_kg',
               'varejo_brl_kg','diferenca_brl_kg','diferenca_pct_sobre_atacado',
               'status_comparacao','nota']
STATS_FIELDS = ['produto','ano','n_pares','mediana_diferencial_pct',
                'media_diferencial_pct','min_diferencial_pct','max_diferencial_pct','interpretacao']
ALERT_FIELDS = ['tipo','uuid','produto','regiao','data','detalhe']
SQLITE_INTEGER_FIELDS = {
    'fao_precos_normalizados_v8': {'meses_base_2020','meses_defasagem_serie','serie_defasada_4m','flag_outlier'},
    'fao_series_classificadas_v8': {'campos_auxiliares_divergentes','observacoes','meses_ausentes_internos',
                                   'defasagem_meses','serie_defasada_4m','meses_base_2020'},
    'fao_pares_atacado_varejo_v8': set(),
    'fao_resumo_diferenciais_v8': {'ano','n_pares'},
    'alertas_qualidade_v8': set(),
}
SQLITE_KEYS = {
    'fao_precos_normalizados_v8': ('uuid','data'),
    'fao_series_classificadas_v8': ('uuid',),
    'fao_pares_atacado_varejo_v8': ('produto','regiao','data'),
    'fao_resumo_diferenciais_v8': ('produto','ano'),
    'alertas_qualidade_v8': ('tipo','uuid','data'),
}

def dec(x):
    try: return Decimal(str(x).strip())
    except (InvalidOperation, ValueError): return None

def fix(x, digits=6):
    if x is None: return ''
    return str(x.quantize(Decimal(10) ** -digits, rounding=ROUND_HALF_UP))

def read_csv(zf, name):
    with zf.open(name) as file:
        return list(csv.DictReader(io.TextIOWrapper(file, encoding='utf-8-sig',newline='')))

def write_csv(path,rows,fields):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore', delimiter=',')
        w.writeheader();w.writerows(rows)

def baseline_reference():
    return date.fromisoformat(json.loads(BASELINE_MANIFEST.read_text(encoding='utf-8'))['referencia'])

def monthdist(s, reference_date):
    dt=date.fromisoformat(s[:10]);return (reference_date.year-dt.year)*12+reference_date.month-dt.month

def months_between(st,en):
    a=date.fromisoformat(st[:10]);b=date.fromisoformat(en[:10]);return (b.year-a.year)*12+b.month-a.month+1

def read_bytes_zip(zf,name):
    with zf.open(name) as f:return f.read()

def main(zip_path, out_dir, reference_date=None):
    if reference_date is None: reference_date=baseline_reference()
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        files={Path(x).name:x for x in z.namelist() if not x.endswith('/')}
        miss=[x for x in EXPECTED if x not in files]
        if miss:raise ValueError('Arquivo ZIP não contém: '+', '.join(miss))
        prices=read_csv(z, files['fao_precos_auditados_v7.csv'])
        metas=read_csv(z, files['fao_tipos_preco_e_fontes_v7.csv'])
        cobertura=read_csv(z, files['fao_cobertura_series_v7.csv'])
        dbname=files.get('agro_integrado_v7.sqlite')
        if dbname:
            with open(out/'agro_integrado_v8.sqlite','wb') as w:w.write(read_bytes_zip(z,dbname))
    byid={r['uuid']:r for r in metas}
    bycoverage={r['uuid']:r for r in cobertura}
    if not prices or not metas: raise ValueError('Preços e metadados de séries são obrigatórios')
    if len(byid)!=len(metas): raise ValueError('UUID duplicado nos metadados das séries')
    if len(bycoverage)!=len(cobertura): raise ValueError('UUID duplicado na cobertura das séries')
    if len({(r['uuid'],r['data']) for r in prices})!=len(prices):raise ValueError('Duplicatas (uuid,data) detectadas')
    missing_meta={r['uuid'] for r in prices}-byid.keys()
    missing_coverage=set(byid)-bycoverage.keys()
    if missing_meta: raise ValueError('Séries sem metadados: '+', '.join(sorted(missing_meta)))
    if missing_coverage: raise ValueError('Séries sem cobertura: '+', '.join(sorted(missing_coverage)))
    # Base 2020 média aritmética mensal para índices NOMINAIS; não representa inflação real.
    base2020=defaultdict(list)
    for r in prices:
        x=dec(r['preco_brl_por_kg_exato'])
        if r['data'].startswith('2020-') and x is not None and x>0 and r['flag_salto_isolado']!='True':base2020[r['uuid']].append(x)
    base2020={k: (sum(v)/Decimal(len(v))) for k,v in base2020.items() if len(v)>=6}

    normalized=[]
    for r in prices:
        uuid=r['uuid']; m=byid[uuid]; cov=bycoverage[uuid]
        original=dec(r['valor_brl_por_unidade_original']);kg=dec(r['quantidade_kg_unidade_original'])
        perkg=original/kg if original is not None and kg and kg>0 else None
        flag=(r['flag_salto_isolado']=='True')
        status='REVISAR_OUTLIER' if flag else ('OK' if perkg is not None and perkg>0 else 'SEM_PRECO_VALIDO')
        b=base2020.get(uuid)
        rawmeta=json.loads(m['raw_serie_json'])
        row={
            'uuid':uuid,'data':r['data'],'pais':'BRA',
            'produto':PRODUTO.get(r['commodity_nome'],r['commodity_nome']),
            'produto_fao':r['commodity_nome'],'regiao':REGIAO.get(r['mercado_nome'],r['mercado_nome']),
            'commodity_id':r['commodity_id'],'mercado_id':r['market_id'],
            'tipo_preco':m['classificacao_preco'],'preco_tipo_fao':m['preco_tipo_campo'],
            'tipo_mercado_auxiliar_fao':m['market_type_campo'],
            'fonte_primaria':rawmeta.get('source_name',''),
            'fonte_distribuidora':'FAO FPMA',
            'moeda':'BRL','unidade_original':r['unidade_original'],
            'massa_kg_unidade_original':fix(kg,3),
            'valor_original_brl':fix(original,4),
            'preco_brl_kg':fix(perkg,6),
            'equivalente_brl_60kg_APENAS_MATEMATICO':fix(perkg*Decimal(60) if perkg is not None else None,4),
            'indice_nominal_2020_100':fix((perkg/b*Decimal(100)) if b and perkg else None,3),
            'meses_base_2020':len([v for v in prices if v['uuid']==uuid and v['data'].startswith('2020-')]),
            'status_qualidade':status,'flag_outlier':int(flag),
            'data_ultima_serie':cov['data_fim'],
            'meses_defasagem_serie':monthdist(cov['data_fim'],reference_date),
            'serie_defasada_4m':int(monthdist(cov['data_fim'],reference_date)>=4),
            'status_licenca':'REVISAR_TERMOS_FAO_E_FONTE_TERCEIROS',
            'url_origem_api':'https://fpma.fao.org/giews/v4/global/price_module/api/v1/FpmaSeriePrice/',
        }
        normalized.append(row)
    cols_prices=list(normalized[0]);write_csv(out/'fao_precos_normalizados_v8.csv',normalized,cols_prices)

    serie=[]
    for uuid,meta in sorted(byid.items(),key=lambda x:(x[1]['produto'],x[1]['mercado'],x[1]['classificacao_preco'])):
        c=bycoverage[uuid];raw=json.loads(meta['raw_serie_json'])
        serie.append({'uuid':uuid,'produto':PRODUTO.get(meta['produto'],meta['produto']),
          'regiao':REGIAO.get(meta['mercado'],meta['mercado']),
          'tipo_preco':meta['classificacao_preco'],'price_type_fao':meta['preco_tipo_campo'],
          'market_type_auxiliar_fao':meta['market_type_campo'],
          'campos_auxiliares_divergentes':int((meta['preco_tipo_campo']=='WHOLESALE' and meta['market_type_campo']=='Retail')),
          'fonte_primaria':raw.get('source_name',''),'fonte_url':raw.get('source_url',''),
          'codigo_produto_fao':raw.get('commodity_code',''),
          'unidade_original':c['unidade_original'], 'data_inicio':c['data_inicio'], 'data_fim':c['data_fim'],
          'observacoes':int(c['observacoes']),'meses_ausentes_internos':int(c['meses_ausentes_internos']),
          'cobertura_pct':c['cobertura_pct'],'defasagem_meses':monthdist(c['data_fim'],reference_date),
          'serie_defasada_4m':int(monthdist(c['data_fim'],reference_date)>=4),
          'meses_base_2020':sum(1 for r in prices if r['uuid']==uuid and r['data'].startswith('2020-')),
          'licenca':'FAO_CONDICIONAL_VERIFICAR_TERCEIROS',
          'observacoes_uso':'Preços de comercialização, não representam preços ao produtor'})
    cols_series=list(serie[0]);write_csv(out/'fao_series_classificadas_v8.csv',serie,cols_series)

    mapping=defaultdict(dict)
    for r in normalized:
        mapping[(r['produto'],r['regiao'],r['data'])][r['tipo_preco']]=r
    paired=[]
    for (prod,market,dt), types in sorted(mapping.items()):
        if not ('ATACADO' in types and 'VAREJO' in types):continue
        a,b=types['ATACADO'],types['VAREJO']
        va,vb=dec(a['preco_brl_kg']),dec(b['preco_brl_kg'])
        good=(a['status_qualidade']=='OK' and b['status_qualidade']=='OK' and va is not None and va>0)
        paired.append({'produto':prod,'regiao':market,'data':dt,
           'uuid_atacado':a['uuid'],'uuid_varejo':b['uuid'],
           'atacado_brl_kg':a['preco_brl_kg'],'varejo_brl_kg':b['preco_brl_kg'],
           'diferenca_brl_kg':fix(vb-va,6) if va is not None and vb is not None else '',
           'diferenca_pct_sobre_atacado':fix((vb/va-1)*100,3) if va and vb else '',
           'status_comparacao':'ANOMALIA_NAO_USAR_EM_AGREGADOS' if not good else 'AMOSTRA_COMPARAVEL',
           'nota':'Diferencial de preços; NÃO é margem de lucro, nem preço na fazenda'})
    cols_paired=list(paired[0]) if paired else PAIR_FIELDS
    write_csv(out/'fao_pares_atacado_varejo_v8.csv',paired,cols_paired)
    # Estatísticas somente da amostra pareada, sem inferência nacional e sem outliers.
    sam=defaultdict(list)
    for p in paired:
        if p['status_comparacao']=='AMOSTRA_COMPARAVEL':sam[(p['produto'],p['data'][:4])].append(float(p['diferenca_pct_sobre_atacado']))
    stats=[]
    for (prod,yr),v in sorted(sam.items()):
        stats.append({'produto':prod,'ano':int(yr),'n_pares':len(v),
         'mediana_diferencial_pct':round(statistics.median(v),2),
         'media_diferencial_pct':round(statistics.mean(v),2),
         'min_diferencial_pct':round(min(v),2),'max_diferencial_pct':round(max(v),2),
         'interpretacao':'Diferença varejo/atacado em amostra regional; não é margem nem média nacional'})
    cols_stats=list(stats[0]) if stats else STATS_FIELDS
    write_csv(out/'fao_resumo_diferenciais_v8.csv',stats,cols_stats)

    alert=[]
    for s in serie:
        if s['serie_defasada_4m']:
            alert.append({'tipo':'SERIE_DEFASADA','uuid':s['uuid'],'produto':s['produto'],
                          'regiao':s['regiao'],'data':s['data_fim'],'detalhe':str(s['defasagem_meses'])+' meses de defasagem'})
        if s['campos_auxiliares_divergentes']:
            alert.append({'tipo':'METADADOS_MERCADO_TIPO','uuid':s['uuid'],'produto':s['produto'],
                          'regiao':s['regiao'],'data':'','detalhe':'price_type=WHOLESALE; market_type=Retail (campos distintos)'})
        if int(s['meses_ausentes_internos'])>0:
            alert.append({'tipo':'LACUNAS_INTERNAS','uuid':s['uuid'],'produto':s['produto'],'regiao':s['regiao'],
                          'data':'','detalhe':str(s['meses_ausentes_internos'])+' meses sem observação dentro da cobertura'})
    for p in normalized:
        if p['flag_outlier']:
            alert.append({'tipo':'OUTLIER_SUSPEITO','uuid':p['uuid'],'produto':p['produto'],
                          'regiao':p['regiao'],'data':p['data'],'detalhe':'Manter valor original e investigar na fonte'})
    cols_alert=list(alert[0]) if alert else ALERT_FIELDS
    write_csv(out/'alertas_qualidade_v8.csv',alert,cols_alert)

    # Banco V7 herdado + cinco tabelas V8, preservando origem e versão legada.
    db=out/'agro_integrado_v8.sqlite'
    if not db.exists(): sqlite3.connect(db).close()
    with sqlite3.connect(db) as cn:
        tables = [
            ('fao_precos_normalizados_v8',normalized,cols_prices),
            ('fao_series_classificadas_v8',serie,cols_series),
            ('fao_pares_atacado_varejo_v8',paired,cols_paired),
            ('fao_resumo_diferenciais_v8',stats,cols_stats),
            ('alertas_qualidade_v8',alert,cols_alert),
        ]
        for name,entries,cols in tables:
            numeric=SQLITE_INTEGER_FIELDS[name]
            definitions=[f'"{col}" {"INTEGER" if col in numeric else "TEXT"}' for col in cols]
            key=','.join(f'"{col}"' for col in SQLITE_KEYS[name])
            cn.execute(f'DROP TABLE IF EXISTS "{name}"')
            cn.execute(f'CREATE TABLE "{name}" ({",".join(definitions)}, PRIMARY KEY ({key})) WITHOUT ROWID')
            fields=','.join(f'"{col}"' for col in cols)
            placeholders=','.join('?' for _ in cols)
            cn.executemany(f'INSERT INTO "{name}" ({fields}) VALUES ({placeholders})',
                           [[int(row[col]) if col in numeric else str(row[col]) for col in cols]
                            for row in entries])
        cn.execute('CREATE INDEX IF NOT EXISTS idx_precos_v8_tipo ON fao_precos_normalizados_v8(tipo_preco,produto,regiao,data)')
    r={
      'referencia':reference_date.isoformat(),'input':Path(zip_path).name,
      'series':len(serie),'observacoes':len(normalized),'preco_atacado':sum(x['tipo_preco']=='ATACADO' for x in normalized),
      'preco_varejo':sum(x['tipo_preco']=='VAREJO' for x in normalized),
      'pares_completos':len(paired),'pares_sem_anomalias':sum(p['status_comparacao']=='AMOSTRA_COMPARAVEL' for p in paired),
      'origens':dict(Counter(s['fonte_primaria'] for s in serie)),
      'series_defasadas_4m':sum(s['serie_defasada_4m'] for s in serie),
      'series_com_campo_auxiliar_Retail_para_atacado':sum(s['campos_auxiliares_divergentes'] for s in serie),
      'meses_faltantes_dentro_das_series':sum(s['meses_ausentes_internos'] for s in serie),
      'outliers_suspeitos':sum(p['flag_outlier'] for p in normalized),
      'produtos':dict(Counter(s['produto'] for s in serie)),
      'intervalo':[min(p['data'] for p in normalized),max(p['data'] for p in normalized)],
      'criterios':['Moeda BRL e unidade kg','Tipo de preço por price_type e não market_type',
         'Preço original preservado','Índice nominal base média 2020=100 por série (>=6 meses em 2020)',
         'Diferencial sem outlier, não equivale a lucro','Séries com >=4 meses de defasagem sinalizadas',
         'Licença deve ser verificada para redistribuição/comercialização']}
    (out/'resumo_v8.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
    # Auditoria de invariantes de integridade.
    with sqlite3.connect(db) as cn:
        for table, expected_count in [('fao_precos_normalizados_v8',len(normalized)),
                                      ('fao_pares_atacado_varejo_v8',len(paired))]:
            count=cn.execute('select count(*) from '+table).fetchone()[0]
            if count!=expected_count: raise RuntimeError(f'{table}: {count} linhas no banco; {expected_count} geradas')
        if cn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise RuntimeError('Falha na integridade do SQLite V8')
    return r

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('zip_input');ap.add_argument('--output',default='resultados_agro_v8')
    ap.add_argument('--reference-date',type=date.fromisoformat,default=None,metavar='YYYY-MM-DD',
                    help='Data para calcular defasagem; padrão: referência em docs/baseline_v8.json')
    args=ap.parse_args();print(json.dumps(main(args.zip_input,args.output,args.reference_date),ensure_ascii=False,indent=2))
