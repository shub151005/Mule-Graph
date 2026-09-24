import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from . import config

def now():
    return datetime.now(timezone.utc).isoformat()

def encode(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, default=str)

@contextmanager
def connection():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(recover_jobs=False):
    with connection() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT, created_at TEXT, rows INTEGER,
            accounts INTEGER, time_kind TEXT, min_time REAL, max_time REAL, quality TEXT);
        CREATE TABLE IF NOT EXISTS transactions (
            dataset_id TEXT REFERENCES datasets(id) ON DELETE CASCADE, id TEXT, sender TEXT,
            receiver TEXT, time REAL, timestamp TEXT, amount TEXT, currency TEXT,
            received TEXT, receiving_currency TEXT, payment_format TEXT, source_row INTEGER,
            device_id TEXT, PRIMARY KEY(dataset_id,id));
        CREATE INDEX IF NOT EXISTS tx_time ON transactions(dataset_id,time,id);
        CREATE INDEX IF NOT EXISTS tx_sender ON transactions(dataset_id,sender,time);
        CREATE INDEX IF NOT EXISTS tx_receiver ON transactions(dataset_id,receiver,time);
        CREATE TABLE IF NOT EXISTS labels (
            dataset_id TEXT REFERENCES datasets(id) ON DELETE CASCADE, entity_type TEXT,
            entity_id TEXT, label INTEGER, typology TEXT, PRIMARY KEY(dataset_id,entity_type,entity_id));
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, kind TEXT, status TEXT, progress INTEGER, message TEXT,
            created_at TEXT, updated_at TEXT, result TEXT);
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, dataset_id TEXT REFERENCES datasets(id), created_at TEXT,
            config TEXT, summary TEXT);
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), dataset_id TEXT,
            pattern TEXT, severity TEXT, score REAL, title TEXT, explanation TEXT,
            accounts TEXT, transaction_ids TEXT, evidence TEXT, status TEXT DEFAULT 'New');
        CREATE INDEX IF NOT EXISTS alert_run ON alerts(run_id,severity);
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY, alert_id TEXT REFERENCES alerts(id), body TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, event TEXT, entity_id TEXT, details TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY, dataset_id TEXT, created_at TEXT, kind TEXT, metadata TEXT);
        ''')
        if recover_jobs:
            c.execute("UPDATE jobs SET status='interrupted',message='Server restarted. Please run again.',updated_at=? WHERE status IN ('queued','running')", (now(),))

def audit(c, event, entity_id, details):
    c.execute('INSERT INTO audit(event,entity_id,details,created_at) VALUES(?,?,?,?)', (event,entity_id,encode(details),now()))

def dataset_dict(row):
    d = dict(row); d['quality'] = json.loads(d['quality']); return d

def alert_dict(row):
    d = dict(row)
    for field in ('accounts','transaction_ids','evidence'):
        d[field] = json.loads(d[field])
    return d
