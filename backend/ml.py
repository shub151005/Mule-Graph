"""Reproducible temporal evaluation; source labels are evaluation targets only."""
import io
import json
import uuid
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, confusion_matrix, precision_recall_curve
from . import config
from .analysis import load_transactions, causal_features, FEATURES
from .db import connection, encode, now, audit, using_postgres

def metrics(y, scores, threshold):
    pred=(scores>=threshold).astype(int)
    p,r,f,_=precision_recall_fscore_support(y,pred,average='binary',zero_division=0)
    return {'precision':float(p),'recall':float(r),'f1':float(f),
        'pr_auc':float(average_precision_score(y,scores)) if len(np.unique(y))==2 else None,
        'confusion_matrix':confusion_matrix(y,pred,labels=[0,1]).tolist(),'positive':int(y.sum()),'rows':len(y),
        'threshold':float(threshold),'prevalence':float(np.mean(y))}

def validation_threshold(y,scores):
    precision,recall,thresholds=precision_recall_curve(y,scores)
    f1=np.divide(2*precision[:-1]*recall[:-1],precision[:-1]+recall[:-1],out=np.zeros_like(precision[:-1]),where=(precision[:-1]+recall[:-1])!=0)
    # Exact validation thresholds matter for a ~0.1% positive class; coarse percentiles can miss its entire tail.
    best=np.flatnonzero(f1==f1.max())[-1]
    return float(thresholds[best])

def train(dataset_id, start, end, progress):
    ds,rows=load_transactions(dataset_id,start,end)
    if len(rows)<100:raise ValueError('At least 100 transactions are needed to train a model.')
    progress(15,'Computing features using only earlier transaction history')
    X=causal_features(rows);times=np.asarray([r['time'] for r in rows])
    boundary1=times[int(len(rows)*0.7)];boundary2=times[int(len(rows)*0.85)]
    train_idx=times<boundary1;val_idx=(times>=boundary1)&(times<boundary2);test_idx=times>=boundary2
    if min(sum(train_idx),sum(val_idx),sum(test_idx))<10:raise ValueError('Not enough distinct timestamps for disjoint train/validation/test periods.')
    progress(35,'Fitting Isolation Forest on the earliest 70% time boundary')
    iso=IsolationForest(n_estimators=120,max_samples=min(2048,int(sum(train_idx))),random_state=42,n_jobs=1)
    iso.fit(X[train_idx]);reference=-iso.score_samples(X[train_idx]);scores=-iso.score_samples(X)
    threshold=float(np.quantile(reference,0.99))
    with connection() as c:
        labels={r['entity_id']:r['label'] for r in c.execute("SELECT entity_id,label FROM labels WHERE dataset_id=? AND entity_type='transaction'",(dataset_id,))}
    y=np.asarray([labels.get(r['id'],-1) for r in rows]);labeled=y>=0
    card={'dataset_id':dataset_id,'dataset_name':ds['name'],'synthetic':True,'feature_names':FEATURES,
        'split':'Chronological approximately 70/15/15; equal timestamps never cross a split',
        'split_counts':{'train':int(sum(train_idx)),'validation':int(sum(val_idx)),'test':int(sum(test_idx))},
        'train_end':float(times[train_idx].max()),'test_start':float(times[test_idx].min()),'time_kind':ds['time_kind'],
        'labeled_rows':int(sum(labeled)),'supervised_status':'Unavailable: transaction labels with both classes required in all periods',
        'limitations':['Synthetic, source-specific evaluation; not real-world fraud accuracy','Account overlap across temporal splits is allowed; this is not an unseen-account benchmark',
        'This is a development holdout, not an independently blinded external benchmark',
        'Sample boundaries may omit historical context','No calibration or causal proof; do not use scores for automated adverse action'],
        'anomaly_threshold':threshold,'seed':42}
    test_labeled=test_idx&labeled
    if sum(test_labeled)>0:card['anomaly_test']=metrics(y[test_labeled],scores[test_labeled],threshold)
    classifier=None
    masks=[train_idx&labeled,val_idx&labeled,test_idx&labeled]
    if all(len(np.unique(y[m]))==2 for m in masks) and int(sum(y[masks[0]]==1))>=10:
        progress(60,'Training class-balanced supervised baseline; selecting threshold on validation only')
        classifier=RandomForestClassifier(n_estimators=120,max_depth=10,min_samples_leaf=4,class_weight='balanced',random_state=42,n_jobs=1)
        classifier.fit(X[masks[0]],y[masks[0]])
        val_scores=classifier.predict_proba(X[masks[1]])[:,1]
        best=validation_threshold(y[masks[1]],val_scores)
        test_scores=classifier.predict_proba(X[masks[2]])[:,1]
        card.update(supervised_status='Trained: Random Forest, class-balanced',supervised_threshold=float(best),
            validation=metrics(y[masks[1]],val_scores,best),test=metrics(y[masks[2]],test_scores,best),
            feature_importance=dict(zip(FEATURES,map(float,classifier.feature_importances_))))
    model_id=uuid.uuid4().hex[:16]
    model_object={'isolation':iso,'classifier':classifier,'reference':np.sort(reference),'threshold':threshold,
        'training_start':rows[0]['time'],'training_end':card['train_end'],'features':FEATURES}
    payload=io.BytesIO();joblib.dump(model_object,payload);artifact=payload.getvalue()
    # Local development keeps a convenient file copy. Cloud inference loads the
    # authoritative artifact from PostgreSQL, so Render's filesystem is disposable.
    if not using_postgres():
        directory=config.DATA_DIR/'models';directory.mkdir(exist_ok=True)
        joblib.dump(model_object,directory/f'{model_id}.joblib')
    with connection() as c:
        c.execute('INSERT INTO models(id,dataset_id,created_at,kind,metadata,artifact) VALUES(?,?,?,?,?,?)',
            (model_id,dataset_id,now(),'isolation_forest+optional_random_forest',encode(card),artifact))
        audit(c,'model.trained',model_id,{'dataset_id':dataset_id,'split_counts':card['split_counts']})
    return {'model_id':model_id,**card}

def score_latest(dataset_id,rows):
    with connection() as c:
        model=c.execute('SELECT id,dataset_id,created_at,kind,metadata,artifact FROM models WHERE dataset_id=? ORDER BY created_at DESC LIMIT 1',(dataset_id,)).fetchone()
    if not model:return [],'No trained model for this dataset. Train in Models first.'
    if model['artifact']:
        obj=joblib.load(io.BytesIO(bytes(model['artifact'])))
    else:
        # Compatibility for models trained before database-backed artifacts.
        legacy=config.DATA_DIR/'models'/f"{model['id']}.joblib"
        if not legacy.exists():return [],'The legacy model artifact is unavailable. Train the model again once.'
        obj=joblib.load(legacy)
    # Recreate consistent causal history from the training observation start.
    _,history=load_transactions(dataset_id,obj['training_start'],rows[-1]['time'])
    scores=-obj['isolation'].score_samples(causal_features(history))
    allowed={r['id'] for r in rows};reference=obj['reference']
    result=[]
    for r,s in zip(history,scores):
        if r['id'] in allowed and r['time']>obj['training_end'] and s>=obj['threshold']:
            result.append((r,100*float(np.searchsorted(reference,s))/len(reference)))
    result.sort(key=lambda x:x[1],reverse=True)
    return result[:50],f"Model {model['id']}; post-training timestamps only; top 50 anomalies maximum"
