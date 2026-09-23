import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const apiUrl = path => `${API_BASE_URL}${path}`

const emptyOrder = () => ({ symbol:'', expiry:'', strike:'', option_type:'CE', side:'SELL', entry_price:'', lots:1 })
const money = value => value === null || value === undefined ? '—' : `${value >= 0 ? '+' : '-'}₹${Math.abs(value).toFixed(2)}`
const num = (value, digits=2) => value === null || value === undefined ? '—' : Number(value).toFixed(digits)
const pct = value => value === null || value === undefined ? '—' : `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`

function RiskChart({ history=[], events=[], entrySpot=null }) {
  const validHistory = history.filter(x => x.spot != null)
  if (validHistory.length < 2) return <div className="chart-empty"><strong>Building risk history</strong><span>Live underlying prices are captured every minute. The chart will appear after two valid snapshots.</span></div>
  const width=920, height=280, pad=42
  const scores=history.map(x=>Number(x.risk_score)||0)
  const baseSpot=entrySpot ?? validHistory[0].spot
  const changes=history.map(x=>x.spot != null && baseSpot ? ((x.spot/baseSpot)-1)*100 : null)
  const maxC=Math.max(1,...changes.filter(v=>v!=null).map(Math.abs))
  const x=i=>pad+i*(width-pad*2)/(Math.max(1,history.length-1))
  const y=v=>height-pad-(v/100)*(height-pad*2)
  const yc=v=>height-pad-((v+maxC)/(2*maxC))*(height-pad*2)
  const points=arr=>arr.map((v,i)=>v==null?'':x(i)+','+y(v)).filter(Boolean).join(' ')
  const pointsC=changes.map((v,i)=>v==null?'':x(i)+','+yc(v)).filter(Boolean).join(' ')
  const nearestIndex=ts=>{let best=0,bestDiff=Infinity;history.forEach((h,i)=>{const d=Math.abs(new Date(h.timestamp)-new Date(ts));if(d<bestDiff){best=i;bestDiff=d}});return best}
  return <div className="chart-wrap">
    <div className="chart-heading"><div><strong>Risk timeline</strong><span>Risk starts at 0 at entry. Spot change is measured from the captured entry spot.</span></div><div className="chart-entry"><span>Entry baseline</span><b>{baseSpot ? '₹'+num(baseSpot) : '—'}</b></div></div>
    <svg viewBox={'0 0 '+width+' '+height} className="risk-chart" role="img">
      <line x1={pad} x2={width-pad} y1={y(70)} y2={y(70)} className="grid-critical" />
      <line x1={pad} x2={width-pad} y1={y(40)} y2={y(40)} className="grid-warning" />
      <line x1={pad} x2={width-pad} y1={y(0)} y2={y(0)} className="grid-zero" />
      <polyline points={points(scores)} fill="none" className="risk-line" />
      {pointsC && <polyline points={pointsC} fill="none" className="spot-line" />}
      {events.map((e,n)=>{const i=nearestIndex(e.timestamp);return <g key={e.timestamp+'-'+e.event_type+'-'+n}><circle cx={x(i)} cy={y(scores[i])} r="4" className="event-dot"/><text x={x(i)+6} y={y(scores[i])-8} className="svg-label">{e.event_type.replaceAll('_',' ')}</text></g>})}
      <text x={pad+5} y={y(70)-7} className="svg-label">70 Critical</text>
      <text x={pad+5} y={y(40)-7} className="svg-label">40 Warning</text>
      <text x={pad+5} y={y(0)-7} className="svg-label">0 Entry</text>
      <text x={width-pad-75} y={18} className="svg-label">Risk / 100</text>
    </svg>
    <div className="chart-legend"><span><i className="legend-risk"/> Risk score</span><span><i className="legend-spot"/> Spot change %</span></div>
    <div className="event-list">{events.slice(-8).reverse().map((e,i)=><span key={i}><b>{e.event_type.replaceAll('_',' ')}</b> · {new Date(e.timestamp).toLocaleTimeString()} · {e.message}</span>)}</div>
  </div>
}

