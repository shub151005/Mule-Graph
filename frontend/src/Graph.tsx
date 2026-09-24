import {useEffect,useRef,useState} from 'react';
import cytoscape from 'cytoscape';
import {Maximize,Minus,Plus,Pause,Play,MousePointer2} from 'lucide-react';
import {Transaction,date} from './api';

export default function Graph({rows,onSelect,kind='timestamp'}:{rows:Transaction[];onSelect:(id:string)=>void;kind?:string}){
  const container=useRef<HTMLDivElement>(null);const cy=useRef<cytoscape.Core|null>(null);const select=useRef(onSelect);
  const [cursor,setCursor]=useState(100);const [playing,setPlaying]=useState(false);const [selected,setSelected]=useState('');
  select.current=onSelect;
  useEffect(()=>{
    if(!container.current)return;
    const ids=[...new Set(rows.flatMap(r=>[r.sender,r.receiver]))];
    cy.current=cytoscape({container:container.current,elements:[...ids.map(id=>({data:{id,label:id.length>23?id.slice(0,10)+'…'+id.slice(-8):id}})),...rows.map(r=>({data:{id:'edge:'+r.id,source:r.sender,target:r.receiver,label:`${Number(r.amount).toLocaleString()} ${r.currency||'unspecified'}`,time:r.time}}))],
      style:[{selector:'node',style:{'background-color':'#f9f5e8','border-color':'#a89c7b','border-width':1.5,width:39,height:39,label:'data(label)','font-family':'JetBrains Mono','font-size':10,color:'#49483e','text-valign':'bottom','text-margin-y':10,'text-background-color':'#f9f5e8','text-background-opacity':.94,'text-background-padding':'4px'}},
      {selector:'edge',style:{width:1.6,'line-color':'#b69a7b','target-arrow-color':'#b69a7b','target-arrow-shape':'triangle','curve-style':'bezier','arrow-scale':.8,opacity:.85}},
      {selector:'node:selected',style:{'background-color':'#ef705c','border-color':'#a83d2d','border-width':3,color:'#a83d2d'}},
      {selector:'edge:selected',style:{'line-color':'#a83d2d','target-arrow-color':'#a83d2d',width:2.5,label:'data(label)','font-size':11,'text-background-color':'#f9f5e8','text-background-opacity':1,'text-background-padding':'4px'}},
      {selector:'.hidden',style:{display:'none'}}],
      layout:{name:ids.length<=7||ids.length>35?'circle':'breadthfirst',directed:true,padding:65,spacingFactor:1.15,animate:false} as any,minZoom:.15,maxZoom:4,wheelSensitivity:.2});
    cy.current.on('tap','node',evt=>{setSelected(evt.target.id());select.current(evt.target.id())});
    setCursor(100);setPlaying(false);setSelected('');
    const observer=new ResizeObserver(()=>{cy.current?.resize()});observer.observe(container.current);
    return()=>{observer.disconnect();cy.current?.destroy()};
  },[rows]);
  useEffect(()=>{
    if(!playing)return;const timer=setInterval(()=>setCursor(c=>{if(c>=100){setPlaying(false);return 100}return Math.min(100,c+2)}),200);return()=>clearInterval(timer);
  },[playing]);
  const times=rows.map(r=>r.time);const low=Math.min(...times);const high=Math.max(...times);const at=low+(high-low)*cursor/100;
  useEffect(()=>{cy.current?.edges().forEach(e=>{e.toggleClass('hidden',e.data('time')>at)})},[at]);
  return <div className="graph-wrap">
    <div className="graph-toolbar"><span className="mono">DIRECTED / {numberLabel(rows.length)} EDGES</span><div>
      <button className="icon-btn" title="Zoom out" onClick={()=>cy.current?.zoom((cy.current?.zoom()||1)/1.3)}><Minus size={15}/></button>
      <button className="icon-btn" title="Zoom in" onClick={()=>cy.current?.zoom((cy.current?.zoom()||1)*1.3)}><Plus size={15}/></button>
      <button className="icon-btn" title="Fit graph" onClick={()=>cy.current?.fit(undefined,50)}><Maximize size={15}/></button></div></div>
    <div className="graph-canvas" ref={container}/>
    {!rows.length&&<div className="graph-empty">Select an alert to follow the evidence.</div>}
    <div className="graph-caption"><span><MousePointer2 size={12}/> {selected||'Select a node to inspect its account'}</span><span>↗ Transaction direction</span></div>
    {!!rows.length&&<div className="playback"><button className="icon-btn" aria-label={playing?'Pause timeline':'Play timeline'} onClick={()=>{if(cursor>=100)setCursor(0);setPlaying(!playing)}}>{playing?<Pause size={15}/>:<Play size={15}/>}</button><input aria-label="Graph timeline" type="range" min="0" max="100" value={cursor} onChange={e=>{setPlaying(false);setCursor(Number(e.target.value))}}/><span className="mono">{date(at,kind)}</span></div>}
  </div>
}
const numberLabel=(n:number)=>n.toLocaleString();
