#!/usr/bin/env python3
"""Agro V6 — auditoria e coleta explícita da FAO FPMA a partir do ZIP V5.

Uso Colab: python pipeline_agro_v6.py --input resultados_agro_v5.zip --out resultados_agro_v6
Diagnóstico sem rede: acrescentar --offline.

Distingue metadados de preços observados; nenhuma consulta online simulada.
Não desativa TLS, não presume nomes de produtos e não converte unidades sem metadados.
"""
import argparse, io, json, math, re, sqlite3, sys, time, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

FPMA = 'https://fpma.fao.org/giews/v4/global/price_module/api/v1/'
IPEA = "https://www.ipeadata.gov.br/api/odata4/Metadados('ABATE_ABPEAV')"
SICOR = 'https://olinda.bcb.gov.br/olinda/servico/SICOR/versao/v2/odata/$metadata'
EXPECTED = {'manifesto_v5.json','observacoes_staging_v5.csv','fao_candidatas_brasil_v5.csv'}
PRICE_COLUMNS = ['uuid','pais','commodity_id','commodity_nome','market_id','mercado_nome',
                 'data','valor_brl_por_unidade_original','valor_brl_por_kg','moeda','unidade_original',
                 'conversion_factor_api','periodicidade','tipo_preco','qualidade','url_fonte']
AUDIT_COLUMNS = ['fonte','etapa','identificador','status','http_status','linhas','detalhe','url','hora_utc']
IPEA_DOC_META = {'SERCODIGO':'ABATE_ABPEAV','SERNOME':'Abate - aves - peso das carcaças',
                  'PERNOME':'Anual','UNINOME':'Tonelada','MULNOME':'mil',
                  'FNTNOME':'IBGE/Coagro', 'proveniencia':'documentacao_publica_verificada_2026-10-14',
                  'url':IPEA}


def ts(): return datetime.now(timezone.utc).isoformat()
def dump(obj, path): Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def read_csv_from_zip(z, name): return pd.read_csv(io.BytesIO(z.read(name)),dtype=str,keep_default_na=False,encoding='utf-8-sig')
def s(x): return '' if x is None else str(x).strip()
def validfloat(value):
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None


def prepare_v5(source, out):
    with zipfile.ZipFile(source) as z:
        names=set(z.namelist()); missing=EXPECTED-names
        if missing: raise ValueError('ZIP V5 inválido; faltam: '+', '.join(sorted(missing)))
        manifesto=json.loads(z.read('manifesto_v5.json').decode('utf-8-sig'))
        raw=read_csv_from_zip(z,'observacoes_staging_v5.csv')
        fao=read_csv_from_zip(z,'fao_candidatas_brasil_v5.csv')
    if len(raw)!=369: print(f'AVISO: staging contém {len(raw)} registros; não presume contagem de V5',file=sys.stderr)
    if not {'source_id','valor','periodo','situacao_qualidade'}.issubset(raw.columns):
        raise ValueError('CSV de observações não contém as colunas esperadas')
    if not {'uuid','pais','commodity_id','market_id','periodicidade','unit','currency'}.issubset(fao.columns):
        raise ValueError('CSV de séries FAO incompleto')
    if fao['uuid'].duplicated().any():
        raise ValueError('UUIDs repetidos no catálogo FAO; revisar origem antes de extrair')
    for col in ('produto_resolvido','mercado_resolvido','status_resolucao_v6'):
        if col not in fao: fao[col]=''
    out.mkdir(parents=True,exist_ok=True)
    dump(manifesto,out/'manifesto_origem_v5.json')
    raw.to_csv(out/'observacoes_staging_importadas_v6.csv',index=False,encoding='utf-8-sig')
    fao.to_csv(out/'fao_candidatas_input_v6.csv',index=False,encoding='utf-8-sig')
    enrich_ipea(raw,out,IPEA_DOC_META,auth='DOCUMENTACAO_PUBLICA_NAO_REVALIDADA_NA_EXECUCAO')
    return raw,fao,manifesto


def enrich_ipea(raw,out,meta,auth):
    ip=raw[raw.source_id=='AG018'].copy()
    if ip.empty: return 0
    name=s(meta.get('SERNOME')); u=s(meta.get('UNINOME')); mul=s(meta.get('MULNOME'))
    if s(meta.get('SERCODIGO'))!='ABATE_ABPEAV' or not u or not mul:
        raise ValueError('Metadados IPEADATA incompatíveis com ABATE_ABPEAV')
    ip['serie_codigo']='ABATE_ABPEAV';ip['serie_nome']=name; ip['unidade_basica']=u
    ip['multiplicador_literal']=mul;ip['unidade_original']=f'{mul} {u.lower()}s' if u.lower()=='tonelada' else f'{mul} {u}'
    ip['valor_original']=pd.to_numeric(ip.valor,errors='coerce')
    ip['valor_em_toneladas']=ip['valor_original']*1000 if mul.lower()=='mil' and u.lower()=='tonelada' else float('nan')
    ip['qualidade_metadado']=auth
    ip['situacao_qualidade_v6']='SERIE_IDENTIFICADA_AMOSTRAL_NAO_AUDITADA_HISTORICAMENTE'
    ip['url_metadados']=IPEA
    ip.to_csv(out/'ipeadata_abate_aves_serie_v6.csv',index=False,encoding='utf-8-sig')
    dump({'serie':meta,'status_metadados':auth,'registros':len(ip)},out/'ipeadata_metadados_v6.json')
    return len(ip)


