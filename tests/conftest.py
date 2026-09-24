import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import config
from backend.db import init_db

@pytest.fixture(autouse=True)
def isolated_database(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'DATA_DIR',tmp_path)
    monkeypatch.setattr(config,'DB_PATH',tmp_path/'test.sqlite3')
    monkeypatch.setattr(config,'API_KEY','')
    init_db()
