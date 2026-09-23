import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const apiUrl = path => API_BASE_URL + path

const emptyOrder = () => ({ symbol:'', expiry:'', strike:'', option_type:'CE', side:'SELL', entry_price:'', lots:1 })
const money = value => value == null || !Number.isFinite(Number(value)) ? '—' : (Number(value) >= 0 ? '+' : '-') + '₹' + Math.abs(Number(value)).toFixed(2)
const num = (value, digits=2) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits)
const pct = value => value == null || !Number.isFinite(Number(value)) ? '—' : (Number(value) >= 0 ? '+' : '') + Number(value).toFixed(2) + '%'
const timeLabel = ts => new Date(ts).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})
const dateTimeLabel = ts => new Date(ts).toLocaleString([], {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})

const RISK_META = {
  distance: 'Distance to the nearest short strike. A smaller distance means less price cushion.',
  delta: 'Directional exposure of the whole strategy. Higher magnitude means greater directional sensitivity.',
  gamma: 'How quickly strategy Delta changes as the underlying moves.',
  iv: 'Implied-volatility contribution from the open option legs.',
  technical: 'Combined technical pressure from momentum, RSI, ADX, ATR and volume context.',
}
const TECH_META = {
  rsi:'Wilder RSI(14), a 0–100 momentum oscillator.',
  adx:'Wilder ADX(14), a measure of trend strength.',
  plus_di:'Plus Directional Indicator used by ADX.',
  minus_di:'Minus Directional Indicator used by ADX.',
  atr:'Wilder ATR(14), average true price range.',
  atr_pct:'ATR as a percentage of the underlying price.',
  vwap:'Session VWAP from current-session intraday candles.',
  rolling_vwap_20:'Twenty-bar rolling volume-weighted price proxy for daily fallback data.',
  volume_ratio:'Latest volume divided by recent average volume.',
  momentum_pct:'Recent five-bar percentage price change.',
}

function InfoTip({text}) {
  return <span className="info-tip" tabIndex="0">i<span className="tooltip">{text}</span></span>
}

function StatusPill({band}) {
  const value = String(band || 'NORMAL').toLowerCase()
  return <span className={'status-pill '+value}><span className="status-dot"/>{band || 'NORMAL'}</span>
}

function RiskMeter({score}) {
  const value=Math.max(0,Math.min(100,Number(score)||0))
  return <div className="risk-meter"><div className="risk-track"><span style={{width:value+'%'}}/></div><div className="risk-scale"><span>0</span><span>40</span><span>70</span><span>100</span></div></div>
}

function RiskSummary({risk}) {
  if(!risk) return <div className="risk-summary-loading">Loading risk…</div>
  const band=String(risk.risk_band||'NORMAL').toLowerCase()
  return <div className="risk-summary">
    <div className="summary-risk-head"><div><span className="metric-label">RISK SCORE</span><strong>{num(risk.risk_score,0)}<small>/100</small></strong></div><StatusPill band={risk.risk_band}/></div>
    <RiskMeter score={risk.risk_score}/>
    <div className="mini-metrics">
      <div><span>Spot</span><strong>₹{num(risk.spot)}</strong></div>
      <div><span>Entry</span><strong>₹{num(risk.entry_spot)}</strong></div>
      <div><span>Change</span><strong className={Number(risk.spot_change_pct)>=0?'value-positive':'value-negative'}>{pct(risk.spot_change_pct)}</strong></div>
      <div><span>IV</span><strong>{risk.avg_iv==null?'—':num(risk.avg_iv*100,1)+'%'}</strong></div>
    </div>
  </div>
}

