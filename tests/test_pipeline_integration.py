"""Offline V7 ZIP fixture covering the V8 processing and structural audit."""
import csv
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from agro import pipeline_v8 as pipeline
from agro import webapp
from scripts import audit_v8


def csv_bytes(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def fixture_rows():
    prices = []
    months = [f'2020-{month:02d}-01' for month in range(1, 8)] + [
        f'2026-{month:02d}-01' for month in range(6, 11)
    ]
    for uuid, classification, masses in [
        ('wholesale', 'ATACADO', (10, 30, 50, 60)),
        ('retail', 'VAREJO', (60, 50, 30, 10)),
    ]:
        for index, day in enumerate(months):
            if uuid == 'retail' and day in ('2020-04-01', '2026-08-01'):
                continue
            kg = masses[index % len(masses)]
            price_per_kg = 10 if classification == 'ATACADO' else 12
            if uuid == 'retail' and day == '2026-09-01':
                price_per_kg = 8
            original = str(kg * price_per_kg)
            if uuid == 'retail' and day == '2026-07-01':
                original = 'não informado'
            prices.append({
                'uuid': uuid, 'data': day, 'preco_brl_por_kg_exato': str(price_per_kg),
                'valor_brl_por_unidade_original': original,
                'quantidade_kg_unidade_original': str(kg),
                'flag_salto_isolado': str(uuid == 'wholesale' and day == '2020-03-01'),
                'commodity_nome': 'Beans (black)', 'mercado_nome': 'São Paulo',
                'commodity_id': 'beans', 'market_id': 'sp',
                'unidade_original': f'R$/{kg} kg',
            })

    metas = []
    coverage = []
    for uuid, classification in [('wholesale', 'ATACADO'), ('retail', 'VAREJO')]:
        rows = [row for row in prices if row['uuid'] == uuid]
        metas.append({
            'uuid': uuid, 'produto': 'Beans (black)', 'mercado': 'São Paulo',
            'classificacao_preco': classification,
            'preco_tipo_campo': 'WHOLESALE' if uuid == 'wholesale' else 'RETAIL',
            'market_type_campo': 'Retail',
            'raw_serie_json': json.dumps({'source_name': 'Fonte sintética',
                                          'source_url': 'https://example.org/data',
                                          'commodity_code': 'beans'}),
        })
        months_in_range = pipeline.months_between(rows[0]['data'], rows[-1]['data'])
        coverage.append({
            'uuid': uuid, 'unidade_original': rows[0]['unidade_original'],
            'data_inicio': rows[0]['data'], 'data_fim': rows[-1]['data'],
            'observacoes': str(len(rows)),
            'meses_ausentes_internos': str(months_in_range - len(rows)),
            'cobertura_pct': str(round(100 * len(rows) / months_in_range, 2)),
        })
    return prices, metas, coverage


def write_fixture(path, prices, metas, coverage):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('fao_precos_auditados_v7.csv', csv_bytes(prices))
        archive.writestr('fao_tipos_preco_e_fontes_v7.csv', csv_bytes(metas))
        archive.writestr('fao_cobertura_series_v7.csv', csv_bytes(coverage))
        for name in ('fao_series_metadata_raw_v7.json', 'resumo_metadados_fao_v7.json',
                     'resumo_qualidade_v7.json'):
            archive.writestr(name, '{}')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as source:
        return list(csv.DictReader(source))


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.zip_path = self.root / 'synthetic_v7.zip'
        self.prices, self.metas, self.coverage = fixture_rows()
        write_fixture(self.zip_path, self.prices, self.metas, self.coverage)

    def test_complete_pipeline_and_audit(self):
        legacy_db = self.root / 'legacy.sqlite'
        with sqlite3.connect(legacy_db) as connection:
            connection.execute('CREATE TABLE origem_v7 (id INTEGER PRIMARY KEY, valor TEXT)')
            connection.execute('INSERT INTO origem_v7 VALUES (1, ?)', ('preservado',))
        with zipfile.ZipFile(self.zip_path, 'a') as archive:
            archive.write(legacy_db, 'agro_integrado_v7.sqlite')
        output = self.root / 'v8'
        summary = pipeline.main(self.zip_path, output)
        self.assertEqual(summary['referencia'], '2026-10-14')
        self.assertEqual(summary['series'], 2)
        self.assertEqual(summary['observacoes'], len(self.prices))
        self.assertEqual(summary['outliers_suspeitos'], 1)
        self.assertEqual(summary['series_com_campo_auxiliar_Retail_para_atacado'], 1)
        self.assertGreater(summary['meses_faltantes_dentro_das_series'], 0)

        normalized = read_csv(output / 'fao_precos_normalizados_v8.csv')
        masses = {row['massa_kg_unidade_original'] for row in normalized}
        self.assertEqual(masses, {'10.000', '30.000', '50.000', '60.000'})
        by_key = {(row['uuid'], row['data']): row for row in normalized}
        self.assertEqual(by_key['wholesale', '2026-10-01']['preco_brl_kg'], '10.000000')
        self.assertEqual(by_key['retail', '2026-07-01']['status_qualidade'], 'SEM_PRECO_VALIDO')
        self.assertEqual(by_key['wholesale', '2020-03-01']['status_qualidade'], 'REVISAR_OUTLIER')
        self.assertEqual(by_key['wholesale', '2026-10-01']['indice_nominal_2020_100'], '100.000')

        pairs = read_csv(output / 'fao_pares_atacado_varejo_v8.csv')
        by_date = {row['data']: row for row in pairs}
        self.assertEqual(by_date['2026-09-01']['diferenca_pct_sobre_atacado'], '-20.000')
        self.assertNotIn('2026-08-01', by_date)
        self.assertEqual(by_date['2026-07-01']['status_comparacao'], 'ANOMALIA_NAO_USAR_EM_AGREGADOS')
        self.assertEqual(by_date['2020-03-01']['status_comparacao'], 'ANOMALIA_NAO_USAR_EM_AGREGADOS')
        self.assertEqual(summary['pares_sem_anomalias'], sum(
            row['status_comparacao'] == 'AMOSTRA_COMPARAVEL' for row in pairs
        ))

        db = output / 'agro_integrado_v8.sqlite'
        with sqlite3.connect(db) as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute(
                'SELECT COUNT(*) FROM fao_precos_normalizados_v8'
            ).fetchone()[0], len(self.prices))
            self.assertEqual(connection.execute(
                'SELECT valor FROM origem_v7 WHERE id=1'
            ).fetchone()[0], 'preservado')
        self.assertEqual(len(webapp.local_observations(db)), len(self.prices))

        result_zip = self.root / 'synthetic_v8.zip'
        subprocess.run(
            [sys.executable, '-m', 'zipfile', '-c', str(result_zip),
             *sorted(path.name for path in output.iterdir())],
            cwd=output, check=True, capture_output=True, text=True,
        )
        audit = audit_v8.audit(result_zip)
        self.assertEqual(audit['resultado'], 'APROVADO_ESTRUTURALMENTE')
        self.assertEqual(audit['pares_varejo_menor_atacado'], 1)

    def test_reference_date_changes_staleness(self):
        output = self.root / 'later_reference'
        completed = subprocess.run(
            [sys.executable, str(ROOT / 'src/agro/pipeline_v8.py'), str(self.zip_path),
             '--output', str(output), '--reference-date', '2027-02-01'],
            check=True, capture_output=True, text=True,
        )
        summary = json.loads(completed.stdout)
        self.assertEqual(summary['referencia'], '2027-02-01')
        self.assertEqual(summary['series_defasadas_4m'], 2)
        series = read_csv(output / 'fao_series_classificadas_v8.csv')
        self.assertEqual({row['defasagem_meses'] for row in series}, {'4'})

    def test_duplicate_observation_is_rejected(self):
        self.prices.append(self.prices[0].copy())
        write_fixture(self.zip_path, self.prices, self.metas, self.coverage)
        with self.assertRaisesRegex(ValueError, 'Duplicatas'):
            pipeline.main(self.zip_path, self.root / 'duplicate')

    def test_missing_metadata_is_rejected(self):
        write_fixture(self.zip_path, self.prices, self.metas[:1], self.coverage)
        with self.assertRaisesRegex(ValueError, 'Séries sem metadados'):
            pipeline.main(self.zip_path, self.root / 'missing_metadata')

    def test_negative_price_is_preserved_but_excluded_from_aggregates(self):
        for row in self.prices:
            if row['uuid'] == 'retail' and row['data'] == '2026-06-01':
                row['valor_brl_por_unidade_original'] = '-60'
        write_fixture(self.zip_path, self.prices, self.metas, self.coverage)
        output = self.root / 'negative_price'
        pipeline.main(self.zip_path, output)
        normalized = read_csv(output / 'fao_precos_normalizados_v8.csv')
        row = next(row for row in normalized
                   if row['uuid'] == 'retail' and row['data'] == '2026-06-01')
        self.assertEqual(row['valor_original_brl'], '-60.0000')
        self.assertEqual(row['status_qualidade'], 'SEM_PRECO_VALIDO')
        pair = next(row for row in read_csv(output / 'fao_pares_atacado_varejo_v8.csv')
                    if row['data'] == '2026-06-01')
        self.assertEqual(pair['status_comparacao'], 'ANOMALIA_NAO_USAR_EM_AGREGADOS')

    def test_single_series_without_pairs_or_alerts_has_typed_schema(self):
        prices = [row for row in self.prices
                  if row['uuid'] == 'wholesale' and row['data'] == '2026-10-01']
        metas = [row.copy() for row in self.metas if row['uuid'] == 'wholesale']
        metas[0]['market_type_campo'] = 'Wholesale'
        coverage = [{**self.coverage[0], 'data_inicio': '2026-10-01',
                     'data_fim': '2026-10-01', 'observacoes': '1',
                     'meses_ausentes_internos': '0', 'cobertura_pct': '100'}]
        write_fixture(self.zip_path, prices, metas, coverage)
        output = self.root / 'one_series'
        summary = pipeline.main(self.zip_path, output)
        self.assertEqual(summary['series'], 1)
        self.assertEqual(summary['observacoes'], 1)
        self.assertEqual(summary['pares_completos'], 0)
        for name in ('fao_pares_atacado_varejo_v8.csv', 'fao_resumo_diferenciais_v8.csv',
                     'alertas_qualidade_v8.csv'):
            self.assertEqual(read_csv(output / name), [])

        with sqlite3.connect(output / 'agro_integrado_v8.sqlite') as connection:
            columns = {row[1]: row for row in connection.execute(
                'PRAGMA table_info(fao_precos_normalizados_v8)'
            )}
            self.assertEqual(columns['meses_base_2020'][2], 'INTEGER')
            self.assertEqual(columns['preco_brl_kg'][2], 'TEXT')
            self.assertEqual([columns[key][5] for key in ('uuid', 'data')], [1, 2])
            self.assertEqual(connection.execute('''SELECT typeof(meses_base_2020),
                typeof(preco_brl_kg) FROM fao_precos_normalizados_v8''').fetchone(),
                ('integer', 'text'))
            for table in ('fao_pares_atacado_varejo_v8', 'fao_resumo_diferenciais_v8',
                          'alertas_qualidade_v8'):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute('''INSERT INTO fao_precos_normalizados_v8
                    SELECT * FROM fao_precos_normalizados_v8''')


if __name__ == '__main__':
    unittest.main()
