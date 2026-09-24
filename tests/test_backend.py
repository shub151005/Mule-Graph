import csv
import gzip
import json
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend import config,ingest,analysis,ml
from backend.db import connection
from backend.main import app

def tx(i,s='A',r='B',t=0,amount='100',currency='USD',received='100',rcurrency='USD',device=''):
    return {'id':str(i),'sender':s,'receiver':r,'time':t,'amount':amount,'currency':currency,'received':received,'receiving_currency':rcurrency,'device_id':device}

def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def prepared(**kw):
    return {'sender_account_id':'001','receiver_account_id':'002','timestamp_iso':'2022-09-01T00:01:00','amount_paid':'100.01','payment_currency':'USD','amount_received':'100.01','receiving_currency':'USD',**kw}

def test_prepared_preserves_ids_amount_and_time(tmp_path):
    p=tmp_path/'x.csv';write_csv(p,[prepared()]);res=ingest.import_csv(p,'x',100)
    ds,rows=analysis.load_transactions(res['dataset_id'])
    assert rows[0]['sender']=='001';assert rows[0]['amount']=='100.01';assert rows[0]['timestamp']=='2022-09-01T00:01:00'

@pytest.mark.parametrize('amount',['-1','NaN','Infinity','not-money','1e30'])
def test_invalid_amount_rejected_and_rollback(tmp_path,amount):
    p=tmp_path/'bad.csv';write_csv(p,[prepared(amount_paid=amount)])
    with pytest.raises(ValueError):ingest.import_csv(p,'bad',100)
    with connection() as c:assert c.execute('SELECT count(*) FROM datasets').fetchone()[0]==0

def test_rejection_quality_and_prefix_cap(tmp_path):
    p=tmp_path/'x.csv';write_csv(p,[prepared(),prepared(sender_account_id=''),prepared(sender_account_id='003')])
    res=ingest.import_csv(p,'x',2)
    with connection() as c:quality=json.loads(c.execute('SELECT quality FROM datasets').fetchone()[0])
    assert res['rows']==1 and res['rejected']==1 and quality['truncated']

def test_amlsim_steps_no_currency(tmp_path):
    p=tmp_path/'x.csv';write_csv(p,[{'sourceNodeId':'1','targetNodeId':'2','value':'10','time':'3'}])
    result=ingest.import_csv(p,'x',100);ds,rows=analysis.load_transactions(result['dataset_id'])
    assert ds['time_kind']=='step' and rows[0]['currency']=='' and rows[0]['timestamp']==''

def test_raw_ibm_duplicate_columns(tmp_path):
    p=tmp_path/'ibm.csv'
    p.write_text('Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering\n2022/09/01 00:20,001,00001,002,00002,10,USD,10,USD,Wire,1\n',encoding='utf-8')
    res=ingest.import_csv(p,'ibm',100);_,rows=analysis.load_transactions(res['dataset_id'])
    assert rows[0]['sender']=='001_00001' and rows[0]['receiver']=='002_00002'
    assert 'label' not in rows[0]
    with connection() as c:assert c.execute('SELECT label FROM labels').fetchone()[0]==1

def test_gzip_prepared(tmp_path):
    plain=tmp_path/'x.csv';write_csv(plain,[prepared()]);compressed=tmp_path/'x.csv.gz'
    with gzip.open(compressed,'wb') as f:f.write(plain.read_bytes())
    assert ingestest(compressed)['rows']==1

def ingestest(p):return ingest.import_csv(p,'gzip',100)

def test_fan_in_and_out():
    rows=[tx(i,f'S{i}','H',i) for i in range(5)]+[tx(i+5,'H',f'R{i}',10+i) for i in range(5)]
    found,_=analysis.detect(rows,'timestamp',{'window':100,'min_peers':5})
    assert {'fan_in','fan_out'}<={a['pattern'] for a in found}

def test_self_transfers_not_cycles():
    found,_=analysis.detect([tx(1,'A','A'),tx(2,'A','A',1)],'timestamp',{})
    assert not found

def test_cycle_strictly_temporal():
    rows=[tx(1,'A','B',0),tx(2,'B','C',1),tx(3,'C','A',2)]
    found,_=analysis.detect(rows,'timestamp',{'patterns':['cycle']})
    assert any(a['pattern']=='cycle' for a in found)
    for row in rows:row['time']=0
    assert not analysis.detect(rows,'timestamp',{'patterns':['cycle']})[0]

def test_pass_through_received_amount_and_currency():
    rows=[tx(1,'A','B',0,'200','EUR','100','USD'),tx(2,'B','C',60,'90','USD','90')]
    alerts,_=analysis.detect(rows,'timestamp',{'patterns':['pass_through']})
    assert alerts and alerts[0]['evidence']['forwarded_ratio']==.9
    rows[1]['currency']='GBP'
    assert not analysis.detect(rows,'timestamp',{'patterns':['pass_through']})[0]

def test_unknown_currency_no_amount_match():
    rows=[tx(1,'A','B',0,currency='',rcurrency=''),tx(2,'B','C',60,currency='',rcurrency='')]
    assert not analysis.detect(rows,'step',{'patterns':['pass_through']})[0]