function StrategyCard({strategy,risk,onOpen}) {
  const currentRisk=risk?.risk_score
  const band=risk?.risk_band || 'NORMAL'
  return <article className="strategy-overview-card" onClick={()=>onOpen(strategy.id)}>
    <div className="strategy-card-head">
      <div><div className="strategy-number">STRATEGY #{strategy.id} · {strategy.status}</div><h3>{strategy.name}</h3><p>{strategy.description || 'Multi-leg paper strategy'}</p></div>
      <div className="strategy-card-action"><StatusPill band={band}/><button onClick={e=>{e.stopPropagation();onOpen(strategy.id)}}>Details</button></div>
    </div>

    <div className="strategy-key-row">
      <div className="pnl-block"><span>Paper P&L</span><strong className={strategy.pnl>=0?'value-positive':'value-negative'}>{money(strategy.pnl)}</strong></div>
      <RiskSummary risk={risk}/>
    </div>

    <div className="leg-summary">
      {strategy.orders.slice(0,4).map(o=><div className="leg-pill" key={o.id}>
        <span className={'side-marker '+o.side.toLowerCase()} />
        <strong>{o.symbol} {o.strike} {o.option_type}</strong>
        <span>{o.side}</span>
        <b>{o.current_ltp==null?'—':'₹'+o.current_ltp.toFixed(2)}</b>
      </div>)}
      {strategy.orders.length>4&&<span className="more-legs">+{strategy.orders.length-4} more</span>}
    </div>

    <div className="strategy-footer">
      <span>{strategy.priced_legs}/{strategy.total_legs} legs priced</span>
      <span>{currentRisk==null?'Risk unavailable':'Updated '+(risk?.timestamp ? dateTimeLabel(risk.timestamp) : 'live')}</span>
      <span className="open-link">Open risk workspace →</span>
    </div>
  </article>
}

function TooltipMetric({label,value,tip,sub}) {
  return <div className="detail-metric"><div className="detail-metric-label"><span>{label}</span>{tip&&<InfoTip text={tip}/>}</div><strong>{value}</strong>{sub&&<small>{sub}</small>}</div>
}

function RiskDrivers({risk}) {
  return <section className="workspace-section">
    <div className="workspace-section-head"><div><h4>Risk drivers</h4><span>Contribution to the current 0–100 score</span></div><InfoTip text="Higher component values indicate greater contribution to the monitoring score. This is not a probability of loss."/></div>
    <div className="driver-grid">
      {Object.entries(risk?.components||{}).map(([key,value])=><div className="driver-card" key={key}>
        <div className="driver-head"><div><strong>{key.replaceAll('_',' ')}</strong><InfoTip text={RISK_META[key]||'Risk contribution.'}/></div><b>{num(value,0)}</b></div>
        <div className="driver-bar"><span style={{width:Math.max(0,Math.min(100,Number(value)||0))+'%'}}/></div>
        <small>{key==='distance'?'Strike proximity':key==='delta'?'Directional exposure':key==='gamma'?'Risk acceleration':key==='iv'?'Volatility environment':'Market pressure'}</small>
      </div>)}
    </div>
  </section>
}

function Greeks({risk}) {
  const rows=[['Delta',risk?.delta,'Directional sensitivity'],['Gamma',risk?.gamma,'Delta acceleration'],['Theta',risk?.theta,'Time decay per day'],['Vega',risk?.vega,'Volatility sensitivity']]
  return <section className="workspace-section">
    <div className="workspace-section-head"><div><h4>Strategy Greeks</h4><span>Signed across all open legs</span></div><span className="data-chip">Live option data</span></div>
    <div className="greek-grid">{rows.map(([name,value,desc])=><div className="greek-card" key={name}><div><span>{name}</span><InfoTip text={desc+'.'}/></div><strong>{num(value,3)}</strong><small>{desc}</small></div>)}</div>
  </section>
}

function Technicals({risk}) {
  const entries=Object.entries(risk?.technical||{})
  return <section className="workspace-section">
    <div className="workspace-section-head"><div><h4>Technical context</h4><span>Underlying conditions used by the risk engine</span></div><span className="data-chip">{risk?.technical_source||'Live / historical'}</span></div>
    {entries.length?<div className="technical-grid">{entries.map(([key,value])=><div className="technical-card" key={key}><div><span>{key.replaceAll('_',' ')}</span><InfoTip text={TECH_META[key]||'Technical indicator.'}/></div><strong>{value==null?'—':key==='volume_ratio'?num(value,2)+'×':key.includes('pct')||key==='plus_di'||key==='minus_di'?num(value,1)+'%':key==='atr'||key==='vwap'||key==='rolling_vwap_20'?'₹'+num(value,2):num(value,1)}</strong></div>)}</div>:<div className="empty-state"><strong>Technical context unavailable</strong><span>Waiting for enough underlying bars or historical market data.</span></div>}
  </section>
}

