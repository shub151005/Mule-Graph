"""Explicit manual integration check against the user's immutable source CSVs."""
import json
from backend.db import init_db,connection
from backend.ingest import import_local
from backend.analysis import analyze

if __name__=='__main__':
    init_db()
    for source in ['ibm','samld','amlsim']:
        progress=lambda n,s:print(source,n,s,flush=True)
        result=import_local(source,5000,progress)
        report=analyze(result['dataset_id'],{'window':5 if source=='amlsim' else 900},progress)
        with connection() as c:
            labels=[dict(r) for r in c.execute('SELECT entity_type,label,count(*) count FROM labels WHERE dataset_id=? GROUP BY entity_type,label',(result['dataset_id'],))]
        print(json.dumps({'source':source,'import':result,'analysis':report,'labels':labels}),flush=True)