def test_capability_flags_and_dormancy():
    rows=[tx(1,'A','B',0),tx(2,'A','C',100*86400)]
    alerts,limits=analysis.detect(rows,'timestamp',{'patterns':['dormant']})
    assert alerts and 'shared_device' in limits['unavailable_patterns']
    alerts,limits=analysis.detect(rows,'step',{'patterns':['dormant']})
    assert not alerts and 'dormant' in limits['unavailable_patterns']

def test_optional_device_cluster():
    rows=[tx(i,f'A{i}','H',i,device='D1') for i in range(4)]
    assert any(a['pattern']=='shared_device' for a in analysis.detect(rows,'timestamp',{})[0])

def test_features_causal_and_equal_time_safe():
    rows=[tx(1,'A','B',0),tx(2,'A','C',0),tx(3,'A','D',10)]
    first=analysis.causal_features(rows)
    assert first[0,1]==first[1,1]==0 and first[2,1]>0
    extended=analysis.causal_features(rows+[tx(4,'A','B',100,amount='99999')])
    np.testing.assert_equal(first,extended[:3])
    rows[0]['label']=1
    np.testing.assert_equal(first,analysis.causal_features(rows))

def test_api_auth_validation_and_error_states(monkeypatch):
    monkeypatch.setattr(config,'API_KEY','secret')
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        assert client.get('/api/datasets').status_code==401
        assert client.get('/api/datasets',headers={'X-API-Key':'secret'}).status_code==200
        assert client.post('/api/analysis',headers={'X-API-Key':'secret'},json={'dataset_id':'x','window':-1}).status_code==422
        assert client.get('/api/alerts/missing',headers={'X-API-Key':'secret'}).status_code==404

def test_end_to_end_demo_model_and_persistence():
    res=ingest.demo();did=res['dataset_id']
    result=analysis.analyze(did,{'window':900},lambda *_:None)
    assert result['alerts']>0
    assert result['evaluation']['entity_type']=='transaction'
    assert result['evaluation']['positive']>0
    model=ml.train(did,None,None,lambda *_:None)
    assert model['split_counts']['train']>0
    assert model['supervised_status'].startswith('Trained')
    assert model['test']['rows']>0
    assert (config.DATA_DIR/'models'/f"{model['model_id']}.joblib").exists()
    ds,rows=analysis.load_transactions(did)
    scored,status=ml.score_latest(did,rows)
    assert all(r['time']>model['train_end'] for r,s in scored)
    with TestClient(app) as client:
        listing=client.get('/api/alerts',params={'dataset_id':did}).json();aid=listing['items'][0]['id']
        detail=client.get('/api/alerts/'+aid).json();assert detail['transactions']
        response=client.patch('/api/alerts/'+aid,json={'status':'Reviewing','note':'Check source history'}).json()
        assert response['status']=='Reviewing' and response['notes'][0]['body']=='Check source history'
        assert client.get('/api/export/'+aid+'?format=csv').status_code==200
        assert client.get('/api/export/'+aid).json()['alert']['id']==aid
        graph=client.get('/api/graph',params={'dataset_id':did,'alert_id':aid}).json();assert graph['nodes'] and graph['edges']

def test_analysis_limit_enforced(tmp_path,monkeypatch):
    p=tmp_path/'x.csv';write_csv(p,[prepared(),prepared(),prepared()]);res=ingest.import_csv(p,'x',100)
    monkeypatch.setattr(config,'MAX_ANALYSIS_ROWS',2)
    with pytest.raises(ValueError,match='Narrow'):analysis.load_transactions(res['dataset_id'])

def test_alert_cap_preserves_later_high_priority_patterns():
    rows=[]
    for i in range(510):
        for k in range(3):rows.append(tx(f'{i}-{k}',f'S{i}-{k}',f'H{i}',i*100+k))
    rows.extend([tx('r1','X','Y',99900),tx('r2','Y','Z',99901),tx('r3','Z','X',99902)])
    found,limits=analysis.detect(rows,'timestamp',{'min_peers':3,'window':5,'patterns':['fan_in','cycle']})
    assert len(found)==500 and limits['alert_limit_reached']
    assert any(a['pattern']=='cycle' for a in found)

def test_initializing_cli_does_not_interrupt_existing_job():
    from backend.db import init_db
    with connection() as c:c.execute("INSERT INTO jobs VALUES('j','analysis','running',1,'work','x','x',NULL)")
    init_db()
    with connection() as c:assert c.execute("SELECT status FROM jobs WHERE id='j'").fetchone()[0]=='running'
    init_db(recover_jobs=True)
    with connection() as c:assert c.execute("SELECT status FROM jobs WHERE id='j'").fetchone()[0]=='interrupted'

def test_threshold_selection_uses_exact_validation_tail():
    y=np.array([0]*998+[1,0]);scores=np.linspace(0,.99,1000)
    threshold=ml.validation_threshold(y,scores)
    assert threshold==scores[998]
    assert ml.metrics(y,scores,threshold)['recall']==1
