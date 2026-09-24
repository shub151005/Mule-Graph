"""Streaming, provenance-preserving adapters. Labels never enter feature records."""
import csv
import gzip
import math
import random
import uuid
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from .db import connection, encode, now, audit
from . import config

def text_open(path):
    return gzip.open(path, 'rt', encoding='utf-8-sig', newline='') if str(path).endswith('.gz') else open(path, encoding='utf-8-sig', newline='')

def money(value, required=True):
    if value in (None,''):
        if required: raise ValueError('Missing amount')
        return ''
    d = Decimal(str(value))
    if not d.is_finite() or d < 0 or abs(d) > Decimal('1e18'): raise ValueError('Invalid or out-of-range amount')
    return str(d)

def normalize(row, n, did):
    if 'sender_account_id' in row:
        sender,receiver = row['sender_account_id'],row['receiver_account_id']
        stamp = row.get('timestamp_iso') or row.get('timestamp_raw','')
        step = row.get('time_step','')
        amount,currency = row.get('amount_paid',''),row.get('payment_currency','')
        received,rcurrency = row.get('amount_received',''),row.get('receiving_currency','')
        tid = row.get('transaction_id') or f'{did}:{n}'
        form = row.get('payment_format','')
    elif 'From Bank' in row:
        sender = f"{row['From Bank']}_{row['Account']}"
        receiver = f"{row['To Bank']}_{row['Account_receiver']}"
        stamp,step = row['Timestamp'],''
        amount,currency,received,rcurrency = (row[k] for k in ['Amount Paid','Payment Currency','Amount Received','Receiving Currency'])
        tid,form = f'{did}:{n}',row.get('Payment Format','')
    elif 'Sender_account' in row:
        sender,receiver = row['Sender_account'],row['Receiver_account']
        stamp,step = row['Date']+'T'+row['Time'],''
        amount,currency,received,rcurrency = row['Amount'],row['Payment_currency'],'',row['Received_currency']
        tid,form = f'{did}:{n}',row.get('Payment_type','')
    elif 'sourceNodeId' in row:
        sender,receiver=row['sourceNodeId'],row['targetNodeId']
        stamp,step='',row['time']
        amount,currency,received,rcurrency=row['value'],'','',''
        tid,form=f'{did}:{n}',''
    else:
        raise ValueError('Unsupported schema. Use the documented prepared CSV header or IBM/SAML/AMLSim raw schema.')
    if not sender or not receiver: raise ValueError('Missing account identifier')
    if max(len(sender),len(receiver),len(tid))>300: raise ValueError('Identifier exceeds 300 characters')
    if stamp:
        dt=datetime.fromisoformat(stamp.replace('/','-').replace('Z','+00:00'))
        # Naive dates are ordered on a neutral axis, not claimed to be UTC.
        moment=dt.replace(tzinfo=timezone.utc).timestamp() if dt.tzinfo is None else dt.timestamp()
        time_kind='timestamp'
    else:
        moment=float(step); time_kind='step'
    if not math.isfinite(moment): raise ValueError('Invalid time')
    label = row.get('Is Laundering',row.get('Is_laundering',row.get('label','')))
    return (did,tid,sender,receiver,moment,stamp,money(amount),currency,money(received,False),rcurrency,form,n,row.get('device_id','')),time_kind,label,row.get('Laundering_type','')

def import_csv(path, name, limit, progress=lambda *_:None, label_path=None, source='upload'):
    did=uuid.uuid4().hex[:16]
    accounts=set(); ids=set(); currencies=Counter(); missing=Counter(); rejects=[]
    low=float('inf'); high=-float('inf'); kinds=set(); accepted=0; rejected=0; seen=0; truncated=False
    tx_batch=[];label_batch=[]
    progress(5,'Reading and validating transaction records')
    with connection() as c:
        def flush():
            if tx_batch:
                c.executemany('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',tx_batch)
                tx_batch.clear()
            if label_batch:
                c.executemany('INSERT INTO labels VALUES(?,?,?,?,?)',label_batch)
                label_batch.clear()
        c.execute('INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?,?,?)',(did,name,source,now(),0,0,'',None,None,'{}'))
        with text_open(path) as stream:
            reader=csv.reader(stream); header=next(reader,None)
            if not header: raise ValueError('CSV is empty')
            if header.count('Account')==2:
                second=header.index('Account',header.index('Account')+1); header[second]='Account_receiver'
            for n,values in enumerate(reader,1):
                if n>limit: truncated=True; break
                seen=n
                try:
                    if len(values)!=len(header): raise ValueError('Column count mismatch')
                    tx,kind,label,typology=normalize(dict(zip(header,values)),n,did)
                    if tx[1] in ids: raise ValueError('Duplicate transaction identifier')
                    if kinds and kind not in kinds: raise ValueError('Mixed timestamp and step time axes are not supported')
                    kinds.add(kind); ids.add(tx[1]); accounts.update(tx[2:4]); currencies[tx[7] or 'Unspecified']+=1
                    for i,field in [(7,'currency'),(8,'amount_received'),(12,'device_id')]: missing[field]+=int(tx[i]=='')
                    low=min(low,tx[4]); high=max(high,tx[4])
                    tx_batch.append(tx);accepted+=1
                    if label in ('0','1'):
                        label_batch.append((did,'transaction',tx[1],int(label),typology))
                    if len(tx_batch)>=1000:flush()
                except (ValueError,InvalidOperation,OverflowError) as exc:
                    rejected+=1
                    if len(rejects)<100: rejects.append({'source_row':n,'reason':str(exc)})
        if not accepted: raise ValueError('No valid transaction rows. '+str(rejects[:3]))
        flush()
        # Sidecar streaming is intentionally separate from detection input.
        if label_path and Path(label_path).exists():
            with text_open(label_path) as stream:
                for row in csv.DictReader(stream):
                    etype,eid=row.get('entity_type'),row.get('entity_id')
                    if (etype=='transaction' and eid not in ids) or (etype=='account' and eid not in accounts): continue
                    if row.get('label_name') in ('Is Laundering','Is_laundering','isFraud') and row['label_value'] in ('0','1'):
                        c.execute('''INSERT INTO labels(dataset_id,entity_type,entity_id,label,typology) VALUES(?,?,?,?,?)
                            ON CONFLICT(dataset_id,entity_type,entity_id)
                            DO UPDATE SET label=excluded.label,typology=excluded.typology''',(did,etype,eid,int(row['label_value']),''))
                    elif row.get('label_name')=='Laundering_type':
                        c.execute('UPDATE labels SET typology=? WHERE dataset_id=? AND entity_type=? AND entity_id=?',(row['label_value'],did,etype,eid))
        labeled=c.execute('SELECT count(*) FROM labels WHERE dataset_id=?',(did,)).fetchone()[0]
        quality={'accepted':accepted,'rejected':rejected,'rejected_examples':rejects,'rows_examined':seen,'truncated':truncated,
                 'selection':'First source rows, then chronological ordering at query time; NOT representative sampling',
                 'currencies':dict(currencies),'missing':dict(missing),'labeled_entities':labeled,'synthetic':True,
                 'timezone':'Source timezone unspecified unless explicitly present; no local timezone inferred',
                 'limitations':['Synthetic/research data; not proof of criminal activity','Source-row subset can omit network context']}
        c.execute('UPDATE datasets SET rows=?,accounts=?,time_kind=?,min_time=?,max_time=?,quality=? WHERE id=?',
                  (accepted,len(accounts),next(iter(kinds)),low,high,encode(quality),did))
        audit(c,'dataset.imported',did,{'source':source,'accepted':accepted,'rejected':rejected})
    progress(95,'Dataset stored and indexed')
    return {'dataset_id':did,'rows':accepted,'rejected':rejected}

