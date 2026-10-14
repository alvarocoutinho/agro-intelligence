"""Constrói uma camada local auditável para resultados_agro_v6.zip.
Uso: python construir_base_v7.py /caminho/resultados_agro_v6.zip /diretorio/saida
Não executa chamadas externas nem presume licenças para uso comercial.
"""
from __future__ import annotations
import io, json, re, sqlite3, sys, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED = ['fao_precos_mensais_v6.csv','fao_catalogo_resolvido_v6.csv',
            'ipeadata_abate_aves_serie_v6.csv','observacoes_staging_importadas_v6.csv',
            'sicor_entidades_odata_v6.csv','resumo_v6.json']

def go(zip_path, output_path):
    out=Path(output_path); out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        missing=set(REQUIRED).difference(z.namelist())
        if missing: raise ValueError(f'Faltam arquivos essenciais: {missing}')
        read=lambda name: pd.read_csv(io.BytesIO(z.read(name)))
        p=read('fao_precos_mensais_v6.csv'); cat=read('fao_catalogo_resolvido_v6.csv')
        ipea=read('ipeadata_abate_aves_serie_v6.csv'); stag=read('observacoes_staging_importadas_v6.csv')
        sicor=read('sicor_entidades_odata_v6.csv')
        meta=json.loads(z.read('ipeadata_metadados_v6.json')) if 'ipeadata_metadados_v6.json' in z.namelist() else {}
        log=read('auditoria_online_v6.csv') if 'auditoria_online_v6.csv' in z.namelist() else pd.DataFrame()
    for col in ['valor_brl_por_unidade_original','valor_brl_por_kg','conversion_factor_api']:
        p[col]=pd.to_numeric(p[col],errors='coerce')
    # Exata por massa da embalagem, não pelo fator arredondado informado pela API.
    def kg(unit):
        if pd.isna(unit): return np.nan
        u=str(unit).strip().lower().replace(',','.')
        if u in ('kg','1 kg'):return 1.0
        m=re.fullmatch(r'(\d+(?:\.\d+)?)\s*kg',u)
        return float(m.group(1)) if m else np.nan
    p['quantidade_kg_unidade_original']=p['unidade_original'].map(kg)
    p['preco_brl_por_kg_exato']=p.valor_brl_por_unidade_original/p.quantidade_kg_unidade_original
    p['preco_brl_por_saca_60kg_equivalente']=60*p.preco_brl_por_kg_exato
    p['fator_conversao_exato']=1/p.quantidade_kg_unidade_original
    p['desvio_relativo_fator_api_pct']=100*(p.conversion_factor_api/p.fator_conversao_exato-1)
    p['ajuste_conversao']=np.where(abs(p.desvio_relativo_fator_api_pct)>0.005,'FATOR_API_ARREDONDADO','SEM_DIFERENCA_RELEVANTE')
    p['classificacao_preco']= 'PENDENTE_PRECO_TIPO_ESPECIFICO'
    p['licenca_redistribuicao']='PENDENTE_VERIFICACAO'
    p['nivel_qualidade']='CANDIDATA_COM_METADADOS_PARCIAIS'
    p['data']=pd.to_datetime(p.data,errors='coerce')
    assert p.data.notna().all(), 'Datas FAO inválidas'
    assert p.uuid.notna().all() and (p.preco_brl_por_kg_exato>0).all(), 'Observação FAO sem UUID/preço positivo'
    assert not p.duplicated(['uuid','data']).any(), 'UUID+data duplicados'
    assert set(p.uuid)==set(cat.uuid), 'Catálogo e valores FAO divergem'

    # Detecção reprodutível de saltos extremos isolados entre meses consecutivos.
    p=p.sort_values(['uuid','data']).reset_index(drop=True)
    anomalies=[]
    p['flag_salto_isolado']=False
    for uid, group in p.groupby('uuid'):
        idx=group.index.to_list()
        for a,b,c in zip(idx,idx[1:],idx[2:]):
            r0,r1,r2=p.loc[a],p.loc[b],p.loc[c]
            gap1=(r1.data-r0.data).days;gap2=(r2.data-r1.data).days
            if not (27<=gap1<=35 and 27<=gap2<=35): continue
            v0,v1,v2=(float(r.preco_brl_por_kg_exato) for r in (r0,r1,r2))
            base=np.sqrt(v0*v2)
            ratio=v1/base
            if (ratio<0.35 or ratio>2.85) and (0.65<=v0/v2<=1.55):
                p.loc[b,'flag_salto_isolado']=True
                anomalies.append({'uuid':uid,'produto':r1.commodity_nome,'mercado':r1.mercado_nome,
                 'data':r1.data.date().isoformat(),'unidade_original':r1.unidade_original,
                 'valor_original':v1*float(r1.quantidade_kg_unidade_original),
                 'valor_mes_anterior':v0*float(r0.quantidade_kg_unidade_original),
                 'valor_mes_seguinte':v2*float(r2.quantidade_kg_unidade_original),
                 'razao_vs_media_geometrica_vizinhos':ratio,
                 'flag':'REVISAR_SALTO_ISOLADO_SEM_CORRECAO_AUTOMATICA'})
    anomaly_df=pd.DataFrame(anomalies,columns=['uuid','produto','mercado','data','unidade_original','valor_original','valor_mes_anterior','valor_mes_seguinte','razao_vs_media_geometrica_vizinhos','flag'])
    p['data']=p.data.dt.date.astype(str)
    p.to_csv(out/'fao_precos_auditados_v7.csv',index=False)
    anomaly_df.to_csv(out/'fao_alertas_outliers_v7.csv',index=False)
    cov=[]
    for uid,g in p.groupby('uuid'):
        m=pd.to_datetime(g.data)
        months=pd.date_range(m.min(),m.max(),freq='MS')
        gaps=months.difference(m)
        cov.append({'uuid':uid,'produto':g.commodity_nome.iloc[0], 'mercado':g.mercado_nome.iloc[0],
           'unidade_original':g.unidade_original.iloc[0], 'tipo_preco':'NAO_CONFIRMADO',
           'data_inicio':g.data.min(),'data_fim':g.data.max(), 'observacoes':len(g),
           'meses_periodo':len(months),'meses_ausentes_internos':len(gaps),
           'cobertura_pct':round(100*len(g)/len(months),2),
           'meses_ausentes_lista':','.join(gaps.strftime('%Y-%m')),
           'sinalizacoes_outlier':int(g.flag_salto_isolado.sum()),
           'status':'METADADOS_DE_PRECO_E_LICENCA_PENDENTES'})
    coverage=pd.DataFrame(cov).sort_values(['produto','mercado','unidade_original'])
    coverage.to_csv(out/'fao_cobertura_series_v7.csv',index=False)

    # A série IPEADATA é separada e preserva os valores da V6, sem presumir comparabilidade histórica.
    ipea[['periodo','valor_original','valor_em_toneladas','unidade_original','serie_codigo','serie_nome','qualidade_metadado']].to_csv(out/'ipeadata_abate_aves_v7.csv',index=False)
    # Retém todos os estágios anteriores para rastreabilidade.
    db=sqlite3.connect(out/'agro_integrado_v7.sqlite')
    for name,table in [('fao_precos_candidatos',p),('fao_series_cobertura',coverage),('fao_alertas_outliers',anomaly_df),
        ('ipeadata_abate_aves',ipea),('ibge_amostras',stag[stag.source_id.isin(['AG009','AG010'])]),
        ('v5_staging_legado',stag),('sicor_entidades_catalogadas',sicor),('auditoria_online_v6',log)]:
        table.to_sql(name,db,if_exists='replace',index=False)
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_fao_uuid_data ON fao_precos_candidatos(uuid,data)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_fao_prod_merc_data ON fao_precos_candidatos(commodity_nome,mercado_nome,data)')
    db.commit()
    checks={x:db.execute('SELECT COUNT(*) FROM '+x).fetchone()[0] for x in ['fao_precos_candidatos','fao_series_cobertura','ipeadata_abate_aves','ibge_amostras','v5_staging_legado']}
    db.close()
    summary={'versao':'V7 local: normalização e QA; consultas externas NÃO executadas nesta versão',
             'fao_observacoes':len(p),'fao_series':p.uuid.nunique(),'fao_produtos':p.commodity_nome.nunique(),
             'fao_pracas':p.mercado_nome.nunique(),'fao_data_min':p.data.min(),'fao_data_max':p.data.max(),
             'ipeadata_obs':len(ipea),'ibge_amostras':checks['ibge_amostras'],
             'fao_fator_30kg_registros':int((p.unidade_original=='30 kg').sum()),
             'fao_outliers_suspeitos':len(anomaly_df),'fao_meses_ausentes_internos':int(coverage.meses_ausentes_internos.sum()),
             'preco_tipo_validado':0,'licenca_publicacao_validada':False,
             'banco_tabelas':checks,
             'nota':'Preços FAO são dados candidatos; a comparação direta com preços ao produtor permanece inadequada até confirmação do tipo de preço.'}
    (out/'resumo_qualidade_v7.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary

if __name__=='__main__':
    go(sys.argv[1] if len(sys.argv)>1 else '/mnt/data/resultados_agro_v6.zip',
       sys.argv[2] if len(sys.argv)>2 else '/mnt/data/agro_v7')