function RiskPanel({ strategy }) {
  const [risk,setRisk]=useState(null)
  const load=async()=>{ const r=await fetch(apiUrl('/api/strategies/'+strategy.id+'/risk')); if(r.ok)setRisk(await r.json()) }
  useEffect(()=>{ load(); const t=setInterval(load,5000); return()=>clearInterval(t)},[strategy.id])
  if(!risk) return <div className="risk-loading">Loading risk engine…</div>
  const band=risk.risk_band.toLowerCase()
  const probability=risk.probability
  return <div className="risk-panel">
    <div className="risk-top"><div><div className="eyebrow">RISK ENGINE</div><h3>Strategy health</h3><p>Monitoring only · no real orders are placed</p></div><div className={'risk-badge '+band}><span className="risk-dot"/>{risk.risk_band}<b>{num(risk.risk_score,0)}/100</b></div></div>
    <div className="risk-section"><div className="risk-section-title"><strong>Market position</strong><span>Current values</span></div><div className="risk-grid">
      <div className="risk-card primary-metric current-spot-card"><span>Current spot</span><strong>{risk.spot==null?'Waiting…':'₹'+num(risk.spot)}</strong><small>Live underlying price · now</small></div>
      <div className="risk-card entry-spot-card"><span>Entry baseline</span><strong>{risk.entry_spot==null?'Waiting…':'₹'+num(risk.entry_spot)}</strong><small>{risk.entry_spot_source || 'Underlying entry reference'} · Change: {pct(risk.spot_change_pct)}</small></div>
      <div className="risk-card"><span>Expected move</span><strong>{risk.expected_move==null?'—':'±₹'+num(risk.expected_move)}</strong><small>Estimated 1σ range</small></div>
      <div className="risk-card"><span>Nearest short</span><strong>{risk.distance_to_short_pct==null?'—':num(risk.distance_to_short_pct)+'%'}</strong><small>Distance from spot</small></div>
      <div className="risk-card"><span>Average IV</span><strong>{risk.avg_iv==null?'—':num(risk.avg_iv*100,1)+'%'}</strong><small>From live option premium</small></div>
    </div></div>
    <div className="risk-section"><div className="risk-section-title"><strong>Strategy Greeks</strong><span>Signed across all open legs</span></div><div className="greek-grid">{[['Delta',risk.delta],['Gamma',risk.gamma],['Theta',risk.theta],['Vega',risk.vega]].map(([k,v])=><div className="metric" key={k}><span>{k}</span><strong>{num(v,3)}</strong></div>)}</div></div>
    <div className="risk-section"><div className="risk-section-title"><strong>Risk drivers</strong><span>0 = low contribution · 100 = high contribution</span></div><div className="component-grid">{Object.entries(risk.components||{}).map(([k,v])=><div className="component" key={k}><div className="component-label"><span>{k.replaceAll('_',' ')}</span><b>{num(v,0)}</b></div><div className="meter"><span style={{width:Math.max(0,Math.min(100,v))+'%'}}/></div></div>)}</div></div>
    <div className="risk-section"><div className="risk-section-title"><strong>Technical context</strong><span>Underlying 1-minute data · live</span></div><div className="tech-row">{Object.entries(risk.technical||{}).map(([k,v])=><span key={k}>{k.replaceAll('_',' ')} <b>{num(v,2)}</b></span>)}</div></div>
    <RiskChart history={risk.history} events={risk.events || []} entrySpot={risk.entry_spot}/>
    <div className="risk-section">{probability && probability.buckets?.length ? <div className="probability"><div><strong>Historical calibration</strong><span>{probability.sample_count} snapshots · strategy-specific observations</span></div><div className="prob-grid">{probability.buckets.map(b=><div key={b.risk_min}><span>Risk {b.risk_min}–{b.risk_max}</span><b>{b.event_rate_pct}%</b><small>{b.observations} observations</small></div>)}</div></div> : <div className="probability muted"><strong>Historical probability: not available yet</strong><span>The engine calculates this only after enough real strategy snapshots. Nothing is hardcoded.</span></div>}</div>
    <div className="risk-foot"><b>How to read:</b> Risk score combines short-strike distance, strategy Greeks, IV and technical pressure. It is a monitoring score, not a probability of loss or a trading signal.</div>
  </div>
}
function StrategyCard({strategy,onDelete,pnlClass,onAction}) {
  return <article className="strategy card">
    <div className="strategy-head"><div><div className="strategy-id">STRATEGY #{strategy.id} · {strategy.status}</div><h2>{strategy.name}</h2><p>{strategy.description||'No description'}</p></div><div className="actions"><div><div className="hint">{strategy.priced_legs}/{strategy.total_legs} legs priced</div><strong className={`strategy-pnl ${pnlClass(strategy.pnl)}`}>{money(strategy.pnl)}</strong></div>{strategy.status==='OPEN'&&<button className="danger" onClick={()=>onAction(strategy.id,'exit')}>Exit</button>}<button className="danger" onClick={()=>onDelete(strategy.id)}>Delete</button></div></div>
    <div className="table-wrap"><table><thead><tr><th>Leg</th><th>Side</th><th>Entry</th><th>LTP</th><th>Lots</th><th>Lot size</th><th>Qty</th><th>P&L</th><th/></tr></thead><tbody>{strategy.orders.map(o=><tr key={o.id}><td><strong>{o.symbol} {o.strike} {o.option_type}</strong><small>{o.trading_symbol||o.instrument_key}</small></td><td><span className={`badge ${o.side.toLowerCase()}`}>{o.side}</span></td><td>₹{o.entry_price.toFixed(2)}</td><td>{o.current_ltp==null?'—':`₹${o.current_ltp.toFixed(2)}`}</td><td>{o.lots}</td><td>{o.lot_size}</td><td>{o.quantity}</td><td className={o.pnl==null?'':pnlClass(o.pnl)}>{money(o.pnl)}</td><td>{strategy.status==='OPEN'&&o.status==='OPEN'&&<button className="danger" onClick={()=>onAction(strategy.id,'close',o.id)}>Close</button>}</td></tr>)}</tbody></table></div>
    <RiskPanel strategy={strategy}/>
  </article>
}

