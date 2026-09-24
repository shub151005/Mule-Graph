import json
import math
import time
import uuid
import heapq
from collections import defaultdict, deque, Counter
from decimal import Decimal
import numpy as np
from . import config
from .db import connection, encode, now, audit

FEATURES=['log_amount','sender_prior_out','sender_prior_in','receiver_prior_in','sender_prior_counterparties',
          'seconds_or_steps_since_sender_activity','amount_vs_sender_prior_mean','self_transfer']

def load_transactions(dataset_id, start=None, end=None):
    clauses=['dataset_id=?']; args=[dataset_id]
    if start is not None: clauses.append('time>=?');args.append(start)
    if end is not None: clauses.append('time<=?');args.append(end)
    with connection() as c:
        ds=c.execute('SELECT * FROM datasets WHERE id=?',(dataset_id,)).fetchone()
        if ds is None: raise ValueError('Dataset not found')
        records=c.execute('SELECT * FROM transactions WHERE '+' AND '.join(clauses)+' ORDER BY time,id LIMIT ?',args+[config.MAX_ANALYSIS_ROWS+1]).fetchall()
    if len(records)>config.MAX_ANALYSIS_ROWS:
        raise ValueError(f'Window exceeds {config.MAX_ANALYSIS_ROWS:,} records. Narrow the time window or raise MAX_ANALYSIS_ROWS on a sufficiently sized server.')
    if not records: raise ValueError('No transactions in the selected window')
    return dict(ds),[dict(r) for r in records]

def causal_features(rows):
    outgoing=Counter();incoming=Counter();totals=defaultdict(float);last={};partners=defaultdict(set)
    result=[]
    # Equal-time transactions use identical pre-timestamp history; row ordering cannot imply causality.
    i=0
    while i<len(rows):
        j=i+1
        while j<len(rows) and rows[j]['time']==rows[i]['time']: j+=1
        for r in rows[i:j]:
            key=(r['sender'],r['currency']); recv=(r['receiver'],r['receiving_currency'] or r['currency'])
            amount=float(r['amount']);mean=totals[key]/max(1,outgoing[key])
            gap=max(0,r['time']-last.get(r['sender'],r['time']))
            result.append([math.log1p(amount),math.log1p(outgoing[key]),math.log1p(incoming[key]),math.log1p(incoming[recv]),
                math.log1p(len(partners[key])),math.log1p(gap),min(amount/max(mean,1),1000),float(r['sender']==r['receiver'])])
        for r in rows[i:j]:
            key=(r['sender'],r['currency']);recv=(r['receiver'],r['receiving_currency'] or r['currency'])
            outgoing[key]+=1;incoming[recv]+=1;totals[key]+=float(r['amount']);partners[key].add(r['receiver'])
            last[r['sender']]=last[r['receiver']]=r['time']
        i=j
    return np.asarray(result,dtype=float)