def as_obj(value):
    if isinstance(value,dict) and 'value' in value and isinstance(value['value'],list):
        value=value['value'][0] if value['value'] else {}
    if isinstance(value,dict) and isinstance(value.get('results'),list):
        value=value['results'][0] if value['results'] else {}
    if isinstance(value,list):value=value[0] if value else {}
    return value if isinstance(value,dict) else {}


def label(obj,kind):
    # Somente rótulos explícitos, nunca converte IDs numéricos para suposições.
    pref=['name','commodity_name','market_name','name_en','en_name','label','description']
    for k in pref:
        x=obj.get(k)
        if isinstance(x,str) and x.strip() and not x.strip().isdigit():return x.strip()
    # API eventualmente devolve traduções aninhadas
    for k in ['translations','name_translations']:
        d=obj.get(k)
        if isinstance(d,dict):
            for lang in ['en','eng','pt','pt-br']:
                x=d.get(lang)
                if isinstance(x,str) and x.strip():return x.strip()
    return ''


class HttpClient:
    def __init__(self,pause,timeout,audit):
        import requests
        self.session=requests.Session()
        self.session.headers.update({'Accept':'application/json, application/xml;q=0.8, */*;q=0.5',
                                     'User-Agent':'AgroOpenDataAudit/0.6 (research; read-only)'})
        self.pause=max(0.35,pause);self.timeout=timeout;self.audit=audit
    def get(self,url,params=None,kind='API',id=''):
        import requests
        response=None
        for attempt in range(3):
            time.sleep(self.pause)
            try:
                response=self.session.get(url,params=params,timeout=self.timeout,allow_redirects=True)
                if response.status_code in (429,500,502,503,504) and attempt<2:
                    wait= min(10, max(1, 2**attempt))
                    if response.status_code==429:
                        try:wait=min(20,max(wait,float(response.headers.get('Retry-After','0'))))
                        except (ValueError,TypeError):pass
                    time.sleep(wait);continue
                response.raise_for_status()
                return response
            except (requests.exceptions.Timeout,requests.exceptions.ConnectionError) as e:
                if attempt>=2:raise
                time.sleep(2**attempt)
        response.raise_for_status()
    def log(self,fonte,etapa,identifier,status,detail='',n=0,response=None,url=''):
        self.audit.append({'fonte':fonte,'etapa':etapa,'identificador':identifier,'status':status,
            'http_status':getattr(response,'status_code',''),'linhas':int(n),
            'detalhe':s(detail)[:500],'url':getattr(response,'url',url),'hora_utc':ts()})


def fetch_lookup(client,kind,ident):
    url=f'{FPMA}{kind}/{ident}/'; response=None
    try:
        response=client.get(url,kind=kind,id=ident); obj=as_obj(response.json()); name=label(obj,kind)
        client.log('FAO_FPMA',f'lookup_{kind}',ident,'METADADO_VALIDO' if name else 'ROTULO_AUSENTE',
                   f'keys={list(obj.keys())[:15]}',1 if obj else 0,response)
        return name,obj
    except Exception as e:
        client.log('FAO_FPMA',f'lookup_{kind}',ident,'FALHA',repr(e),response=response,url=url)
        return '',{}


