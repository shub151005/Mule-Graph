"""Local-only batch entry points. No arbitrary file paths accepted over HTTP."""
import argparse
import json
from . import ingest, analysis, ml
from .db import init_db

def main():
    parser=argparse.ArgumentParser(description='MuleGraph local data and ML tools')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('demo')
    p=sub.add_parser('import');p.add_argument('--source',choices=['ibm','samld','amlsim']);p.add_argument('--csv');p.add_argument('--labels');p.add_argument('--name',default='Research collection');p.add_argument('--limit',type=int,default=25000)
    p=sub.add_parser('analyze');p.add_argument('dataset_id');p.add_argument('--window',type=float,default=900)
    p=sub.add_parser('train');p.add_argument('dataset_id')
    args=parser.parse_args();init_db()
    progress=lambda n,s:print(f'{n}% {s}',flush=True)
    if args.command=='demo':
        result=ingest.demo(progress);result['analysis']=analysis.analyze(result['dataset_id'],{'window':900},progress)
    elif args.command=='import':
        if args.source:result=ingest.import_local(args.source,args.limit,progress)
        elif args.csv:result=ingest.import_csv(args.csv,args.name,args.limit,progress,args.labels,'local_custom')
        else:parser.error('Supply --source or --csv')
    elif args.command=='analyze':result=analysis.analyze(args.dataset_id,{'window':args.window},progress)
    else:result=ml.train(args.dataset_id,None,None,progress)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