function LegsTable({strategy,risk,onAction}) {
  return <section className="workspace-section">
    <div className="workspace-section-head"><div><h4>Open legs</h4><span>Live option prices, IV and paper P&L</span></div><span className="data-chip">{strategy.priced_legs}/{strategy.total_legs} priced</span></div>
    <div className="table-wrap"><table className="workspace-table"><thead><tr><th>Instrument</th><th>Side</th><th>Lots</th><th>Qty</th><th>Entry</th><th>LTP</th><th>IV</th><th>P&L</th><th/></tr></thead>
    <tbody>{strategy.orders.map(o=>{
      const leg=risk?.legs?.find(x=>x.id===o.id)
      return <tr key={o.id}><td><strong>{o.symbol} {o.strike} {o.option_type}</strong><small>{o.trading_symbol||o.instrument_key}</small></td><td><span className={'side-badge '+o.side.toLowerCase()}>{o.side}</span></td><td>{o.lots}</td><td>{o.quantity}</td><td>₹{o.entry_price.toFixed(2)}</td><td>{o.current_ltp==null?'—':'₹'+o.current_ltp.toFixed(2)}</td><td>{leg?.iv==null?'—':num(leg.iv*100,1)+'%'}</td><td className={o.pnl>=0?'value-positive':'value-negative'}>{money(o.pnl)}</td><td>{strategy.status==='OPEN'&&o.status==='OPEN'?<button className="small-action" onClick={()=>onAction(strategy.id,'close',o.id)}>Close</button>:null}</td></tr>
    })}</tbody></table></div>
  </section>
}

function PayoffDiagram({strategy,currentSpot}) {
  const legs=(strategy?.orders||[]).filter(o=>o.status==='OPEN')
  if(!legs.length)return null
  const strikes=legs.map(o=>Number(o.strike)).filter(Number.isFinite)
  const current=Number(currentSpot)||Math.max(...strikes)
  const minStrike=Math.min(...strikes),maxStrike=Math.max(...strikes)
  const minX=Math.max(0,Math.min(current,minStrike)*.94),maxX=Math.max(current,maxStrike)*1.06
  const values=Array.from({length:51},(_,i)=>{
    const spot=minX+(maxX-minX)*i/50
    let pnl=0
    legs.forEach(o=>{
      const intrinsic=o.option_type==='CE'?Math.max(spot-Number(o.strike),0):Math.max(Number(o.strike)-spot,0)
      const qty=Number(o.lots)*Number(o.lot_size)
      pnl += o.side==='BUY'?(intrinsic-Number(o.entry_price))*qty:(Number(o.entry_price)-intrinsic)*qty
    })
    return {spot,pnl}
  })
  const minP=Math.min(...values.map(v=>v.pnl),0),maxP=Math.max(...values.map(v=>v.pnl),0)
  const width=920,height=250,left=56,right=28,top=24,bottom=34,plotW=width-left-right,plotH=height-top-bottom
  const x=v=>left+(v-minX)/Math.max(.0001,maxX-minX)*plotW
  const y=v=>top+(1-(v-minP)/Math.max(.0001,maxP-minP))*plotH
  const points=values.map(v=>x(v.spot)+','+y(v.pnl)).join(' ')
  return <section className="workspace-section">
    <div className="workspace-section-head"><div><h4>Expiry payoff</h4><span>Scenario view based on option intrinsic value at expiry</span></div><span className="data-chip">Current spot ₹{num(current)}</span></div>
    <div className="payoff-wrap"><svg viewBox={'0 0 '+width+' '+height} className="payoff-chart">
      <line x1={left} x2={width-right} y1={y(0)} y2={y(0)} className="chart-zero"/>
      <polyline points={points} fill="none" className="payoff-line"/>
      {strikes.map((s,i)=><g key={i}><line x1={x(s)} x2={x(s)} y1={top} y2={height-bottom} className="strike-line"/><text x={x(s)} y={top-6} textAnchor="middle" className="strike-label">₹{num(s,0)}</text></g>)}
      <line x1={x(current)} x2={x(current)} y1={top} y2={height-bottom} className="current-spot-line"/>
      {[minX,(minX+maxX)/2,maxX].map((v,i)=><text key={i} x={x(v)} y={height-10} textAnchor={i===0?'start':i===2?'end':'middle'} className="axis-label">₹{num(v,0)}</text>)}
    </svg></div>
  </section>
}