function App(){
  const [dashboard,setDashboard]=useState({strategies:[],total_pnl:0,open_orders:0,market_data_mode:'upstox'})
  const [market,setMarket]=useState({status:'DISCONNECTED',mode:'upstox',subscribed:[],last_error:null})
  const [name,setName]=useState(''),[description,setDescription]=useState(''),[orders,setOrders]=useState([emptyOrder()]),[message,setMessage]=useState(''),[loading,setLoading]=useState(false),[connecting,setConnecting]=useState(false)
  const refresh=async()=>{try{const [d,m]=await Promise.all([fetch(apiUrl('/api/dashboard')),fetch(apiUrl('/api/market/status'))]);if(d.ok)setDashboard(await d.json());if(m.ok)setMarket(await m.json())}catch(e){setMessage(`Backend unavailable: ${e.message}`)}}
  useEffect(()=>{refresh();const t=setInterval(refresh,1500);return()=>clearInterval(t)},[])
  const createStrategy=async e=>{e.preventDefault();setLoading(true);setMessage('');try{const normalized=orders.map(o=>({...o,strike:Number(o.strike),entry_price:Number(o.entry_price),lots:Number(o.lots)}));const r=await fetch(apiUrl('/api/strategies'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description,orders:normalized})});const b=await r.json();if(!r.ok)throw new Error(b.detail||'Failed');setName('');setDescription('');setOrders([emptyOrder()]);setMessage(`Created paper strategy #${b.id}`);await refresh()}catch(e){setMessage(e.message)}finally{setLoading(false)}}
  const connectMarket=async()=>{setConnecting(true);try{const r=await fetch(apiUrl('/api/market/connect'),{method:'POST'});const b=await r.json();if(!r.ok)throw new Error(b.detail||'Market connection failed');setMessage(b.message||`Subscribed to ${b.subscribed} instrument(s)`);await refresh()}catch(e){setMessage(e.message)}finally{setConnecting(false)}}
  const deleteStrategy=async id=>{if(!window.confirm('Delete this paper strategy and its risk history?'))return;const r=await fetch(apiUrl(`/api/strategies/${id}`),{method:'DELETE'});if(r.ok)refresh()}
  const strategyAction=async(id,action,orderId)=>{const message=action==='exit'?'Exit this paper strategy?':'Close this paper leg?';if(!window.confirm(message))return;const path=action==='exit'?'/exit':'/adjust';const body=action==='exit'?{reason:'Manual paper exit'}:{action:'CLOSE_LEG',order_id:orderId,reason:'Manual paper adjustment'};const r=await fetch(apiUrl(`/api/strategies/${id}${path}`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok){const b=await r.json();setMessage(b.detail||'Action failed');return}await refresh()}
  const updateOrder=(i,f,v)=>setOrders(c=>c.map((o,j)=>j===i?{...o,[f]:v}:o)); const addOrder=()=>setOrders(c=>[...c,emptyOrder()]); const removeOrder=i=>setOrders(c=>c.length===1?c:c.filter((_,j)=>j!==i))
  const pnlClass=v=>v>=0?'positive':'negative'; const connectionClass=market.status.includes('CONNECTED')?'connected':market.status.startsWith('ERROR')?'error':'connecting'
  return <div className="app"><header><div><div className="eyebrow">PAPER TRADING TERMINAL · RISK ENGINE</div><h1>Paper Trader</h1><p>Multi-leg NSE options tracker · live market data · paper only</p></div><div className={`status ${connectionClass}`}><span className="dot"/>{market.status}</div></header><main>
    <section className="toolbar panel"><div><strong>Upstox Market Data</strong><span className="hint">{market.subscribed.length} instrument(s) subscribed · underlying feed included for risk</span></div><button className="primary" onClick={connectMarket} disabled={connecting}>{connecting?'Connecting…':'Connect / Refresh Feed'}</button></section>
    {market.last_error&&<div className="error-box"><strong>Market data error:</strong> {market.last_error}</div>}
    <section className="stats"><div className="card"><span>Total Paper P&L</span><strong className={pnlClass(dashboard.total_pnl)}>{money(dashboard.total_pnl)}</strong></div><div className="card"><span>Strategies</span><strong>{dashboard.strategies.length}</strong></div><div className="card"><span>Open Legs</span><strong>{dashboard.open_orders}</strong></div><div className="card"><span>Feed</span><strong>{dashboard.market_data_mode.toUpperCase()}</strong></div></section>
    <section className="panel"><div className="panel-title"><div><h2>Create Strategy</h2><span>Any combination of CE/PE BUY/SELL legs. Risk tracking begins immediately.</span></div></div><form onSubmit={createStrategy}><div className="grid2"><label>Strategy name<input required value={name} onChange={e=>setName(e.target.value)} placeholder="INFY Short Strangle"/></label><label>Description<input value={description} onChange={e=>setDescription(e.target.value)} placeholder="Optional"/></label></div><div className="orders-header"><h3>Paper legs</h3><button type="button" onClick={addOrder}>+ Add leg</button></div><div className="table-wrap"><table><thead><tr><th>Symbol</th><th>Expiry</th><th>Strike</th><th>Type</th><th>Side</th><th>Entry</th><th>Lots</th><th/></tr></thead><tbody>{orders.map((o,i)=><tr key={i}><td><input required value={o.symbol} onChange={e=>updateOrder(i,'symbol',e.target.value)} placeholder="INFY"/></td><td><input required type="date" value={o.expiry} onChange={e=>updateOrder(i,'expiry',e.target.value)}/></td><td><input required type="number" min="0.01" step="0.01" value={o.strike} onChange={e=>updateOrder(i,'strike',e.target.value)}/></td><td><select value={o.option_type} onChange={e=>updateOrder(i,'option_type',e.target.value)}><option>CE</option><option>PE</option></select></td><td><select value={o.side} onChange={e=>updateOrder(i,'side',e.target.value)}><option>SELL</option><option>BUY</option></select></td><td><input required type="number" min="0" step="0.01" value={o.entry_price} onChange={e=>updateOrder(i,'entry_price',e.target.value)}/></td><td><input required type="number" min="1" step="1" value={o.lots} onChange={e=>updateOrder(i,'lots',e.target.value)}/></td><td><button className="danger" type="button" onClick={()=>removeOrder(i)}>×</button></td></tr>)}</tbody></table></div><div className="form-footer"><span className="hint">Option entry premium: enter 0 to use the live option LTP. The underlying entry baseline is captured separately from the stock LTP.</span><button className="primary" type="submit" disabled={loading}>{loading?'Resolving…':'Create paper strategy'}</button></div>{message&&<div className="message">{message}</div>}</form></section>
    <section><div className="section-title"><div><h2>Strategies</h2><span className="hint">LTP/P&L refresh automatically. Risk snapshots are stored every minute.</span></div><button onClick={refresh}>Refresh</button></div>{dashboard.strategies.length===0?<div className="empty">No strategies yet. Create your first paper strategy above.</div>:dashboard.strategies.map(s=><StrategyCard key={s.id} strategy={s} onDelete={deleteStrategy} onAction={strategyAction} pnlClass={pnlClass}/>)}</section>
  </main></div>
}
createRoot(document.getElementById('root')).render(<App />)
