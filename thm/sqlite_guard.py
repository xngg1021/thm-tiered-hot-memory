"""Refuse foreign SQLite files before installing derived THM tables."""
from pathlib import Path
import sqlite3


def connect_derived(path, required_tables, *, shared_thread=False):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('symlink derived database refused')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5, check_same_thread=not shared_thread)
    try:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables and not set(required_tables) <= tables:
            raise ValueError('FOREIGN_DATABASE: use a separate THM derived database')
        return db
    except Exception:
        db.close()
        raise
