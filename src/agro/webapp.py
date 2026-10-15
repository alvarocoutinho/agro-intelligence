"""Read-only exploration API for explicitly identified agro data sources."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
BCB_URL = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/20?formato=json'
IBGE_URL = 'https://servicodados.ibge.gov.br/api/v3/agregados/1612/periodos/-5/variaveis/214'
CACHE_SECONDS = 15 * 60

SOURCES = [
    {'id': 'demo', 'name': 'Amostra sintética', 'group': 'Explorar', 'kind': 'demo',
     'unit': 'BRL/kg', 'frequency': 'Mensal', 'stage': 'Atacado e varejo',
     'note': 'Valores fictícios para testar a interface. Não representam preços observados.'},
    {'id': 'v8', 'name': 'FAO / CONAB · V8 local', 'group': 'Preços', 'kind': 'local',
     'unit': 'BRL/kg', 'frequency': 'Mensal', 'stage': 'Atacado e varejo',
     'note': 'Séries locais V8. Verificar licença FAO e fonte original antes de redistribuir.'},
    {'id': 'bcb', 'name': 'BCB · câmbio SGS 1', 'group': 'Contexto', 'kind': 'live',
     'unit': 'BRL/USD', 'frequency': 'Diária', 'stage': 'Câmbio',
     'note': 'Dólar comercial, série SGS 1. Contexto macroeconômico; não é preço agropecuário.'},
    {'id': 'ibge', 'name': 'IBGE · PAM 1612', 'group': 'Produção', 'kind': 'live',
     'unit': 'Toneladas', 'frequency': 'Anual', 'stage': 'Produção',
     'note': 'Quantidade produzida na lavoura temporária, por produto. Não é preço.'},
    {'id': 'mdic', 'name': 'MDIC · Comex Stat', 'group': 'Próximas fontes', 'kind': 'planned',
     'unit': 'US$ FOB / kg', 'frequency': 'Mensal', 'stage': 'Comércio exterior',
     'note': 'Conector em preparação: NCM, país, localidade e unidade precisam ser validados.'},
    {'id': 'conab_prices', 'name': 'CONAB · produtor', 'group': 'Próximas fontes', 'kind': 'planned',
     'unit': 'Por fonte', 'frequency': 'Por fonte', 'stage': 'Produtor',
     'note': 'Conector em preparação: metodologia e licença da série precisam ser validadas.'},
    {'id': 'conab_costs', 'name': 'CONAB · custos', 'group': 'Próximas fontes', 'kind': 'planned',
     'unit': 'Por fonte', 'frequency': 'Por fonte', 'stage': 'Custo de produção',
     'note': 'Conector em preparação: safra, sistema de produção e componentes de custo.'},
]

app = FastAPI(title='Agro Intelligence', version='0.1.0')
app.mount('/assets', StaticFiles(directory=WEB), name='assets')
_cache: dict[str, tuple[float, list[dict], str]] = {}


def source_info(source_id: str) -> dict:
    source = next((item for item in SOURCES if item['id'] == source_id), None)
    if source is None:
        raise HTTPException(status_code=404, detail='Fonte desconhecida')
    return {**source, 'available': source['kind'] not in ('planned',) and (
        source_id != 'v8' or Path(os.environ.get('AGRO_V8_SQLITE', '')).is_file()
    )}


def finite_number(value) -> float | None:
    try:
        number = Decimal(str(value))
        return float(number) if number.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_bcb(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError('Resposta SGS sem lista de observações')
    observations = []
    for row in payload:
        day = datetime.strptime(row['data'], '%d/%m/%Y').date().isoformat()
        value = finite_number(row.get('valor'))
        observations.append({
            'date': day, 'value': value, 'unit': 'BRL/USD',
            'product': 'Dólar comercial', 'location': 'Brasil', 'stage': 'CÂMBIO',
            'quality': 'OK' if value is not None else 'AUSENTE',
            'source_url': BCB_URL, 'primary_source': 'Banco Central do Brasil',
            'distributor': 'BCB SGS',
        })
    return sorted(observations, key=lambda row: row['date'])


def parse_ibge(payload: object) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise ValueError('Resposta PAM sem variáveis')
    observations = []
    for variable in payload:
        if (str(variable.get('id')) != '214' or
                'quantidade produzida' not in variable.get('variavel', '').lower()):
            raise ValueError('Variável PAM diferente de quantidade produzida')
        unit = variable.get('unidade', '')
        if unit.lower() != 'toneladas':
            raise ValueError('Unidade PAM não reconhecida')
        for result in variable.get('resultados', []):
            categories = [name for classification in result.get('classificacoes', [])
                          for name in classification.get('categoria', {}).values()]
            product = ' / '.join(categories) if categories else 'Produto não identificado'
            for series in result.get('series', []):
                location = series.get('localidade', {}).get('nome', 'Local não identificado')
                for period, raw_value in series.get('serie', {}).items():
                    if not (len(period) == 4 and period.isdigit()):
                        continue
                    value = finite_number(raw_value)
                    observations.append({
                        'date': f'{period}-01-01', 'value': value, 'unit': unit,
                        'product': product, 'location': location, 'stage': 'PRODUÇÃO',
                        'quality': 'OK' if value is not None else 'AUSENTE',
                        'source_url': IBGE_URL, 'primary_source': 'IBGE',
                        'distributor': 'IBGE SIDRA',
                    })
    return sorted(observations, key=lambda row: (row['product'], row['date']))


async def fetch_json(url: str, params: dict | None = None) -> object:
    async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                 headers={'User-Agent': 'AgroIntelligence/0.1 (research; read-only)'}) as client:
        for attempt in range(3):
            try:
                response = await client.get(url, params=params)
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry_after = response.headers.get('Retry-After', '0')
                    delay = min(5, max(2 ** attempt, int(retry_after) if retry_after.isdigit() else 0))
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError('Resposta maior que o limite de 2 MB')
                return response.json()
            except httpx.TransportError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError('Consulta não concluída')


def local_observations(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError('SQLite V8 configurado não encontrado')
    uri = f'{path.resolve().as_uri()}?mode=ro'
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute('''
            SELECT data, produto, regiao, tipo_preco, preco_brl_kg,
                   status_qualidade, url_origem_api, fonte_primaria, fonte_distribuidora
            FROM fao_precos_normalizados_v8 ORDER BY data, produto, regiao, tipo_preco
        ''').fetchall()
    return [{
        'date': row['data'], 'value': finite_number(row['preco_brl_kg']),
        'unit': 'BRL/kg', 'product': row['produto'], 'location': row['regiao'],
        'stage': row['tipo_preco'], 'quality': row['status_qualidade'],
        'source_url': row['url_origem_api'], 'primary_source': row['fonte_primaria'],
        'distributor': row['fonte_distribuidora'],
    } for row in rows]


@app.get('/')
def index():
    return FileResponse(WEB / 'index.html')


@app.get('/api/sources')
def sources():
    return [source_info(source['id']) for source in SOURCES]


@app.get('/api/observations/{source_id}')
async def observations(source_id: str, refresh: bool = False):
    source = source_info(source_id)
    if not source['available']:
        raise HTTPException(status_code=409, detail='Fonte ainda não configurada')
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        if source_id == 'demo':
            data = json.loads((ROOT / 'data/samples/demo_observations.json').read_text(encoding='utf-8'))
            data = [{**row, 'unit': 'BRL/kg', 'source_url': None,
                     'primary_source': 'Amostra sintética', 'distributor': 'Agro Intelligence'} for row in data]
        elif source_id == 'v8':
            data = local_observations(Path(os.environ['AGRO_V8_SQLITE']))
        else:
            cached = _cache.get(source_id)
            if cached and cached[0] > time.monotonic() and not refresh:
                data = cached[1]
                fetched_at = cached[2]
            else:
                if source_id == 'bcb':
                    data = parse_bcb(await fetch_json(BCB_URL))
                elif source_id == 'ibge':
                    data = parse_ibge(await fetch_json(IBGE_URL, {
                        'localidades': 'N1[all]', 'classificacao': '81[all]',
                    }))
                else:
                    raise HTTPException(status_code=404, detail='Fonte desconhecida')
                _cache[source_id] = (time.monotonic() + CACHE_SECONDS, data, fetched_at)
    except (httpx.HTTPError, OSError, ValueError, KeyError, sqlite3.Error) as exc:
        raise HTTPException(status_code=502, detail=f'Falha ao consultar {source["name"]}: {exc}') from exc
    return {'source': source, 'observations': data, 'fetched_at': fetched_at}
