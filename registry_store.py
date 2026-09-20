"""SQLite metadata store. No plaintext medical records or AES keys are stored."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL


def now():
    return datetime.now(timezone.utc).isoformat()


class RegistryStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, file_id, **fields):
        record = dict(fields, id=file_id, created_at=now(), updated_at=now())
        with self.connect() as db:
            db.execute('INSERT INTO files VALUES (?, ?)', (file_id, json.dumps(record)))
        return record

    def update(self, file_id, **fields):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM files WHERE id=?', (file_id,)).fetchone()
            if row is None:
                raise KeyError(file_id)
            record = json.loads(row[0])
            record.update(fields, updated_at=now())
            db.execute('UPDATE files SET payload=? WHERE id=?', (json.dumps(record), file_id))
        return record

    def list(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM files ORDER BY rowid')]

    def import_legacy(self, path):
        """Explicit, atomic and repeatable migration; preserve the source JSON."""
        with open(path, encoding='utf-8') as source:
            records = json.load(source)
        if not isinstance(records, list) or not all(isinstance(x, dict) for x in records):
            raise ValueError('Legacy registry must contain an array of objects')
        with self.connect() as db:
            for record in records:
                identity = json.dumps(record, sort_keys=True, ensure_ascii=False)
                file_id = str(uuid5(NAMESPACE_URL, identity))
                payload = dict(record, id=file_id, status='LEGACY_UNVERIFIED', updated_at=now())
                db.execute('INSERT OR IGNORE INTO files VALUES (?, ?)', (file_id, json.dumps(payload)))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Import registry.json without modifying the original')
    parser.add_argument('source')
    parser.add_argument('--database', default='registry.sqlite3')
    args = parser.parse_args()
    RegistryStore(args.database).import_legacy(args.source)