def import_local(source, limit, progress):
    path=config.SOURCES[source]
    if not path.exists(): raise ValueError('Local source is not installed on this server. Upload a prepared CSV instead.')
    labels=path.parent/('source_labels.csv.gz' if source=='ibm' else 'source_labels.csv')
    return import_csv(path,{'ibm':'IBM HI-Small','samld':'SAML-D','amlsim':'AMLSim 20K'}[source],limit,progress,labels,source)

def demo(progress=lambda *_:None):
    """Deterministic illustrative cases, not evaluation evidence for source datasets."""
    rng=random.Random(42); records=[]; base=datetime(2026,1,1)
    def add(s,r,t,amount,label=0,pattern='',device=''):
        records.append({'sender_account_id':s,'receiver_account_id':r,'timestamp_iso':t.isoformat(),
            'amount_paid':str(amount),'payment_currency':'USD','amount_received':str(amount),
            'receiving_currency':'USD','payment_format':'Transfer','label':str(label),'Laundering_type':pattern,'device_id':device})
    # Background traffic and legitimate high-degree business activity.
    for day in range(120):
        t=base+timedelta(days=day)
        for _ in range(35):
            add(f'PERSON-{rng.randrange(160):03}',f'MERCHANT-{rng.randrange(25):02}',t+timedelta(minutes=rng.randrange(1440)),round(rng.uniform(8,350),2))
        for k in range(8): add(f'CUSTOMER-{k}', 'BUSINESS-01',t+timedelta(hours=k+8),rng.randrange(50,500))
        add('BUSINESS-01','SUPPLIER-01',t+timedelta(hours=19),rng.randrange(200,900))
        if day%30==0:
            for k in range(15): add('EMPLOYER-01',f'PERSON-{k:03}',t+timedelta(hours=9,minutes=k*4),3200)
        if day%4==0:
            anchor=t+timedelta(hours=12)
            group=f'{day:03}'
            for k in range(6): add(f'ORIGIN-{group}-{k}',f'HUB-{group}',anchor+timedelta(seconds=k*30),10000+k*10,1,'Fan_In')
            add(f'HUB-{group}',f'PASS-{group}',anchor+timedelta(minutes=4),59000,1,'Deposit-Send')
            add(f'PASS-{group}',f'EXIT-{group}',anchor+timedelta(minutes=6),58000,1,'Deposit-Send')
            for k in range(6): add(f'EXIT-{group}',f'OUT-{group}-{k}',anchor+timedelta(minutes=7,seconds=k*20),9500,1,'Fan_Out')
            for k in range(3): add(f'RING-{group}-{k}',f'RING-{group}-{(k+1)%3}',anchor+timedelta(minutes=20+k*2),7000-k*20,1,'Cycle')
            for k in range(4): add(f'LINK-{group}-{k}','COLLECTOR',anchor+timedelta(minutes=30+k),3000,1,'Shared_Device',f'DEVICE-{group}')
    add('DORMANT-01','MERCHANT-01',base,20)
    add('ORIGIN-D','DORMANT-01',base+timedelta(days=110),50000,1,'Dormant')
    add('DORMANT-01','EXIT-D',base+timedelta(days=110,minutes=3),49000,1,'Dormant')
    records.sort(key=lambda r:r['timestamp_iso'])
    config.DATA_DIR.mkdir(parents=True,exist_ok=True)
    path=config.DATA_DIR/'illustrative-demo.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    return import_csv(path,'Illustrative research sandbox',len(records),progress,source='illustrative_demo')