function RiskTimeline({history=[],events=[],entrySpot=null}) {
  const [hoverIndex,setHoverIndex]=useState(null)
  if(!history.length)return <div className="empty-state"><strong>Risk timeline is building</strong><span>Snapshots are stored while the strategy is open.</span></div>
  const width=920,height=350,left=58,right=72,top=28,bottom=42,plotW=width-left-right,plotH=height-top-bottom
  const times=history.map(h=>new Date(h.timestamp).getTime()).filter(Number.isFinite)
  const first=times.length?Math.min(...times):Date.now(),last=times.length?Math.max(...times):first+60000,span=Math.max(60000,last-first)
  const x=i=>left+Math.max(0,Math.min(1,(new Date(history[i].timestamp).getTime()-first)/span))*plotW
  const riskY=v=>top+(1-Math.max(0,Math.min(100,Number(v)||0))/100)*plotH
  const spotValues=history.filter(h=>h.spot!=null).map(h=>Number(h.spot))
  const minRaw=spotValues.length?Math.min(...spotValues):0,maxRaw=spotValues.length?Math.max(...spotValues):1,pad=Math.max(1,(maxRaw-minRaw)*.12),minS=Math.max(0,minRaw-pad),maxS=maxRaw+pad
  const spotY=v=>top+(1-(Number(v)-minS)/Math.max(.0001,maxS-minS))*plotH
  const ticks=[0,.25,.5,.75,1].map((r)=>first+span*r)
  const riskPoints=history.map((h,i)=>x(i)+','+riskY(h.risk_score)).join(' ')
  const spotPoints=history.map((h,i)=>h.spot!=null?x(i)+','+spotY(h.spot):'').filter(Boolean).join(' ')
  const eventIndexes=events.slice(-6).map(e=>{let bi=0,bd=Infinity;history.forEach((h,i)=>{const d=Math.abs(new Date(h.timestamp)-new Date(e.timestamp));if(d<bd){bd=d;bi=i}});return {e,index:bi}})
  const hovered=hoverIndex==null?null:history[hoverIndex]
  const handleMove=e=>{const rect=e.currentTarget.getBoundingClientRect();const svgX=(e.clientX-rect.left)/rect.width*width;let bi=0,bd=Infinity;history.forEach((h,i)=>{const d=Math.abs(x(i)-svgX);if(d<bd){bd=d;bi=i}});setHoverIndex(bi)}
  const tooltipLeft=hoverIndex==null?0:Math.max(12,Math.min(88,x(hoverIndex)/width*100))
  const hoverSpot=hovered?.spot!=null?Number(hovered.spot):null
  const hoverPct=hoverSpot!=null&&entrySpot?((hoverSpot/entrySpot)-1)*100:null
  return <section className="workspace-section">
    <div className="workspace-section-head"><div><h4>Risk vs underlying LTP</h4><span>Shared time axis · left Y-axis risk 0–100 · right Y-axis underlying price</span></div><span className="data-chip">Hover to compare</span></div>
    <div className="timeline-wrap">
      <svg viewBox={'0 0 '+width+' '+height} className="timeline-svg" onMouseMove={handleMove} onMouseLeave={()=>setHoverIndex(null)}>
        {[0,20,40,60,70,80,100].map(t=><g key={t}><line x1={left} x2={width-right} y1={riskY(t)} y2={riskY(t)} className={t===40||t===70?'threshold-line':t===0?'chart-zero':'chart-grid'}/><text x={left-9} y={riskY(t)+4} textAnchor="end" className="risk-axis">{t}</text></g>)}
        {[0,.25,.5,.75,1].map((r,i)=>{const v=minS+(maxS-minS)*r;return <text key={i} x={width-right+9} y={spotY(v)+4} className="spot-axis">₹{num(v,0)}</text>})}
        {ticks.map((ms,i)=>{const tx=left+(ms-first)/span*plotW;return <g key={ms}>{i>0&&i<ticks.length-1?<line x1={tx} x2={tx} y1={top} y2={height-bottom} className="time-grid"/>:null}<text x={tx} y={height-13} textAnchor={i===0?'start':i===ticks.length-1?'end':'middle'} className="time-label">{timeLabel(ms)}</text></g>})}
        <text x={left} y={14} className="axis-caption risk-caption">RISK / 100</text><text x={width-right} y={14} textAnchor="end" className="axis-caption spot-caption">UNDERLYING LTP</text>
        <polyline points={spotPoints} fill="none" className="timeline-spot-line"/><polyline points={riskPoints} fill="none" className="timeline-risk-line"/>
        {history.map((h,i)=><circle key={'r'+i} cx={x(i)} cy={riskY(h.risk_score)} r={i===history.length-1?4:1.7} className="timeline-risk-dot"/>)}{history.map((h,i)=>h.spot!=null?<circle key={'s'+i} cx={x(i)} cy={spotY(h.spot)} r={i===history.length-1?4:1.7} className="timeline-spot-dot"/>:null)}
        <line x1={left} x2={width-right} y1={riskY(history[0]?.risk_score)} y2={riskY(history[0]?.risk_score)} className="entry-reference"/><line x1={left} x2={width-right} y1={entrySpot!=null?spotY(entrySpot):0} y2={entrySpot!=null?spotY(entrySpot):0} className="entry-reference"/>
        {eventIndexes.map((item,i)=><circle key={i} cx={x(item.index)} cy={riskY(history[item.index]?.risk_score)} r="5" className="timeline-event-dot"/>)}{hovered?<g><line x1={x(hoverIndex)} x2={x(hoverIndex)} y1={top} y2={height-bottom} className="timeline-hover-line"/><circle cx={x(hoverIndex)} cy={riskY(hovered.risk_score)} r="5.5" className="hover-risk"/>{hoverSpot!=null?<circle cx={x(hoverIndex)} cy={spotY(hoverSpot)} r="5.5" className="hover-spot"/>:null}</g>:null}
        <rect x={left} y={top} width={plotW} height={plotH} fill="transparent"/>
      </svg>
      {hovered?<div className="timeline-tooltip" style={{left:tooltipLeft+'%'}}><div>{dateTimeLabel(hovered.timestamp)}</div><section><strong>Risk</strong><b>{num(hovered.risk_score,0)}/100</b><small>{hovered.risk_band||'NORMAL'}</small></section><section><strong>Underlying</strong><b>{hoverSpot==null?'—':'₹'+num(hoverSpot)}</b><small>{hoverPct==null?'—':pct(hoverPct)+' from entry'}</small></section></div>:null}
    </div>
    <div className="chart-legend"><span><i className="legend-risk"/> Risk</span><span><i className="legend-spot"/> Underlying</span><span><i className="legend-entry"/> Entry references</span></div>
  </section>
}

