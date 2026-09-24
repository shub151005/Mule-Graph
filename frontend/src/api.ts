export const API = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
export const key = () => sessionStorage.getItem('mulegraph-key') || '';
export async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string,string> = {'X-API-Key':key(),...(options.body instanceof FormData?{}:{'Content-Type':'application/json'})};
  const response=await fetch(API+'/api'+path,{...options,headers:{...headers,...options.headers}});
  if(!response.ok){let detail;try{detail=(await response.json()).detail}catch{detail=response.statusText}throw new Error(typeof detail==='string'?detail:JSON.stringify(detail));}
  return response.json();
}
export async function download(alertId:string, format:string){
  const res=await fetch(`${API}/api/export/${encodeURIComponent(alertId)}?format=${format}`,{headers:{'X-API-Key':key()}});
  if(!res.ok)throw new Error('Export failed');
  const url=URL.createObjectURL(await res.blob());const a=document.createElement('a');a.href=url;a.download=`${alertId}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export const post=(path:string,body?:unknown)=>request(path,{method:'POST',body:body===undefined?undefined:JSON.stringify(body)});
export type Dataset={id:string;name:string;source:string;rows:number;accounts:number;time_kind:string;min_time:number;max_time:number;quality:any};
export type Transaction={id:string;sender:string;receiver:string;time:number;timestamp:string;amount:string;currency:string;payment_format:string;received:string;receiving_currency:string};
export type Alert={id:string;dataset_id:string;run_id:string;pattern:string;severity:string;score:number;title:string;explanation:string;accounts:string[];transaction_ids:string[];evidence:any;status:string;transactions?:Transaction[];notes?:{id:number;body:string;created_at:string}[]};
export const number=(n:number|undefined)=>n===undefined?'—':n.toLocaleString();
export const human=(s:string)=>s.replaceAll('_',' ');
export const date=(value:number,kind='timestamp')=>kind==='step'?`Step ${value}`:new Date(value*1000).toISOString().replace('T',' ').slice(0,16);
