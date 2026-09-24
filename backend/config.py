import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv('MULEGRAPH_DATA_DIR', str(ROOT / 'runtime')))
DB_PATH = DATA_DIR / 'mulegraph.sqlite3'
API_KEY = os.getenv('MULEGRAPH_API_KEY', '')
CORS_ORIGINS = [x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if x.strip()]
MAX_IMPORT_ROWS = int(os.getenv('MAX_IMPORT_ROWS', '250000'))
MAX_ANALYSIS_ROWS = int(os.getenv('MAX_ANALYSIS_ROWS', '100000'))
MAX_UPLOAD_BYTES = int(os.getenv('MAX_UPLOAD_BYTES', str(100 * 1024 * 1024)))
SOURCES = {
    'ibm': ROOT / 'mule-graph-SHIBANKAR-data/MuleGraph/transactions_prepared.csv.gz',
    'samld': ROOT / 'rindaw_data/MuleGraph_Output/transactions_prepared.csv',
    'amlsim': ROOT / 'AMLSim/AMLSim/transactions_prepared.csv',
}