function StrategyWorkspace({strategy,risk,onAction,onDelete,onClose}) {
  const band=String(risk?.risk_band||'NORMAL').toLowerCase()
  return <div className="modal-backdrop" onClick={onClose}>
    <div className="workspace-modal" onClick={e=>e.stopPropagation()}>
      <div className="workspace-top">
        <div><div className="section-kicker">STRATEGY #{strategy.id}</div><h2>{strategy.name}</h2><p>{strategy.description||'Multi-leg paper strategy'} · Monitoring only</p><div className="hero-tags"><StatusPill band={risk?.risk_band}/><span className="data-chip">{risk?.entry_spot_source||'Underlying entry reference'}</span></div></div>
        <div className="workspace-top-right"><div className="workspace-score"><span>Current risk</span><strong>{num(risk?.risk_score,0)}<small>/100</small></strong></div><button className="danger modal-delete" onClick={()=>onDelete(strategy.id)}>Delete</button><button className="modal-close" onClick={onClose}>×</button></div>
      </div>

      <div className="workspace-body">
        <section className="metric-grid detail-summary-grid">
          <TooltipMetric label="Underlying spot" value={risk?.spot==null?'Waiting…':'₹'+num(risk.spot)} sub={risk?.spot_change_pct==null?'—':pct(risk.spot_change_pct)+' from entry'}/>
          <TooltipMetric label="Entry baseline" value={risk?.entry_spot==null?'Waiting…':'₹'+num(risk.entry_spot)} sub={risk?.entry_spot_source||'Strategy reference'}/>
          <TooltipMetric label="Expected move" value={risk?.expected_move==null?'—':'±₹'+num(risk.expected_move)} tip="Estimated one-standard-deviation move using current average IV and time to the nearest open expiry." sub="1σ estimated range"/>
          <TooltipMetric label="Nearest short" value={risk?.distance_to_short_pct==null?'—':num(risk.distance_to_short_pct,2)+'%'} tip="Percentage distance to the closest open short strike." sub="Strike cushion"/>
          <TooltipMetric label="Average IV" value={risk?.avg_iv==null?'—':num(risk.avg_iv*100,1)+'%'} tip="Average implied volatility across open option legs." sub="Current option IV"/>
          <TooltipMetric label="Paper P&L" value={money(strategy.pnl)} sub={strategy.priced_legs+'/'+strategy.total_legs+' legs priced'}/>
        </section>

        <RiskDrivers risk={risk}/>
        <Greeks risk={risk}/>
        <LegsTable strategy={strategy} risk={risk} onAction={onAction}/>
        <Technicals risk={risk}/>
        <PayoffDiagram strategy={strategy} currentSpot={risk?.spot}/>
        <RiskTimeline history={risk?.history||[]} events={risk?.events||[]} entrySpot={risk?.entry_spot}/>

        <section className="two-col-detail">
          <div className="workspace-section compact-section"><div className="workspace-section-head"><div><h4>Alerts & detections</h4><span>Important strategy-state changes</span></div><span className="count-chip">{risk?.events?.length||0}</span></div><div className="alerts-list">{(risk?.events||[]).slice(-8).reverse().map((e,i)=><div className="alert-row" key={i}><span className="alert-bullet">•</span><div><strong>{e.event_type.replaceAll('_',' ')}</strong><span>{e.message}</span></div><time>{dateTimeLabel(e.timestamp)}</time></div>)}{!(risk?.events||[]).length?<div className="empty-state compact"><strong>No alerts yet</strong><span>Risk-band changes and strike threats will appear here.</span></div>:null}</div></div>
          <div className="workspace-section compact-section"><div className="workspace-section-head"><div><h4>Historical calibration</h4><span>Real strategy observations only</span></div><InfoTip text="No hardcoded probabilities. Calibration appears only after enough real snapshots exist."/></div>{risk?.probability?.buckets?.length?<div className="calibration-grid">{risk.probability.buckets.map(b=><div key={b.risk_min}><span>Risk {b.risk_min}–{b.risk_max}</span><strong>{b.event_rate_pct}%</strong><small>{b.observations} observations</small></div>)}</div>:<div className="empty-state compact"><strong>Collecting observations</strong><span>More stored snapshots are needed before historical rates are calculated.</span></div>}</div>
        </section>
      </div>

      <div className="workspace-footer"><span>Monitoring score only · not a loss probability or order signal</span><span>Last refreshed {new Date().toLocaleTimeString()}</span><button className="primary" onClick={()=>onAction(strategy.id,'exit')}>Exit strategy</button></div>
    </div>
  </div>
}

