import csv
import hmac
import io
import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from . import config, ingest, jobs, analysis, ml
from .db import connection, init_db, now, encode, audit, dataset_dict, alert_dict

@asynccontextmanager
async def lifespan(app):
    if os.getenv('RENDER') and not config.API_KEY:
        raise RuntimeError('Set MULEGRAPH_API_KEY before exposing the API on Render.')
    init_db(recover_jobs=True)
    yield

app=FastAPI(title='MuleGraph',version='1.0.0',lifespan=lifespan,description='Synthetic-data investigation research. No automated financial decisions.')
app.add_middleware(CORSMiddleware,allow_origins=config.CORS_ORIGINS,allow_methods=['GET','POST','PATCH','OPTIONS'],allow_headers=['Content-Type','X-API-Key'])

def authenticated(x_api_key: str=Header(default='')):
    if config.API_KEY and not hmac.compare_digest(x_api_key,config.API_KEY):raise HTTPException(401,'Valid API key required')

api=APIRouter(prefix='/api',dependencies=[Depends(authenticated)])

@app.get('/health')
def health():return {'status':'ok','service':'MuleGraph','version':'1.0.0'}

@api.get('/datasets')
def datasets():
    with connection() as c:return [dataset_dict(r) for r in c.execute('SELECT * FROM datasets ORDER BY created_at DESC')]

@api.get('/sources')
def sources():return [{'id':k,'available':v.exists()} for k,v in config.SOURCES.items()]

class LocalImport(BaseModel):
    source:Literal['ibm','samld','amlsim']
    limit:int=Field(default=25000,ge=100,le=config.MAX_IMPORT_ROWS)

def enqueue(kind,work):
    try:return jobs.submit(kind,work)
    except ValueError as exc:raise HTTPException(429,str(exc))

@api.post('/datasets/local',status_code=202)
def local_import(body:LocalImport):return enqueue('import',lambda p:ingest.import_local(body.source,body.limit,p))

@api.post('/datasets/demo',status_code=202)
def demo():return enqueue('demo',ingest.demo)

@api.post('/datasets/upload',status_code=202)
async def upload(file:UploadFile=File(...),limit:int=Query(default=25000,ge=100,le=config.MAX_IMPORT_ROWS)):
    filename=file.filename or ''
    if not filename.lower().endswith(('.csv','.csv.gz')):raise HTTPException(400,'Only CSV or CSV.GZ files are supported')
    folder=config.DATA_DIR/'uploads';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(uuid.uuid4().hex+('.csv.gz' if filename.lower().endswith('.gz') else '.csv'))
    size=0
    try:
        with path.open('wb') as f:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>config.MAX_UPLOAD_BYTES:raise HTTPException(413,'Upload exceeds configured size limit')
                f.write(chunk)
        def work(progress):
            try:return ingest.import_csv(path,filename[:120],limit,progress)
            finally:path.unlink(missing_ok=True)
        return enqueue('upload',work)
    except Exception:
        path.unlink(missing_ok=True);raise
    finally:await file.close()

@api.get('/jobs')
def list_jobs():
    with connection() as c:
        result=[]
        for r in c.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 20'):
            d=dict(r);d['result']=json.loads(d['result']) if d['result'] else None;result.append(d)
        return result

class AnalysisRequest(BaseModel):
    dataset_id:str
    start:float|None=None
    end:float|None=None
    window:float=Field(default=900,gt=0,le=604800)
    min_peers:int=Field(default=5,ge=3,le=100)
    pass_ratio:float=Field(default=.8,gt=0,le=1)
    burst_count:int=Field(default=8,ge=3,le=1000)
    dormant_days:int=Field(default=90,ge=1,le=3650)
    patterns:list[Literal['fan_in','fan_out','pass_through','cycle','burst','dormant','shared_device']]=Field(default_factory=lambda:['fan_in','fan_out','pass_through','cycle','burst','dormant','shared_device'])
    use_ml:bool=False
    @model_validator(mode='after')
    def check_window(self):
        if self.start is not None and self.end is not None and self.start>self.end:raise ValueError('Start must be before end')
        return self

@api.post('/analysis',status_code=202)
def run_analysis(body:AnalysisRequest):return enqueue('analysis',lambda p:analysis.analyze(body.dataset_id,body.model_dump(exclude={'dataset_id'}),p))

@api.get('/runs')
def runs(dataset_id:str):
    with connection() as c:
        return [{**dict(r),'config':json.loads(r['config']),'summary':json.loads(r['summary'])} for r in c.execute('SELECT * FROM runs WHERE dataset_id=? ORDER BY created_at DESC',(dataset_id,))]

