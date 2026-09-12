"""Supplied economic observations must describe the exported evaluation."""
from dataclasses import asdict
import unittest

from thm.economics_bridge import Measurement, export_evidence
from thm.evaluation.contracts import digest


class CESourceBindingTests(unittest.TestCase):
    def test_foreign_measurement_rejected_for_object_and_mapping(self):
        body = {'layers': {'memory-dataplane': {'rows': []}}, 'provenance': {}}
        receipt = {**body, 'receipt_sha256': digest(body)}
        foreign = Measurement(8, 'byte', 1, 'sum', 'a' * 64)
        for supplied in (foreign, asdict(foreign)):
            with self.subTest(representation=type(supplied).__name__):
                with self.assertRaisesRegex(ValueError, 'different source receipt'):
                    export_evidence(receipt, source_commit='c' * 40,
                                    observations={'physical_read': supplied})
        matching = Measurement(8, 'byte', 1, 'sum', receipt['receipt_sha256'])
        exported = export_evidence(receipt, source_commit='c' * 40,
                                   observations={'physical_read': matching})
        self.assertEqual(exported['measurements']['physical_read'], asdict(matching))
        self.assertEqual(exported['source_receipt_sha256'], matching.source_sha256)


if __name__ == '__main__':
    unittest.main()
