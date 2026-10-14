"""Consulta metadados FAO FPMA por UUID para classificar price_type e source.
Não altera preços, não declara licença ou aptidão comercial. Executar no Colab.
Uso: python enriquecer_fao_v7.py /caminho/resultados_agro_v6.zip /dir/saida
"""
from __future__ import annotations
import io, json, sys, time, sqlite3, zipfile
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
import requests

API='https://fpma.fao.org/giews/v4/global/price_module/api/v1/FpmaSerie/'
ALLOWED_HOST='fpma.fao.org'


def metadata_label(v):
    if isinstance(v,str):return v.strip()
    if isinstance(v,dict):
        for k in ('name','price_type_name','description','label','display_name','price_type','type'):
            if k in v and isinstance(v[k],str):return v[k].strip()
        return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list): return ';'.join(metadata_label(x) for x in v)
    return '' if v is None else str(v)


def collect(session, timeout=45):
    url=API+'?iso3_country_codes=BRA&page_size=100'
    results=[];visited=set();pages=0
    while url and pages<20:
        addr=urlparse(url)
        if addr.scheme!='https' or addr.netloc!=ALLOWED_HOST:raise RuntimeError('URL de paginação fora do domínio permitido')
        if url in visited:raise RuntimeError('Ciclo na paginação')
        visited.add(url)
        r=session.get(url,timeout=timeout);r.raise_for_status();payload=r.json()
        if not isinstance(payload,dict) or not isinstance(payload.get('results'),list):
            raise ValueError('Formato FpmaSerie inesperado; revisar manualmente')
        results.extend(payload['results'])
        url=payload.get('next') or None;pages+=1
        time.sleep(.4)
    if url: raise RuntimeError('Mais de 20 páginas; interrompido por segurança')
    return results,pages


def enrich(zip_path,output_path):
    out=Path(output_path);out.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(zip_path) as z:
        df=pd.read_csv(io.BytesIO(z.read('fao_catalogo_resolvido_v6.csv')))
    session=requests.Session();session.headers.update({'User-Agent':'AgroResearchCatalog/0.7 (educational; contact fpma@fao.org)'})
    candidates,pages=collect(session)
    found={x['uuid']:x for x in candidates if isinstance(x,dict) and isinstance(x.get('uuid'),str)}
    outrows=[]
    for _,row in df.iterrows():
        uid=row.uuid;x=found.get(uid,{})
        pt=x.get('price_type', x.get('price_types', x.get('price_type_name')))
        src=x.get('source', x.get('sources', x.get('source_name')))
        pt_label=metadata_label(pt)
        src_label=metadata_label(src)
        # Não infere atacado ou varejo de unidades nem de market_type.
        canon=pt_label.upper() if pt_label else ''
        if 'WHOLESALE' in canon: typ='ATACADO'
        elif 'RETAIL' in canon: typ='VAREJO'
        elif 'FARMGATE' in canon or 'PRODUCER' in canon:typ='PRODUTOR'
        else:typ='NAO_CLASSIFICADO'
        outrows.append({'uuid':uid,'produto':row.produto_resolvido,'mercado':row.mercado_resolvido,
           'preco_tipo_campo':pt_label,'classificacao_preco':typ,
           'origem_fonte_campo':src_label,'market_type_campo':metadata_label(x.get('market_type')),
           'metadado_presente':bool(x),'status':'MATCH_UUID' if x else 'UUID_NAO_ENCONTRADO',
           'licenca_redistribuicao':'PENDENTE_VERIFICACAO',
           'raw_serie_json':json.dumps(x,ensure_ascii=False,default=str) if x else ''})
    res=pd.DataFrame(outrows)
    res.to_csv(out/'fao_tipos_preco_e_fontes_v7.csv',index=False)
    (out/'fao_series_metadata_raw_v7.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding='utf-8')
    if (out/'agro_integrado_v7.sqlite').exists():
        con=sqlite3.connect(out/'agro_integrado_v7.sqlite');res.to_sql('fao_metadados_tipo_preco',con,if_exists='replace',index=False)
        con.commit();con.close()
    metrics={'n_paginas':pages,'fao_series_respondidas':len(candidates),'faos_series_pareadas':int(res.metadado_presente.sum()),
      'fao_series_nao_pareadas':int((~res.metadado_presente).sum()),
      'tipo_preco':res.classificacao_preco.value_counts().to_dict(),
      'aviso':'Metadados não comprovam licença; não transformar automaticamente em cotação ao produtor.'}
    (out/'resumo_metadados_fao_v7.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metrics,ensure_ascii=False,indent=2))
    return metrics
if __name__=='__main__': enrich(sys.argv[1],sys.argv[2])