def extract_price_rows(payload, batch, rowmap, response, client):
    if isinstance(payload,list): records=payload
    elif isinstance(payload,dict) and isinstance(payload.get('results'),list): records=payload['results']
    else: raise ValueError('Formato FpmaSeriePrice não reconhecido')
    out=[];seen=set()
    for r in records:
        uuid=s(r.get('uuid'))
        if uuid not in rowmap: continue
        orig=rowmap[uuid]; seen.add(uuid)
        for p in r.get('datapoints',[]):
            if not isinstance(p,dict):continue
            v=validfloat(p.get('price_value'))
            date=s(p.get('date'))
            if v is None or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):continue
            factor=validfloat(p.get('conversion_factor'))
            # Aplicar fator só se fornecido pelo próprio ponto e unidade for massa.
            unit=s(orig['unit']);mass_unit=bool(re.fullmatch(r'(?i)(kg|\d+\s*kg|ton|tons|tonne|tonnes|t)',unit))
            norm= v*factor if factor is not None and factor>0 and mass_unit else None
            names=bool(orig['produto_resolvido'] and orig['mercado_resolvido'])
            status='METADADOS_RESOLVIDOS_REVISAR_LICENCA_TIPO' if names else 'PENDENTE_ROTULOS_REFERENCIA'
            out.append({'uuid':uuid,'pais':orig['pais'],'commodity_id':orig['commodity_id'],
                'commodity_nome':orig['produto_resolvido'],'market_id':orig['market_id'],
                'mercado_nome':orig['mercado_resolvido'],'data':date,
                'valor_brl_por_unidade_original':v,'valor_brl_por_kg':norm,
                'moeda':orig['currency'],'unidade_original':unit,'conversion_factor_api':factor,
                'periodicidade':s(p.get('periodicity',orig['periodicidade'])),
                'tipo_preco':'NAO_CONFIRMADO','qualidade':status,'url_fonte':response.url})
    return out,seen


def fao_prices(client,fao,out,batch_size=3,max_series=31):
    fao=fao.iloc[:max_series].copy().fillna('')
    commodities={}; markets={}; lookup_payload={'commodity':{},'market':{}}
    for ident in sorted(fao.commodity_id.unique()):
        name,obj=fetch_lookup(client,'Commodity',ident);commodities[ident]=name;lookup_payload['commodity'][ident]=obj
    for ident in sorted(fao.market_id.unique()):
        name,obj=fetch_lookup(client,'Market',ident);markets[ident]=name;lookup_payload['market'][ident]=obj
    fao['produto_resolvido']=fao.commodity_id.map(commodities).fillna('')
    fao['mercado_resolvido']=fao.market_id.map(markets).fillna('')
    fao['status_resolucao_v6']=fao.apply(lambda r:'RESOLVIDO' if r.produto_resolvido and r.mercado_resolvido else 'PENDENTE_LOOKUP',axis=1)
    fao.to_csv(out/'fao_catalogo_resolvido_v6.csv',index=False,encoding='utf-8-sig')
    dump(lookup_payload,out/'fao_metadados_brutos_v6.json')
    rowmap={r['uuid']:r for r in fao.to_dict('records')}
    uuids=[r.uuid for r in fao.itertuples() if s(r.periodicidade).lower()=='monthly']
    rows=[];done=set()
    def call_batch(ids):
        url=FPMA+'FpmaSeriePrice/';resp=None
        try:
            resp=client.get(url,params={'uuid__in':','.join(ids),'periodicity':'monthly'})
            rec,got=extract_price_rows(resp.json(),ids,rowmap,resp,client)
            rows.extend(rec);done.update(got)
            client.log('FAO_FPMA','precos',','.join(ids),'OBSERVACOES_VALIDAS' if rec else 'SEM_OBSERVACOES',
                       f'UUID retornados: {len(got)} de {len(ids)}',len(rec),resp)
            return True
        except Exception as e:
            client.log('FAO_FPMA','precos',','.join(ids),'FALHA',repr(e),response=resp,url=url)
            return False
    for pos in range(0,len(uuids),batch_size):
        batch=uuids[pos:pos+batch_size]
        ok=call_batch(batch)
        if not ok and len(batch)>1:
            for single in batch:call_batch([single])
    # Reconsultar UUIDs omitidos quando o servidor devolver apenas parte do lote.
    for single in uuids:
        if single not in done: call_batch([single])
    prices=pd.DataFrame(rows,columns=PRICE_COLUMNS)
    duplicate_count=int(prices.duplicated(['uuid','data','periodicidade']).sum()) if len(prices) else 0
    prices=prices.drop_duplicates(['uuid','data','periodicidade'],keep='first')
    prices.to_csv(out/'fao_precos_mensais_v6.csv',index=False,encoding='utf-8-sig')
    stats={'uuid_catalogados':len(fao),'uuid_com_precos':prices.uuid.nunique() if len(prices) else 0,
           'valores':len(prices),'duplicatas_descartadas':duplicate_count,
           'series_resolvidas':int((fao.status_resolucao_v6=='RESOLVIDO').sum()),
           'uuid_sem_preco':sorted(set(uuids)-set(prices.uuid.tolist())) if len(prices) else uuids}
    dump(stats,out/'sumario_fao_v6.json')
    return prices,fao,stats


