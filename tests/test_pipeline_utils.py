"""Unit tests on pure utility functions. Do not require external data or internet."""
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from agro import pipeline_v8 as p

class TestPipelineUtilities(unittest.TestCase):
    def test_decimal(self):
        self.assertEqual(p.dec('3.50'), Decimal('3.50'))
        self.assertIsNone(p.dec('não informado'))
    def test_precision(self):
        self.assertEqual(p.fix(Decimal('1.6666666'), 3), '1.667')
    def test_months_between(self):
        self.assertEqual(p.months_between('2026-01-01','2026-03-01'), 3)
    def test_reference_defaults_to_baseline_manifest(self):
        self.assertEqual(p.baseline_reference(), date(2026,10,14))
        self.assertEqual(p.monthdist('2026-06-01', date(2026,10,14)), 4)
        self.assertEqual(p.monthdist('2026-06-01', date(2026,9,1)), 3)

if __name__ == '__main__': unittest.main()