def detect(rows, time_kind, settings):
    window=settings.get('window',900); min_peers=settings.get('min_peers',5); ratio=settings.get('pass_ratio',0.8)
    requested=set(settings.get('patterns',['fan_in','fan_out','pass_through','cycle','burst','dormant','shared_device']))
    alert_heap=[];seen=set();cooldown={};limit=500;truncated=False;cycle_budget=0;generated=0
    def emit(pattern,txs,score,explanation,evidence):
        nonlocal truncated,generated
        if pattern not in requested: return
        key=(pattern,tuple(sorted(t['id'] for t in txs)))
        if key in seen: return
        seen.add(key)
        generated+=1
        accounts=sorted({x for t in txs for x in (t['sender'],t['receiver'])})
        totals=defaultdict(Decimal)
        for t in txs: totals[t['currency'] or 'Unspecified']+=Decimal(t['amount'])
        candidate={'pattern':pattern,'severity':'High' if score>=75 else 'Medium','score':score,
            'title':pattern.replace('_',' ').title(),'explanation':explanation,'accounts':accounts,
            'transaction_ids':[t['id'] for t in txs], 'evidence':{**evidence,'start':min(t['time'] for t in txs),
            'end':max(t['time'] for t in txs),'amounts_by_currency':{k:str(v) for k,v in totals.items()},
            'score_meaning':'Heuristic priority, not probability of fraud','time_unit':'seconds' if time_kind=='timestamp' else 'simulation steps'}}
        entry=(score,generated,candidate)
        if len(alert_heap)<limit:heapq.heappush(alert_heap,entry)
        else:
            truncated=True
            if entry[:2]>alert_heap[0][:2]:heapq.heapreplace(alert_heap,entry)
    ins=defaultdict(deque);outs=defaultdict(deque);recent=defaultdict(deque);last_activity={};devices=defaultdict(deque)
    for r in rows:
        s,t,moment=r['sender'],r['receiver'],r['time']
        if s==t: continue
        paid_currency=r['currency'];received_currency=r['receiving_currency'] or paid_currency
        for table,key in [(ins,(s,paid_currency)),(ins,(t,received_currency)),(outs,(s,paid_currency)),(recent,s)]:
            while table[key] and moment-table[key][0]['time']>window: table[key].popleft()
        # Compare received amount at the intermediate account against outgoing paid amount.
        if paid_currency and 'pass_through' in requested:
            for prev in reversed(ins[(s,paid_currency)]):
                prior=Decimal(prev['received'] or (prev['amount'] if prev['currency']==prev['receiving_currency'] else '0'))
                delta=moment-prev['time']
                if prior>0 and 0<delta<=window and prev['sender']!=t and ratio<=Decimal(r['amount'])/prior<=Decimal('1.05'):
                    emit('pass_through',[prev,r],80,'Comparable funds entered and left the intermediate account within the configured window. This is temporal evidence, not proof of fund provenance.',
                         {'account':s,'elapsed':delta,'forwarded_ratio':round(float(Decimal(r['amount'])/prior),4),'minimum_ratio':ratio,'window':window})
                    break
        ins[(t,received_currency)].append(r);outs[(s,paid_currency)].append(r);recent[s].append(r)
        for pattern,txs,peer,account in [('fan_in',ins[(t,received_currency)],'sender',t),('fan_out',outs[(s,paid_currency)],'receiver',s)]:
            if len({x[peer] for x in txs})>=min_peers and moment-cooldown.get((pattern,account),-1e30)>window:
                emit(pattern,list(txs),65,f'{len({x[peer] for x in txs})} distinct counterparties within the configured window. Legitimate business activity can have the same shape.',
                     {'account':account,'distinct_counterparties':len({x[peer] for x in txs}),'minimum_counterparties':min_peers,'window':window})
                cooldown[(pattern,account)]=moment
        if len(recent[s])>=settings.get('burst_count',8) and moment-cooldown.get(('burst',s),-1e30)>window:
            emit('burst',list(recent[s]),60,'Outgoing activity exceeded the configured count threshold; investigate against the account context.',{'count':len(recent[s]),'window':window})
            cooldown[('burst',s)]=moment
        if time_kind=='timestamp' and s in last_activity and moment-last_activity[s]>=settings.get('dormant_days',90)*86400:
            emit('dormant',[r],65,'Activity resumed after a long gap in the imported observation window. Missing history can create apparent dormancy.',{'observed_gap_days':round((moment-last_activity[s])/86400,2)})
        # Check receiver activation too, before updating either activity timestamp.
        if time_kind=='timestamp' and t in last_activity and moment-last_activity[t]>=settings.get('dormant_days',90)*86400:
            emit('dormant',[r],65,'Incoming activity resumed after a long observed gap. This does not establish bank-defined dormancy.',{'observed_gap_days':round((moment-last_activity[t])/86400,2)})
        last_activity[s]=last_activity[t]=moment
        if r.get('device_id'):
            q=devices[r['device_id']]
            while q and moment-q[0]['time']>window:q.popleft()
            q.append(r)
            if len({x['sender'] for x in q})>=3 and moment-cooldown.get(('shared_device',r['device_id']),-1e30)>window:
                emit('shared_device',list(q),70,'Multiple sending accounts used a supplied device identifier. Shared devices may have legitimate explanations.',{'device_id':r['device_id'],'window':window})
                cooldown[('shared_device',r['device_id'])]=moment
    # Bounded, strictly time-increasing cycles. Never enumerate all graph cycles.
    cycle_limited=False
    if 'cycle' in requested:
        import bisect
        by_sender=defaultdict(list)
        for r in rows:
            if r['sender']!=r['receiver']:by_sender[r['sender']].append(r)
        times={k:[x['time'] for x in v] for k,v in by_sender.items()}
        for start in rows:
            if start['sender']==start['receiver']:continue
            stack=[([start],{start['sender'],start['receiver']})]
            while stack:
                path,visited=stack.pop();last=path[-1];candidates=by_sender[last['receiver']]
                idx=bisect.bisect_right(times.get(last['receiver'],[]),last['time'])
                for nxt in candidates[idx:idx+100]:
                    cycle_budget+=1
                    if cycle_budget>200000:cycle_limited=True;break
                    if nxt['time']-start['time']>window:break
                    if not start['currency'] or nxt['currency']!=start['currency'] or nxt['receiving_currency'] not in ('',start['currency']):continue
                    if nxt['receiver']==start['sender'] and len(path)>=1:
                        emit('cycle',path+[nxt],85,'A strictly time-ordered path returned to its starting account. Examine business context before escalation.',{'hops':len(path)+1,'window':window})
                    elif nxt['receiver'] not in visited and len(path)<3:
                        stack.append((path+[nxt],visited|{nxt['receiver']}))
                if cycle_limited:break
            if cycle_limited:break
    alerts=[entry[2] for entry in sorted(alert_heap,reverse=True)]
    return alerts,{'alert_limit_reached':truncated,'generated_candidates':generated,
        'selection':'Top 500 heuristic-priority candidates across the full window; ties favor later candidates',
        'cycle_search_budget_reached':cycle_limited,
        'cycle_search_limits':'2–4 hops; up to 100 next edges per expansion; 200,000 edge expansions',
        'unavailable_patterns':(['shared_device'] if not any(r.get('device_id') for r in rows) else [])+(['dormant'] if time_kind=='step' else [])}