def query_ipea(client, raw, out):
    response=None
    try:
        response=client.get(IPEA);meta=as_obj(response.json())
        if meta.get('SERCODIGO')!='ABATE_ABPEAV' or not meta.get('UNINOME') or not meta.get('MULNOME'):
            raise ValueError('Metadados IPEADATA sem unidade/multiplicador esperados')
        n=enrich_ipea(raw,out,meta,'METADADO_OFICIAL_REVALIDADO_NESTA_EXECUCAO')
        client.log('IPEADATA','metadados','ABATE_ABPEAV','METADADO_VALIDO',
                   f"{meta.get('SERNOME')}; {meta.get('MULNOME')} {meta.get('UNINOME')}",n,response)
    except Exception as e:
        client.log('IPEADATA','metadados','ABATE_ABPEAV','FALHA_METADADOS_LIVE_USOU_REFERENCIA_DOCUMENTAL',
                   repr(e),response=response,url=IPEA)


def query_sicor(client,out):
    response=None
    try:
        response=client.get(SICOR)
        root=ET.fromstring(response.content)
        sets=[]
        for node in root.iter():
            if node.tag.split('}')[-1]=='EntitySet':
                sets.append({'nome':node.attrib.get('Name',''), 'tipo':node.attrib.get('EntityType','')})
        pd.DataFrame(sets,columns=['nome','tipo']).to_csv(out/'sicor_entidades_odata_v6.csv',index=False,encoding='utf-8-sig')
        client.log('SICOR','metadata','OData','METADADOS_VALIDOS' if sets else 'SEM_ENTITY_SET',
                   'Não comprova acesso aos registros do crédito rural',len(sets),response)
        # Não presumir que entidade pesquisável devolva dados nem fazer consulta pesada.
    except Exception as e:
        client.log('SICOR','metadata','OData','FALHA',repr(e),response=response,url=SICOR)


def finalize(out,raw,prices,manifesto,audit,online):
    df=pd.DataFrame(audit,columns=AUDIT_COLUMNS)
    df.to_csv(out/'auditoria_online_v6.csv',index=False,encoding='utf-8-sig')
    dump(df.to_dict('records'),out/'auditoria_online_v6.json')
    report={'gerado_utc':ts(),'coleta_online_executada':online,
            'staging_v5_importado':len(raw),'ibge_aprovadas_amostra':int((raw.situacao_qualidade=='APROVADO_AMOSTRA').sum()),
            'ipeadata_identificados':int((raw.source_id=='AG018').sum()),
            'fao_precos_extraidos_online':len(prices),
            'fao_series_com_preco':prices.uuid.nunique() if len(prices) else 0,
            'falhas_registradas':int(df.status.str.startswith(('FALHA','ERRO')).sum()) if len(df) else 0,
            'observacao':'Dados FAO ficam em revisão de tipo de preço/licença, mesmo com valores e rótulos.'}
    dump(report,out/'resumo_v6.json')
    with sqlite3.connect(out/'agro_v6.sqlite') as con:
        raw.to_sql('staging_v5_importado',con,index=False,if_exists='replace')
        prices.to_sql('fao_precos_staging',con,index=False,if_exists='replace')
        df.to_sql('auditoria_online',con,index=False,if_exists='replace')
        ip=pd.read_csv(out/'ipeadata_abate_aves_serie_v6.csv',dtype=str,keep_default_na=False)
        ip.to_sql('ipeadata_abate_aves_staging',con,index=False,if_exists='replace')
        con.execute('CREATE INDEX IF NOT EXISTS ix_staging_v5_source_periodo ON staging_v5_importado(source_id,periodo)')
        con.execute('CREATE INDEX IF NOT EXISTS ix_fao_uuid_data ON fao_precos_staging(uuid,data)')
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description='Agro V6: coleta online FAO / metadados IPEADATA / SICOR a partir da saída V5')
    p.add_argument('--input',required=True);p.add_argument('--out',default='resultados_agro_v6')
    p.add_argument('--offline',action='store_true',help='Não faz consultas externas (diagnóstico local)')
    p.add_argument('--max-series',type=int,default=31);p.add_argument('--batch-size',type=int,default=3)
    p.add_argument('--pause',type=float,default=0.75);p.add_argument('--timeout',type=float,default=25)
    args=p.parse_args(argv);out=Path(args.out)
    raw,fao,man=prepare_v5(args.input,out)
    prices=pd.DataFrame(columns=PRICE_COLUMNS);audit=[]
    if not args.offline:
        client=HttpClient(args.pause,args.timeout,audit)
        prices,cat,stats=fao_prices(client,fao,out,batch_size=max(1,min(5,args.batch_size)),max_series=max(1,min(len(fao),args.max_series)))
        query_ipea(client,raw,out)
        query_sicor(client,out)
    else:
        fao.to_csv(out/'fao_catalogo_resolvido_v6.csv',index=False,encoding='utf-8-sig')
        prices.to_csv(out/'fao_precos_mensais_v6.csv',index=False,encoding='utf-8-sig')
        dump({'status':'NAO_EXECUTADO_OFFLINE','uuid_catalogados':len(fao)},out/'sumario_fao_v6.json')
    report=finalize(out,raw,prices,man,audit,online=not args.offline)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