function CreateStrategyModal({onCreated,onClose}) {
  const [name,setName]=useState(''),[description,setDescription]=useState(''),[orders,setOrders]=useState([emptyOrder()]),[loading,setLoading]=useState(false),[message,setMessage]=useState('')
  const updateOrder=(i,f,v)=>setOrders(c=>c.map((o,j)=>j===i?{...o,[f]:v}:o))
  const addOrder=()=>setOrders(c=>[...c,emptyOrder()])
  const removeOrder=i=>setOrders(c=>c.length===1?c:c.filter((_,j)=>j!==i))
  const submit=async e=>{
    e.preventDefault();setLoading(true);setMessage('')
    try{
      const normalized=orders.map(o=>({...o,strike:Number(o.strike),entry_price:Number(o.entry_price),lots:Number(o.lots)}))
      const r=await fetch(apiUrl('/api/strategies'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description,orders:normalized})})
      const b=await r.json();if(!r.ok)throw new Error(b.detail||'Failed')
      onCreated(b.id)
    }catch(err){setMessage(err.message)}finally{setLoading(false)}
  }
  return <div className="modal-backdrop" onClick={onClose}><div className="create-modal" onClick={e=>e.stopPropagation()}>
    <div className="modal-header"><div><div className="section-kicker">NEW STRATEGY</div><h2>Create paper strategy</h2><p>Any combination of CE/PE BUY/SELL legs. No real orders are placed.</p></div><button className="modal-close" onClick={onClose}>×</button></div>
    <form onSubmit={submit}><div className="form-grid"><label>Strategy name<input required value={name} onChange={e=>setName(e.target.value)} placeholder="NIFTY Iron Condor"/></label><label>Description<input value={description} onChange={e=>setDescription(e.target.value)} placeholder="Optional"/></label></div>
      <div className="orders-heading"><div><strong>Option legs</strong><span>Enter 0 premium to use live option LTP.</span></div><button type="button" onClick={addOrder}>+ Add leg</button></div>
      <div className="table-wrap"><table className="entry-table"><thead><tr><th>Symbol</th><th>Expiry</th><th>Strike</th><th>Type</th><th>Side</th><th>Entry premium</th><th>Lots</th><th/></tr></thead><tbody>{orders.map((o,i)=><tr key={i}><td><input required value={o.symbol} onChange={e=>updateOrder(i,'symbol',e.target.value)} placeholder="NIFTY"/></td><td><input required type="date" value={o.expiry} onChange={e=>updateOrder(i,'expiry',e.target.value)}/></td><td><input required type="number" min="0.01" step="0.01" value={o.strike} onChange={e=>updateOrder(i,'strike',e.target.value)}/></td><td><select value={o.option_type} onChange={e=>updateOrder(i,'option_type',e.target.value)}><option>CE</option><option>PE</option></select></td><td><select value={o.side} onChange={e=>updateOrder(i,'side',e.target.value)}><option>SELL</option><option>BUY</option></select></td><td><input required type="number" min="0" step="0.01" value={o.entry_price} onChange={e=>updateOrder(i,'entry_price',e.target.value)} placeholder="0"/></td><td><input required type="number" min="1" step="1" value={o.lots} onChange={e=>updateOrder(i,'lots',e.target.value)}/></td><td><button className="danger icon-button" type="button" onClick={()=>removeOrder(i)}>×</button></td></tr>)}</tbody></table></div>
      <div className="form-footer"><span>{message||'Underlying entry baseline is captured separately from stock LTP.'}</span><button className="primary" type="submit" disabled={loading}>{loading?'Creating…':'Create strategy'}</button></div>
    </form>
  </div></div>
}

