import json
import unittest
from pathlib import Path
class TestBaselineManifest(unittest.TestCase):
    def test_metadata_has_provenance(self):
        f=Path(__file__).resolve().parents[1]/'docs/baseline_v8.json'
        m=json.loads(f.read_text(encoding='utf-8'))
        self.assertEqual(m['series'],31)
        self.assertEqual(m['observacoes'],3926)
        self.assertEqual(m['referencia'],'2026-10-14')
        self.assertEqual(m['pares_completos'],1399)
        self.assertEqual(m['pares_sem_anomalias'],1398)

if __name__=='__main__':unittest.main()