def analyze(dataset_id, settings, progress):
    started=time.perf_counter();ds,rows=load_transactions(dataset_id,settings.get('start'),settings.get('end'))
    progress(15,f'Analyzing {len(rows):,} chronologically ordered transactions')
    alerts,limits=detect(rows,ds['time_kind'],settings)
    progress(65,'Combining pattern evidence and optional anomaly model')
    ml_status='not_requested'
    if settings.get('use_ml',False):
        from .ml import score_latest
        results,ml_status=score_latest(dataset_id,rows)
        for r,score in results:
            if len(alerts)>=500: limits['alert_limit_reached']=True;break
            alerts.append({'pattern':'ml_anomaly','severity':'Medium','score':round(score,1),'title':'ML anomaly',
                'explanation':'An Isolation Forest model marked this transaction as unusual relative to its training history. This is not a fraud probability.',
                'accounts':list(dict.fromkeys([r['sender'],r['receiver']])),'transaction_ids':[r['id']],
                'evidence':{'score_meaning':'Training-reference anomaly percentile, not fraud probability','model_status':ml_status,'start':r['time'],'end':r['time']}})
    run_id=uuid.uuid4().hex[:16]
    summary={'transactions':len(rows),'alerts':len(alerts),'flagged_accounts':len({a for x in alerts for a in x['accounts']}),
        'patterns':dict(Counter(x['pattern'] for x in alerts)),'seconds':round(time.perf_counter()-started,3),
        'limits':limits,'ml_status':ml_status,'window_start':rows[0]['time'],'window_end':rows[-1]['time'],'time_kind':ds['time_kind']}
    with connection() as c:
        labels=[dict(r) for r in c.execute('SELECT entity_type,entity_id,label FROM labels WHERE dataset_id=?',(dataset_id,))]
    # Evaluate only observed labeled entities, never feed ground truth into detection.
    level='transaction' if any(x['entity_type']=='transaction' for x in labels) else 'account'
    observed={r['id'] for r in rows} if level=='transaction' else {a for r in rows for a in (r['sender'],r['receiver'])}
    predicted={tid for a in alerts for tid in a['transaction_ids']} if level=='transaction' else {n for a in alerts for n in a['accounts']}
    truth={x['entity_id']:x['label'] for x in labels if x['entity_type']==level and x['entity_id'] in observed}
    if truth:
        tp=sum(y==1 and eid in predicted for eid,y in truth.items());fp=sum(y==0 and eid in predicted for eid,y in truth.items())
        fn=sum(y==1 and eid not in predicted for eid,y in truth.items());tn=sum(y==0 and eid not in predicted for eid,y in truth.items())
        summary['evaluation']={'entity_type':level,'labeled_entities':len(truth),'precision':tp/(tp+fp) if tp+fp else 0,
            'recall':tp/(tp+fn) if tp+fn else 0,'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
            'confusion_matrix':[[tn,fp],[fn,tp]],'positive':tp+fn,
            'scope':'In-window descriptive rule evaluation, not an untouched model test; every participating entity is treated as flagged'}
    with connection() as c:
        c.execute('INSERT INTO runs VALUES(?,?,?,?,?)',(run_id,dataset_id,now(),encode(settings),encode(summary)))
        for a in alerts:
            aid='MG-'+uuid.uuid4().hex[:10].upper()
            c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(aid,run_id,dataset_id,a['pattern'],a['severity'],a['score'],a['title'],a['explanation'],encode(a['accounts']),encode(a['transaction_ids']),encode(a['evidence']),'New'))
        audit(c,'analysis.completed',run_id,summary)
    return {'run_id':run_id,**summary}