function App(){
  const [dashboard,setDashboard]=useState({strategies:[],total_pnl:0,open_orders:0,market_data_mode:'upstox'})
  const [riskMap,setRiskMap]=useState({})
  const [selectedId,setSelectedId]=useState(null)
  const [showCreate,setShowCreate]=useState(false)
  const [market,setMarket]=useState({status:'DISCONNECTED',mode:'upstox',subscribed:[],last_error:null})
  const [connecting,setConnecting]=useState(false)
  const [globalMessage,setGlobalMessage]=useState('')

  const loadRisks=async strategies=>{
    const results=await Promise.all(strategies.map(async s=>{
      try{
        const r=await fetch(apiUrl('/api/strategies/'+s.id+'/risk'))
        if(!r.ok)return [s.id,null]
        return [s.id,await r.json()]
      }catch{return [s.id,null]}
    }))
    setRiskMap(Object.fromEntries(results))
  }
  const refresh=async()=>{
    try{
      const [d,m]=await Promise.all([fetch(apiUrl('/api/dashboard')),fetch(apiUrl('/api/market/status'))])
      if(d.ok){
        const data=await d.json();setDashboard(data);loadRisks(data.strategies)
        if(selectedId!=null&&!data.strategies.some(s=>s.id===selectedId))setSelectedId(data.strategies[0]?.id??null)
      }
      if(m.ok)setMarket(await m.json())
    }catch(e){setGlobalMessage('Backend unavailable: '+e.message)}
  }
  useEffect(()=>{refresh();const t=setInterval(refresh,10000);return()=>clearInterval(t)},[])
  const selectedStrategy=useMemo(()=>dashboard.strategies.find(s=>s.id===selectedId)||null,[dashboard.strategies,selectedId])
  const selectedRisk=selectedId!=null?riskMap[selectedId]:null

  const createStrategy=async id=>{setShowCreate(false);setSelectedId(id);await refresh()}
  const connectMarket=async()=>{
    setConnecting(true)
    try{const r=await fetch(apiUrl('/api/market/connect'),{method:'POST'});const b=await r.json();if(!r.ok)throw new Error(b.detail||'Market connection failed');setGlobalMessage('Feed refreshed · '+b.subscribed+' option instruments');await refresh()}catch(e){setGlobalMessage(e.message)}finally{setConnecting(false)}
  }
  const deleteStrategy=async id=>{if(!window.confirm('Delete this paper strategy and its risk history?'))return;const r=await fetch(apiUrl('/api/strategies/'+id),{method:'DELETE'});if(r.ok)await refresh()}
  const strategyAction=async(id,action,orderId)=>{
    if(action==='exit'&&!window.confirm('Exit this paper strategy?'))return
    if(action==='close'&&!window.confirm('Close this paper leg?'))return
    const path=action==='exit'?'/exit':'/adjust'
    const body=action==='exit'?{reason:'Manual paper exit'}:{action:'CLOSE_LEG',order_id:orderId,reason:'Manual paper adjustment'}
    const r=await fetch(apiUrl('/api/strategies/'+id+path),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    if(!r.ok){const b=await r.json();setGlobalMessage(b.detail||'Action failed');return}
    await refresh()
  }

  const warningCount=Object.values(riskMap).filter(r=>r&&(r.risk_band==='WARNING'||r.risk_band==='CRITICAL')).length
  const criticalCount=Object.values(riskMap).filter(r=>r?.risk_band==='CRITICAL').length

  return <div className="app-shell">
    <header className="site-header">
      <div className="header-inner">
        <div className="brand"><div className="brand-icon">P</div><div><div className="brand-name">Paper Trader</div><span>Options strategy & risk dashboard</span></div></div>
        <div className="header-actions"><div className={'feed-status '+(market.status.includes('CONNECTED')?'connected':market.status.startsWith('ERROR')?'error':'')}><span className="feed-dot"/>{market.status}</div><button className="button-secondary" onClick={connectMarket} disabled={connecting}>{connecting?'Refreshing…':'Refresh feed'}</button><button className="button-primary" onClick={()=>setShowCreate(true)}>+ New strategy</button></div>
      </div>
    </header>

    <main className="main-content">
      {market.last_error?<div className="banner error-banner"><strong>Market data error</strong><span>{market.last_error}</span></div>:null}
      {globalMessage?<div className="banner message-banner">{globalMessage}</div>:null}

      <section className="page-intro">
        <div><div className="section-kicker">LIVE DASHBOARD</div><h1>Strategy overview</h1><p>All paper strategies in one view. Click a strategy for the full risk workspace.</p></div>
        <div className="intro-note">Updates every 10 seconds · risk engine refreshed with live market data</div>
      </section>

      <section className="portfolio-summary">
        <div className="summary-card emphasis"><span>Total paper P&L</span><strong className={dashboard.total_pnl>=0?'value-positive':'value-negative'}>{money(dashboard.total_pnl)}</strong><small>Across all strategies</small></div>
        <div className="summary-card"><span>Strategies</span><strong>{dashboard.strategies.length}</strong><small>Tracked positions</small></div>
        <div className="summary-card"><span>Open legs</span><strong>{dashboard.open_orders}</strong><small>Live paper positions</small></div>
        <div className="summary-card"><span>Warning / critical</span><strong className={warningCount?'value-warning':'value-positive'}>{warningCount} / {criticalCount}</strong><small>Risk states needing attention</small></div>
        <div className="summary-card"><span>Feed</span><strong>{dashboard.market_data_mode.toUpperCase()}</strong><small>{market.subscribed.length} instruments subscribed</small></div>
      </section>

      <section className="strategy-list-section">
        <div className="section-heading"><div><h2>Your strategies</h2><span>Each card shows the most important information at a glance.</span></div><button className="button-secondary light" onClick={refresh}>Refresh</button></div>
        {dashboard.strategies.length?<div className="strategy-grid">{dashboard.strategies.map(s=><StrategyCard key={s.id} strategy={s} risk={riskMap[s.id]} onOpen={setSelectedId}/>)}</div>:<div className="empty-dashboard"><strong>No strategies yet</strong><span>Create your first paper strategy to start live risk monitoring.</span><button className="button-primary" onClick={()=>setShowCreate(true)}>Create strategy</button></div>}
      </section>
    </main>

    <footer className="page-footer"><span>Paper trading only · no real orders are placed</span><span>Risk score is a monitoring model, not a loss probability</span></footer>

    {selectedStrategy&&selectedRisk?<StrategyWorkspace strategy={selectedStrategy} risk={selectedRisk} onAction={strategyAction} onDelete={deleteStrategy} onClose={()=>setSelectedId(null)}/>:null}
    {showCreate?<CreateStrategyModal onCreated={createStrategy} onClose={()=>setShowCreate(false)}/>:null}
  </div>
}

createRoot(document.getElementById('root')).render(<App />)
