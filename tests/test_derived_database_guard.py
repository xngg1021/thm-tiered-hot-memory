import sqlite3
import tempfile
from pathlib import Path
import unittest
from thm.retrieval import SearchIndex
from thm.observations import store_observations


class DerivedDatabaseGuards(unittest.TestCase):
    def test_foreign_source_database_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'state.db'
            db = sqlite3.connect(path)
            db.execute('CREATE TABLE messages(id INTEGER,content TEXT)')
            db.execute("INSERT INTO messages VALUES(1,'keep')")
            db.commit(); db.close()
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'FOREIGN_DATABASE'):
                SearchIndex(path)
            self.assertEqual(original, path.read_bytes())
            with self.assertRaisesRegex(ValueError, 'FOREIGN_DATABASE'):
                store_observations(path, [])
            self.assertEqual(original, path.read_bytes())

    def test_observations_cannot_be_written_into_retrieval_database(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'recall.db'
            SearchIndex(path).close()
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'FOREIGN_DATABASE'):
                store_observations(path, [])
            self.assertEqual(original, path.read_bytes())

    def test_retrieval_cannot_be_written_into_observation_database(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'observations.db'
            store_observations(path, [])
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'FOREIGN_DATABASE'):
                SearchIndex(path)
            self.assertEqual(original, path.read_bytes())