@api.get('/alerts')
def alerts(dataset_id:str,run_id:str|None=None,pattern:str|None=None,status:str|None=None,q:str='',limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0)):
    with connection() as c:
        if not run_id:
            r=c.execute('SELECT id FROM runs WHERE dataset_id=? ORDER BY created_at DESC LIMIT 1',(dataset_id,)).fetchone()
            if not r:return {'items':[],'total':0}
            run_id=r['id']
        terms=['dataset_id=?','run_id=?'];args=[dataset_id,run_id]
        for col,value in [('pattern',pattern),('status',status)]:
            if value:terms.append(col+'=?');args.append(value)
        if q:terms.append('(id LIKE ? OR accounts LIKE ?)');args.extend(['%'+q+'%']*2)
        where=' AND '.join(terms)
        total=c.execute('SELECT count(*) FROM alerts WHERE '+where,args).fetchone()[0]
        records=c.execute('SELECT * FROM alerts WHERE '+where+' ORDER BY score DESC,id LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
        return {'items':[alert_dict(r) for r in records],'total':total}

@api.get('/alerts/{alert_id}')
def alert_detail(alert_id:str):
    with connection() as c:
        row=c.execute('SELECT * FROM alerts WHERE id=?',(alert_id,)).fetchone()
        if not row:raise HTTPException(404,'Alert not found')
        d=alert_dict(row)
        d['notes']=[dict(n) for n in c.execute('SELECT * FROM notes WHERE alert_id=? ORDER BY id',(alert_id,))]
        d['transactions']=[dict(t) for tid in d['transaction_ids'] for t in c.execute('SELECT * FROM transactions WHERE dataset_id=? AND id=?',(d['dataset_id'],tid))]
        return d

class UpdateAlert(BaseModel):
    status:Literal['New','Reviewing','Escalated','Closed']|None=None
    note:str=Field(default='',max_length=5000)

@api.patch('/alerts/{alert_id}')
def update_alert(alert_id:str,body:UpdateAlert):
    with connection() as c:
        if not c.execute('SELECT 1 FROM alerts WHERE id=?',(alert_id,)).fetchone():raise HTTPException(404,'Alert not found')
        if body.status:c.execute('UPDATE alerts SET status=? WHERE id=?',(body.status,alert_id))
        if body.note.strip():c.execute('INSERT INTO notes(alert_id,body,created_at) VALUES(?,?,?)',(alert_id,body.note.strip(),now()))
        audit(c,'alert.updated',alert_id,body.model_dump())
    return alert_detail(alert_id)

@api.get('/transactions')
def transactions(dataset_id:str,account:str='',q:str='',start:float|None=None,end:float|None=None,limit:int=Query(50,ge=1,le=500),offset:int=Query(0,ge=0)):
    terms=['dataset_id=?'];args=[dataset_id]
    if account:terms.append('(sender=? OR receiver=?)');args.extend([account,account])
    if q:terms.append('(id LIKE ? OR sender LIKE ? OR receiver LIKE ?)');args.extend(['%'+q+'%']*3)
    if start is not None:terms.append('time>=?');args.append(start)
    if end is not None:terms.append('time<=?');args.append(end)
    where=' AND '.join(terms)
    with connection() as c:
        count=c.execute('SELECT count(*) FROM transactions WHERE '+where,args).fetchone()[0]
        return {'items':[dict(r) for r in c.execute('SELECT * FROM transactions WHERE '+where+' ORDER BY time,id LIMIT ? OFFSET ?',args+[limit,offset])],'total':count}

@api.get('/accounts')
def accounts(dataset_id:str,q:str='',limit:int=Query(50,ge=1,le=200)):
    with connection() as c:
        return [dict(r) for r in c.execute('''SELECT account,count(*) activity FROM
            (SELECT sender account FROM transactions WHERE dataset_id=? UNION ALL SELECT receiver account FROM transactions WHERE dataset_id=?)
            WHERE account LIKE ? GROUP BY account ORDER BY activity DESC LIMIT ?''',(dataset_id,dataset_id,'%'+q+'%',limit))]

@api.get('/accounts/detail')
def account_detail(dataset_id:str,account:str):
    data=transactions(dataset_id,account,'',None,None,100,0)
    with connection() as c:
        groups=[dict(r) for r in c.execute('''SELECT currency, CASE WHEN sender=? THEN 'outgoing' ELSE 'incoming' END direction,
          count(*) count FROM transactions WHERE dataset_id=? AND (sender=? OR receiver=?) GROUP BY currency,direction''',(account,dataset_id,account,account))]
        linked=[alert_dict(r) for r in c.execute('SELECT * FROM alerts WHERE dataset_id=?',(dataset_id,)) if account in json.loads(r['accounts'])]
    return {'account':account,'transactions':data,'currency_activity':groups,'alerts':linked[:50]}

@api.get('/graph')
def graph(dataset_id:str,alert_id:str='',account:str='',limit:int=Query(150,ge=5,le=300)):
    if alert_id:
        detail=alert_detail(alert_id)
        if detail['dataset_id']!=dataset_id:raise HTTPException(400,'Alert belongs to a different dataset')
        rows=detail['transactions'];total=len(rows);rows=rows[:limit]
    else:
        data=transactions(dataset_id,account,'',None,None,limit,0);rows=data['items'];total=data['total']
    nodes=sorted({x for r in rows for x in (r['sender'],r['receiver'])})
    return {'nodes':[{'id':n,'label':n} for n in nodes],'edges':rows,'limited':total>len(rows),'total_transactions':total}

class TrainRequest(BaseModel):
    dataset_id:str
    start:float|None=None
    end:float|None=None

@api.post('/models/train',status_code=202)
def train(body:TrainRequest):return enqueue('training',lambda p:ml.train(body.dataset_id,body.start,body.end,p))

@api.get('/models')
def models(dataset_id:str):
    with connection() as c:return [{**dict(r),'metadata':json.loads(r['metadata'])} for r in c.execute('SELECT * FROM models WHERE dataset_id=? ORDER BY created_at DESC',(dataset_id,))]

@api.get('/audit')
def audit_log():
    with connection() as c:return [{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200')]

@api.get('/export/{alert_id}')
def export(alert_id:str,format:Literal['json','csv']='json'):
    d=alert_detail(alert_id)
    if format=='json':
        payload={'title':'MuleGraph investigation evidence','exported_at':now(),'disclaimer':'Research evidence, not a regulatory SAR filing or proof of wrongdoing','alert':d}
        return Response(encode(payload),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="{alert_id}.json"'})
    out=io.StringIO();rows=d['transactions']
    if rows:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader()
        for row in rows:
            # Prevent formula execution when an exported identifier is opened in Excel.
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()})
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{alert_id}.csv"'})

app.include_router(api)
