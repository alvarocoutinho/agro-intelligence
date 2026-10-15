"""Offline source contract and HTTP checks; no external API calls."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agro import webapp


def fixture(name):
    return json.loads((ROOT / 'tests/fixtures' / name).read_text(encoding='utf-8'))


class TestSourceParsers(unittest.TestCase):
    def test_bcb_sgs_dates_and_unit(self):
        self.assertIn('/ultimos/20?', webapp.BCB_URL)
        rows = webapp.parse_bcb(fixture('bcb_sgs_1.json'))
        self.assertEqual([row['date'] for row in rows], ['2026-09-01', '2026-09-02'])
        self.assertEqual(rows[0]['unit'], 'BRL/USD')
        self.assertEqual(rows[1]['value'], 5.125)

    def test_ibge_quantity_and_missing_value(self):
        rows = webapp.parse_ibge(fixture('ibge_pam_1612.json'))
        self.assertEqual(rows[0]['product'], 'Soja (em grão)')
        self.assertEqual(rows[0]['unit'], 'Toneladas')
        self.assertEqual(rows[0]['value'], 1000)
        self.assertIsNone(rows[1]['value'])
        self.assertEqual(rows[1]['quality'], 'AUSENTE')

    def test_ibge_rejects_other_variable_or_unit(self):
        payload = fixture('ibge_pam_1612.json')
        payload[0]['unidade'] = 'Reais'
        with self.assertRaisesRegex(ValueError, 'Unidade PAM'):
            webapp.parse_ibge(payload)


class TestWebRoutes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        webapp._cache.clear()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=webapp.app), base_url='http://test'
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_home_and_demo_are_usable(self):
        home = await self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertIn('Agro Intelligence', home.text)
        self.assertEqual((await self.client.get('/assets/app.js')).status_code, 200)
        sources = (await self.client.get('/api/sources')).json()
        self.assertFalse(next(item for item in sources if item['id'] == 'mdic')['available'])
        self.assertFalse(next(item for item in sources if item['id'] == 'v8')['available'])
        response = await self.client.get('/api/observations/demo')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['source']['kind'], 'demo')
        self.assertTrue(payload['observations'])
        self.assertTrue(all(row['quality'] == 'SINTETICO' for row in payload['observations']))

    async def test_bcb_cache_and_refresh(self):
        mocked = AsyncMock(return_value=fixture('bcb_sgs_1.json'))
        with patch.object(webapp, 'fetch_json', mocked):
            first = await self.client.get('/api/observations/bcb')
            second = await self.client.get('/api/observations/bcb')
            refreshed = await self.client.get('/api/observations/bcb?refresh=true')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(mocked.await_count, 2)
        self.assertEqual(first.json()['observations'][0]['stage'], 'CÂMBIO')

    async def test_local_v8_requires_explicit_file(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'v8.sqlite'
            with sqlite3.connect(database) as connection:
                connection.execute('''CREATE TABLE fao_precos_normalizados_v8 (
                    data TEXT, produto TEXT, regiao TEXT, tipo_preco TEXT,
                    preco_brl_kg TEXT, status_qualidade TEXT, url_origem_api TEXT,
                    fonte_primaria TEXT, fonte_distribuidora TEXT)''')
                connection.execute('''INSERT INTO fao_precos_normalizados_v8 VALUES
                    ('2026-09-01','Feijão-preto','São Paulo','ATACADO','8.750000','OK',
                     'https://example.org','CONAB','FAO FPMA')''')
            with patch.dict(os.environ, {'AGRO_V8_SQLITE': str(database)}):
                sources = (await self.client.get('/api/sources')).json()
                self.assertTrue(next(item for item in sources if item['id'] == 'v8')['available'])
                response = await self.client.get('/api/observations/v8')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['observations'][0]['value'], 8.75)
            self.assertEqual(response.json()['observations'][0]['primary_source'], 'CONAB')
        self.assertEqual((await self.client.get('/api/observations/v8')).status_code, 409)


if __name__ == '__main__':
    unittest.main()
