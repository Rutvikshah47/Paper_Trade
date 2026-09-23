import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const apiUrl = path => API_BASE_URL + path

const emptyOrder = () => ({ symbol:'', expiry:'', strike:'', option_type:'CE', side:'SELL', entry_price:'', lots:1 })
const money = value => value === null || value === undefined ? '—' : (value >= 0 ? '+' : '-') + '₹' + Math.abs(value).toFixed(2)
const num = (value, digits=2) => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits)
const pct = value => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : (value >= 0 ? '+' : '') + Number(value).toFixed(2) + '%'
const timeLabel = timestamp => new Date(timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})
const dateTimeLabel = timestamp => new Date(timestamp).toLocaleString([], {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})

const RISK_META = {
  distance: 'Distance to the nearest short strike. Smaller distance means less price cushion before the short option is threatened.',
  delta: 'Directional exposure of the complete strategy. The score uses absolute strategy Delta normalized by open quantity.',
  gamma: 'How quickly strategy Delta changes when the underlying moves. High Gamma means risk can accelerate near strikes.',
  iv: 'Implied-volatility contribution. Higher IV indicates a more volatile option-pricing environment.',
  technical: 'Combined technical pressure from momentum, RSI, ADX, ATR and volume context. It is market context, not a trading signal.',
}

const TECH_META = {
  rsi: 'Wilder RSI(14). A 0–100 momentum oscillator.',
  adx: 'Wilder ADX(14). Measures trend strength, not trend direction.',
  plus_di: 'Plus Directional Indicator. Positive directional movement component of ADX.',
  minus_di: 'Minus Directional Indicator. Negative directional movement component of ADX.',
  atr: 'Wilder ATR(14). Average true price range in rupees.',
  atr_pct: 'ATR divided by the current underlying price.',
  vwap: 'Session VWAP from current-session intraday candles.',
  rolling_vwap_20: 'Twenty-bar rolling volume-weighted price proxy used for daily fallback data.',
  volume_ratio: 'Latest volume divided by recent average volume. 1.0x means average participation.',
  momentum_pct: 'Recent five-bar percentage price change.',
}

function InfoTip({ text }) {
  return <span className="info-tip" tabIndex="0">i<span className="tooltip">{text}</span></span>
}

function StatusPill({ band }) {
  const value = String(band || 'NORMAL').toLowerCase()
  return <span className={'status-pill ' + value}>{band || 'NORMAL'}</span>
}

function RiskDial({ score, band }) {
  const value = Math.max(0, Math.min(100, Number(score) || 0))
  const circumference = 141.37
  const offset = circumference * (1 - value / 100)
  return <div className="risk-dial-card">
    <svg className="risk-dial" viewBox="0 0 120 80" aria-label={'Risk score ' + value + ' out of 100'}>
      <path d="M15 66 A45 45 0 0 1 105 66" className="dial-track" pathLength="1"/>
      <path d="M15 66 A45 45 0 0 1 105 66" className="dial-value" pathLength="1" style={{strokeDasharray: 1, strokeDashoffset: offset / circumference}}/>
    </svg>
    <div className="dial-center"><strong>{num(value,0)}</strong><span>/ 100</span></div>
    <StatusPill band={band}/>
    <small>0–39 normal · 40–69 warning · 70–100 critical</small>
  </div>
}

function DriverCard({ name, value }) {
  return <div className="driver-card">
    <div className="driver-top"><div><strong>{name.replaceAll('_',' ')}</strong><InfoTip text={RISK_META[name] || 'Risk contribution component.'}/></div><b>{num(value,0)}</b></div>
    <div className="driver-track"><span style={{width:Math.max(0,Math.min(100,Number(value)||0)) + '%'}}/></div>
    <small>{name === 'distance' ? 'Strike proximity' : name === 'delta' ? 'Directional exposure' : name === 'gamma' ? 'Risk acceleration' : name === 'iv' ? 'Volatility environment' : 'Market pressure'}</small>
  </div>
}

function RiskTimeline({ history=[], events=[], entrySpot=null }) {
  const [hoverIndex,setHoverIndex] = useState(null)
  if (!history.length) return <div className="empty-state"><strong>Risk timeline is building</strong><span>Snapshots are stored every minute while the strategy is open.</span></div>

  const width=1040, height=410, left=68, right=82, top=30, bottom=48
  const plotWidth=width-left-right, plotHeight=height-top-bottom
  const times=history.map(h=>new Date(h.timestamp).getTime()).filter(Number.isFinite)
  const firstTime=times.length ? Math.min(...times) : Date.now()
  const lastTime=times.length ? Math.max(...times) : firstTime+60000
  const span=Math.max(60000,lastTime-firstTime)
  const x=i => {
    const t=new Date(history[i].timestamp).getTime()
    return left + Math.max(0,Math.min(1,(t-firstTime)/span))*plotWidth
  }
  const tickCount=span<=30*60*1000?6:span<=2*60*60*1000?7:8
  const tickTimes=Array.from({length:tickCount},(_,i)=>firstTime+span*i/Math.max(1,tickCount-1))
  const riskY=v=>top+(1-Math.max(0,Math.min(100,Number(v)||0))/100)*plotHeight
  const spotValues=history.filter(h=>h.spot!=null).map(h=>Number(h.spot))
  const spotMinRaw=spotValues.length?Math.min(...spotValues):0
  const spotMaxRaw=spotValues.length?Math.max(...spotValues):1
  const spotPad=Math.max(1,(spotMaxRaw-spotMinRaw)*0.12)
  const spotMin=Math.max(0,spotMinRaw-spotPad), spotMax=spotMaxRaw+spotPad
  const spotY=v=>top+(1-(Number(v)-spotMin)/Math.max(0.0001,spotMax-spotMin))*plotHeight
  const riskTicks=[0,20,40,60,70,80,100]
  const formatSpot=v=>Number(v)>=1000?'₹'+(Number(v)/1000).toFixed(2)+'k':'₹'+Number(v).toFixed(0)
  const riskPoints=history.map((h,i)=>Number.isFinite(Number(h.risk_score))?x(i)+','+riskY(h.risk_score):'').filter(Boolean).join(' ')
  const spotPoints=history.map((h,i)=>h.spot!=null?x(i)+','+spotY(h.spot):'').filter(Boolean).join(' ')
  const hovered=hoverIndex==null?null:history[hoverIndex]
  const hoverX=hoverIndex==null?null:x(hoverIndex)
  const hoverRisk=hovered?Number(hovered.risk_score):null
  const hoverSpot=hovered?.spot!=null?Number(hovered.spot):null
  const hoverPct=hoverSpot!=null && entrySpot?((hoverSpot/entrySpot)-1)*100:null
  const tooltipLeft=hoverX==null?0:Math.max(11,Math.min(89,hoverX/width*100))
  const eventIndexes=events.slice(-6).map(e=>{
    let best=0,bestDiff=Infinity
    history.forEach((h,i)=>{const d=Math.abs(new Date(h.timestamp)-new Date(e.timestamp));if(d<bestDiff){bestDiff=d;best=i}})
    return {event:e,index:best}
  })

  const handleMove=e=>{
    const rect=e.currentTarget.getBoundingClientRect()
    const svgX=((e.clientX-rect.left)/rect.width)*width
    let nearest=0,best=Infinity
    history.forEach((h,i)=>{const d=Math.abs(x(i)-svgX);if(d<best){best=d;nearest=i}})
    setHoverIndex(nearest)
  }

  return <div className="chart-card">
    <div className="chart-head">
      <div><div className="section-kicker">MARKET TIMELINE</div><h4>Risk vs underlying LTP</h4><p>Shared time axis. Left Y-axis is risk 0–100; right Y-axis is the actual underlying price.</p></div>
      <div className="chart-summary"><span>Entry risk</span><strong>{num(history[0]?.risk_score,0)}/100</strong><span>Current risk</span><strong>{num(history[history.length-1]?.risk_score,0)}/100</strong></div>
    </div>
    <div className="combined-plot">
      <svg viewBox={'0 0 '+width+' '+height} className="combined-risk-chart" onMouseMove={handleMove} onMouseLeave={()=>setHoverIndex(null)} role="img" aria-label="Risk and underlying LTP timeline">
        {riskTicks.map(t=><g key={t}><line x1={left} x2={width-right} y1={riskY(t)} y2={riskY(t)} className={t===0?'chart-zero':t===40||t===70?'risk-threshold':'chart-grid'}/><text x={left-10} y={riskY(t)+4} textAnchor="end" className="axis-label risk-axis-label">{t}</text></g>)}
        {[0,.25,.5,.75,1].map((ratio,i)=>{const tick=spotMin+(spotMax-spotMin)*ratio;return <g key={i}><text x={width-right+10} y={spotY(tick)+4} className="axis-label spot-axis-label">{formatSpot(tick)}</text></g>})}
        <text x={left} y={17} className="axis-title left">Risk / 100</text><text x={width-right} y={17} textAnchor="end" className="axis-title right">Underlying LTP</text>
        {tickTimes.map((ms,i)=>{const tx=left+((ms-firstTime)/span)*plotWidth;return <g key={ms}>{i>0&&i<tickTimes.length-1?<line x1={tx} x2={tx} y1={top} y2={height-bottom} className="time-grid"/>:null}<text x={tx} y={height-14} textAnchor={i===0?'start':i===tickTimes.length-1?'end':'middle'} className="axis-label">{new Date(ms).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</text></g>})}
        <polyline points={spotPoints} fill="none" className="spot-line"/><polyline points={riskPoints} fill="none" className="risk-line"/>
        {history.map((h,i)=><circle key={'r'+i} cx={x(i)} cy={riskY(h.risk_score)} r={i===history.length-1?4.5:1.8} className="risk-point"/>)}{history.map((h,i)=>h.spot!=null?<circle key={'s'+i} cx={x(i)} cy={spotY(h.spot)} r={i===history.length-1?4.5:1.8} className="spot-point"/>:null)}
        <line x1={left} x2={width-right} y1={riskY(history[0]?.risk_score)} y2={riskY(history[0]?.risk_score)} className="entry-line"/><text x={left+6} y={riskY(history[0]?.risk_score)-7} className="entry-label">Entry risk {num(history[0]?.risk_score,0)}</text>
        {entrySpot!=null?<g><line x1={left} x2={width-right} y1={spotY(entrySpot)} y2={spotY(entrySpot)} className="entry-line"/><text x={width-right-4} y={spotY(entrySpot)-7} textAnchor="end" className="entry-label">Entry ₹{num(entrySpot)}</text></g>:null}
        {eventIndexes.map((item,n)=><circle key={'e'+n} cx={x(item.index)} cy={riskY(history[item.index]?.risk_score)} r="5" className="event-dot"/>)}
        {hoverIndex!=null?<g><line x1={hoverX} x2={hoverX} y1={top} y2={height-bottom} className="hover-line"/><circle cx={hoverX} cy={riskY(hoverRisk)} r="5.5" className="hover-risk-point"/>{hoverSpot!=null?<circle cx={hoverX} cy={spotY(hoverSpot)} r="5.5" className="hover-spot-point"/>:null}</g>:null}
        <rect x={left} y={top} width={plotWidth} height={plotHeight} fill="transparent"/>
      </svg>
      {hovered?<div className="chart-tooltip" style={{left:tooltipLeft+'%'}}><div className="tooltip-time">{dateTimeLabel(hovered.timestamp)}</div><div className="tooltip-grid"><div><span>Risk</span><strong>{num(hoverRisk,0)}/100</strong><small>{hovered.risk_band||'NORMAL'}</small></div><div><span>Underlying</span><strong>{hoverSpot==null?'—':'₹'+num(hoverSpot)}</strong><small>{hoverPct==null?'—':pct(hoverPct)+' from entry'}</small></div></div></div>:null}
    </div>
    <div className="chart-legend"><span><i className="legend-risk"/> Risk score · left axis</span><span><i className="legend-spot"/> Underlying LTP · right axis</span><span><i className="legend-entry"/> Entry reference</span></div>
  </div>
}

function PayoffDiagram({ strategy, currentSpot }) {
  const legs=(strategy?.orders||[]).filter(o=>o.status==='OPEN')
  if(!legs.length) return null
  const strikes=legs.map(o=>Number(o.strike)).filter(Number.isFinite)
  const current=Number(currentSpot)||Math.max(...strikes)
  const minStrike=Math.min(...strikes), maxStrike=Math.max(...strikes)
  const minX=Math.max(0,Math.min(current,minStrike)*0.94), maxX=Math.max(current,maxStrike)*1.06
  const steps=50
  const values=Array.from({length:steps+1},(_,i)=>{
    const spot=minX+(maxX-minX)*i/steps
    let pnl=0
    legs.forEach(o=>{
      const intrinsic=o.option_type==='CE'?Math.max(spot-Number(o.strike),0):Math.max(Number(o.strike)-spot,0)
      const qty=Number(o.lots)*Number(o.lot_size)
      pnl += o.side==='BUY' ? (intrinsic-Number(o.entry_price))*qty : (Number(o.entry_price)-intrinsic)*qty
    })
    return {spot,pnl}
  })
  const minP=Math.min(...values.map(v=>v.pnl),0), maxP=Math.max(...values.map(v=>v.pnl),0)
  const width=980,height=270,left=58,right=26,top=26,bottom=38,plotW=width-left-right,plotH=height-top-bottom
  const x=v=>left+(v-minX)/Math.max(.0001,maxX-minX)*plotW
  const y=v=>top+(1-(v-minP)/Math.max(.0001,maxP-minP))*plotH
  const points=values.map(v=>x(v.spot)+','+y(v.pnl)).join(' ')
  const zeroY=y(0)
  return <div className="chart-card payoff-card">
    <div className="chart-head"><div><div className="section-kicker">SCENARIO</div><h4>Expiry payoff diagram</h4><p>Premium-only expiry payoff for the currently open legs. Useful for understanding the strategy shape, not a live P&L forecast.</p></div><div className="chart-summary"><span>Current spot</span><strong>{currentSpot==null?'—':'₹'+num(currentSpot)}</strong><span>Range</span><strong>₹{num(minX,0)}–₹{num(maxX,0)}</strong></div></div>
    <svg viewBox={'0 0 '+width+' '+height} className="payoff-chart" role="img" aria-label="Expiry payoff diagram">
      <line x1={left} x2={width-right} y1={zeroY} y2={zeroY} className="chart-zero"/>
      {[minP,0,maxP].map((v,i)=><text key={i} x={left-9} y={y(v)+4} textAnchor="end" className="axis-label">{money(v)}</text>)}
      <polyline points={points} fill="none" className="payoff-line"/>
      <path d={'M '+left+' '+(zeroY+34)+' L '+left+' '+(zeroY+28)+' L '+(width-right)+' '+(zeroY+28)+' L '+(width-right)+' '+(zeroY+34)} fill="none" className="payoff-baseline"/>
      {strikes.map((s,i)=><g key={i}><line x1={x(s)} x2={x(s)} y1={top} y2={height-bottom} className="strike-line"/><text x={x(s)} y={top-6} textAnchor="middle" className="strike-label">₹{num(s,0)}</text></g>)}
      <line x1={x(current)} x2={x(current)} y1={top} y2={height-bottom} className="current-spot-line"/><circle cx={x(current)} cy={y(values.reduce((best,v)=>Math.abs(v.spot-current)<Math.abs(best.spot-current)?v:best,values[0]).pnl)} r="5" className="current-spot-dot"/>
      <text x={x(current)+6} y={top+10} className="entry-label">Spot ₹{num(current)}</text>
      {[minX,(minX+maxX)/2,maxX].map((v,i)=><text key={i} x={x(v)} y={height-12} textAnchor={i===0?'start':i===2?'end':'middle'} className="axis-label">₹{num(v,0)}</text>)}
    </svg>
  </div>
}

function RiskDetails({ strategy, risk, onAction }) {
  if(!risk) return <div className="risk-loading">Loading strategy risk…</div>
  const components=Object.entries(risk.components||{})
  const technical=Object.entries(risk.technical||{})
  const events=risk.events||[]
  const band=String(risk.risk_band||'NORMAL').toLowerCase()
  return <div className="strategy-detail">
    <section className="detail-hero">
      <div className="hero-left"><div className="section-kicker">RISK ENGINE</div><h2>{strategy.name}</h2><p>Live strategy monitor · paper only · no real orders are placed</p><div className="hero-tags"><StatusPill band={risk.risk_band}/><span className="source-chip">{risk.entry_spot_source || 'Underlying entry reference'}</span></div></div>
      <RiskDial score={risk.risk_score} band={risk.risk_band}/>
    </section>

    <section className="metric-grid hero-metrics">
      <div className="metric-card metric-primary"><span>Underlying spot</span><strong>₹{num(risk.spot)}</strong><small>Live price · {pct(risk.spot_change_pct)} from entry</small></div>
      <div className="metric-card"><span>Entry baseline</span><strong>₹{num(risk.entry_spot)}</strong><small>{risk.entry_spot_source || 'Strategy entry reference'}</small></div>
      <div className="metric-card"><span>Expected move</span><strong>{risk.expected_move==null?'—':'±₹'+num(risk.expected_move)}</strong><small><InfoTip text="Estimated one-standard-deviation move using current average IV and time to nearest expiry."/></small></div>
      <div className="metric-card"><span>Nearest short</span><strong>{risk.distance_to_short_pct==null?'—':num(risk.distance_to_short_pct,2)+'%'}</strong><small>Distance to closest short strike</small></div>
      <div className="metric-card"><span>Average IV</span><strong>{risk.avg_iv==null?'—':num(risk.avg_iv*100,1)+'%'}</strong><small>Current option IV</small></div>
      <div className="metric-card"><span>Paper P&L</span><strong className={strategy.pnl>=0?'value-positive':'value-negative'}>{money(strategy.pnl)}</strong><small>{strategy.priced_legs}/{strategy.total_legs} legs priced</small></div>
    </section>

    <section className="two-col">
      <div className="panel-section">
        <div className="section-title-row"><div><h4>Risk engine breakdown</h4><span>Weighted contributors to the current 0–100 score</span></div><InfoTip text="The risk score is a monitoring model, not a probability of loss or a trading signal."/></div>
        <div className="driver-grid">{components.map(([key,value])=><DriverCard key={key} name={key} value={value}/>)}</div>
      </div>
      <div className="panel-section">
        <div className="section-title-row"><div><h4>Strategy Greeks</h4><span>Signed across all open legs</span></div><span className="data-source">Live option premiums + IV</span></div>
        <div className="greek-grid">{[['Delta',risk.delta,'Directional sensitivity'],['Gamma',risk.gamma,'Delta acceleration'],['Theta',risk.theta,'Time decay per day'],['Vega',risk.vega,'Volatility sensitivity']].map(([key,value,desc])=><div className="greek-card" key={key}><div><span>{key}</span><InfoTip text={desc + '.'}/></div><strong>{num(value,3)}</strong><small>{desc}</small></div>)}</div>
      </div>
    </section>

    <section className="panel-section">
      <div className="section-title-row"><div><h4>Open legs · live LTP</h4><span>Current option prices and paper P&L</span></div><span className="data-source">{new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span></div>
      <div className="table-wrap dark-table"><table><thead><tr><th>Instrument</th><th>Side</th><th>Lots</th><th>Qty</th><th>Entry</th><th>LTP</th><th>IV</th><th>P&L</th><th></th></tr></thead><tbody>
        {strategy.orders.map(o=>{const leg=risk.legs?.find(x=>x.id===o.id);return <tr key={o.id}><td><strong>{o.symbol} {o.strike} {o.option_type}</strong><small>{o.trading_symbol||o.instrument_key}</small></td><td><span className={'badge '+o.side.toLowerCase()}>{o.side}</span></td><td>{o.lots}</td><td>{o.quantity}</td><td>₹{o.entry_price.toFixed(2)}</td><td>{o.current_ltp==null?'—':'₹'+o.current_ltp.toFixed(2)}</td><td>{leg?.iv==null?'—':num(leg.iv*100,1)+'%'}</td><td className={o.pnl==null?'':o.pnl>=0?'value-positive':'value-negative'}>{money(o.pnl)}</td><td>{strategy.status==='OPEN'&&o.status==='OPEN'?<button className="danger table-action" onClick={()=>onAction(strategy.id,'close',o.id)}>Close</button>:null}</td></tr>})}
      </tbody></table></div>
    </section>

    <section className="panel-section">
      <div className="section-title-row"><div><h4>Technical section · {strategy.orders[0]?.symbol}</h4><span>Market conditions used by the risk engine</span></div><span className="data-source">{risk.technical_source || 'Historical / live bars'}</span></div>
      {technical.length?<div className="tech-grid">{technical.map(([key,value])=><div className="tech-card" key={key}><div><span>{key.replaceAll('_',' ')}</span><InfoTip text={TECH_META[key] || 'Technical market context.'}/></div><strong>{value==null?'—':key==='volume_ratio'?num(value,2)+'x':key.includes('pct')||key==='plus_di'||key==='minus_di'?num(value,1)+'%':key==='atr'||key==='vwap'||key==='rolling_vwap_20'?'₹'+num(value,2):num(value,1)}</strong></div>)}</div>:<div className="empty-state"><strong>Technical history unavailable</strong><span>The engine will continue building technical context from live or historical underlying candles.</span></div>}
    </section>

    <PayoffDiagram strategy={strategy} currentSpot={risk.spot}/>
    <RiskTimeline history={risk.history} events={events} entrySpot={risk.entry_spot}/>

    <section className="two-col bottom-panels">
      <div className="panel-section">
        <div className="section-title-row"><div><h4>Alerts & detections</h4><span>Important strategy-state changes</span></div><span className="alert-count">{events.length}</span></div>
        <div className="alerts-list">{events.slice(-8).reverse().map((e,i)=><div className="alert-row" key={i}><span className={'alert-icon '+String(e.event_type).toLowerCase().replaceAll('_','-')}>•</span><div><strong>{e.event_type.replaceAll('_',' ')}</strong><span>{e.message}</span></div><time>{dateTimeLabel(e.timestamp)}</time></div>)}{!events.length?<div className="empty-state compact"><strong>No alerts yet</strong><span>Risk-band changes and strike threats will appear here.</span></div>:null}</div>
      </div>
      <div className="panel-section">
        <div className="section-title-row"><div><h4>Historical calibration</h4><span>Strategy-specific real observations</span></div><InfoTip text="This section remains empty until enough real risk snapshots exist. No probability is hardcoded."/></div>
        {risk.probability?.buckets?.length?<div className="calibration-grid">{risk.probability.buckets.map(b=><div key={b.risk_min}><span>Risk {b.risk_min}–{b.risk_max}</span><strong>{b.event_rate_pct}%</strong><small>{b.observations} observations</small></div>)}</div>:<div className="empty-state compact"><strong>Collecting real observations</strong><span>More stored snapshots are needed before historical rates are calculated.</span></div>}
      </div>
    </section>

    <div className="detail-footer"><span>Monitoring only · not a loss probability and not an order signal</span><span>Updated {new Date().toLocaleTimeString()}</span></div>
  </div>
}

function StrategyCard({ strategy, selected, onSelect }) {
  return <button className={'strategy-tab '+(selected?'selected':'')} onClick={()=>onSelect(strategy.id)}>
    <div className="strategy-tab-top"><span>#{strategy.id}</span>{selected ? <StatusPill band={strategy.risk_band || 'NORMAL'}/> : <span className="tab-status-neutral">{strategy.status}</span>}</div>
    <strong>{strategy.name}</strong><span>{strategy.orders.length} legs · {money(strategy.pnl)}</span>
  </button>
}

function CreateStrategy({ onCreated }) {
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
      setName('');setDescription('');setOrders([emptyOrder()]);setMessage('Strategy #'+b.id+' created');onCreated(b.id)
    }catch(err){setMessage(err.message)}finally{setLoading(false)}
  }
  return <section className="create-shell">
    <div className="create-head"><div><div className="section-kicker">NEW STRATEGY</div><h3>Create a paper strategy</h3><p>Any combination of NSE CE/PE BUY/SELL legs. Enter 0 premium to use the live option LTP.</p></div><span className="paper-badge">PAPER ONLY</span></div>
    <form onSubmit={submit}>
      <div className="form-grid"><label>Strategy name<input required value={name} onChange={e=>setName(e.target.value)} placeholder="NIFTY Iron Condor"/></label><label>Description<input value={description} onChange={e=>setDescription(e.target.value)} placeholder="Optional"/></label></div>
      <div className="orders-heading"><div><strong>Option legs</strong><span>Underlying entry baseline is captured separately from the stock LTP.</span></div><button type="button" onClick={addOrder}>+ Add leg</button></div>
      <div className="table-wrap"><table className="entry-table"><thead><tr><th>Symbol</th><th>Expiry</th><th>Strike</th><th>Type</th><th>Side</th><th>Entry premium</th><th>Lots</th><th></th></tr></thead><tbody>{orders.map((o,i)=><tr key={i}><td><input required value={o.symbol} onChange={e=>updateOrder(i,'symbol',e.target.value)} placeholder="NIFTY"/></td><td><input required type="date" value={o.expiry} onChange={e=>updateOrder(i,'expiry',e.target.value)}/></td><td><input required type="number" min="0.01" step="0.01" value={o.strike} onChange={e=>updateOrder(i,'strike',e.target.value)}/></td><td><select value={o.option_type} onChange={e=>updateOrder(i,'option_type',e.target.value)}><option>CE</option><option>PE</option></select></td><td><select value={o.side} onChange={e=>updateOrder(i,'side',e.target.value)}><option>SELL</option><option>BUY</option></select></td><td><input required type="number" min="0" step="0.01" value={o.entry_price} onChange={e=>updateOrder(i,'entry_price',e.target.value)} placeholder="0"/></td><td><input required type="number" min="1" step="1" value={o.lots} onChange={e=>updateOrder(i,'lots',e.target.value)}/></td><td><button className="danger icon-button" type="button" onClick={()=>removeOrder(i)}>×</button></td></tr>)}</tbody></table></div>
      <div className="form-footer"><span>{message || 'Paper mode · no real orders are placed'}</span><button className="primary" type="submit" disabled={loading}>{loading?'Resolving…':'Create strategy'}</button></div>
    </form>
  </section>
}

function App(){
  const [dashboard,setDashboard]=useState({strategies:[],total_pnl:0,open_orders:0,market_data_mode:'upstox'})
  const [market,setMarket]=useState({status:'DISCONNECTED',mode:'upstox',subscribed:[],last_error:null})
  const [selectedId,setSelectedId]=useState(null)
  const [risk,setRisk]=useState(null)
  const [connecting,setConnecting]=useState(false)
  const [globalMessage,setGlobalMessage]=useState('')

  const refresh=async()=>{
    try{
      const [d,m]=await Promise.all([fetch(apiUrl('/api/dashboard')),fetch(apiUrl('/api/market/status'))])
      if(d.ok){
        const data=await d.json();setDashboard(data)
        if(selectedId==null && data.strategies.length)setSelectedId(data.strategies[0].id)
        if(selectedId!=null && !data.strategies.some(s=>s.id===selectedId) && data.strategies.length)setSelectedId(data.strategies[0].id)
        if(!data.strategies.length){setSelectedId(null);setRisk(null)}
      }
      if(m.ok)setMarket(await m.json())
    }catch(e){setGlobalMessage('Backend unavailable: '+e.message)}
  }
  useEffect(()=>{refresh();const t=setInterval(refresh,4000);return()=>clearInterval(t)},[])

  useEffect(()=>{
    if(selectedId==null){setRisk(null);return}
    let cancelled=false
    const load=async()=>{try{const r=await fetch(apiUrl('/api/strategies/'+selectedId+'/risk'));if(r.ok&&!cancelled)setRisk(await r.json())}catch{}}
    load();const t=setInterval(load,5000);return()=>{cancelled=true;clearInterval(t)}
  },[selectedId])

  const selectedStrategy=useMemo(()=>dashboard.strategies.find(s=>s.id===selectedId)||null,[dashboard.strategies,selectedId])

  const connectMarket=async()=>{
    setConnecting(true)
    try{const r=await fetch(apiUrl('/api/market/connect'),{method:'POST'});const b=await r.json();if(!r.ok)throw new Error(b.detail||'Market connection failed');setGlobalMessage('Feed refreshed · '+b.subscribed+' option instruments');await refresh()}catch(e){setGlobalMessage(e.message)}finally{setConnecting(false)}
  }

  const deleteStrategy=async id=>{if(!window.confirm('Delete this paper strategy and its risk history?'))return;const r=await fetch(apiUrl('/api/strategies/'+id),{method:'DELETE'});if(r.ok)await refresh()}
  const strategyAction=async(id,action,orderId)=>{
    const confirmText=action==='exit'?'Exit this paper strategy?':'Close this paper leg?'
    if(!window.confirm(confirmText))return
    const path=action==='exit'?'/exit':'/adjust'
    const body=action==='exit'?{reason:'Manual paper exit'}:{action:'CLOSE_LEG',order_id:orderId,reason:'Manual paper adjustment'}
    const r=await fetch(apiUrl('/api/strategies/'+id+path),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    if(!r.ok){const b=await r.json();setGlobalMessage(b.detail||'Action failed');return}
    await refresh()
  }
  const connectionClass=market.status.includes('CONNECTED')?'connected':market.status.startsWith('ERROR')?'error':'connecting'

  return <div className="terminal-app">
    <header className="terminal-header">
      <div className="header-inner">
        <div className="brand-block"><div className="brand-mark">S</div><div><div className="brand-name">StrikeWatch</div><span>Options paper trading & risk dashboard</span></div></div>
        <div className="header-tickers">
          {selectedStrategy?.orders[0]?<><div className="ticker"><span>{selectedStrategy.orders[0].symbol}</span><strong>{risk?.spot==null?'—':'₹'+num(risk.spot)}</strong><small>{risk?.spot_change_pct==null?'—':pct(risk.spot_change_pct)}</small></div><div className="ticker"><span>Risk</span><strong>{risk?.risk_score==null?'—':num(risk.risk_score,0)+'/100'}</strong><small>{risk?.risk_band||'—'}</small></div><div className="ticker"><span>IV</span><strong>{risk?.avg_iv==null?'—':num(risk.avg_iv*100,1)+'%'}</strong><small>avg IV</small></div><div className="ticker"><span>P&L</span><strong className={selectedStrategy.pnl>=0?'value-positive':'value-negative'}>{money(selectedStrategy.pnl)}</strong><small>paper</small></div></>:<div className="ticker"><span>Market feed</span><strong>{dashboard.market_data_mode.toUpperCase()}</strong><small>{market.subscribed.length} instruments</small></div>}
        </div>
        <div className="header-actions"><div className={'feed-status '+connectionClass}><span className="dot"/>{market.status}</div><button className="header-button" onClick={connectMarket} disabled={connecting}>{connecting?'Refreshing…':'Refresh feed'}</button></div>
      </div>
      <div className="header-strip"><span>Paper · No real orders</span><span>Underlying feed included</span><span>Risk snapshots every minute</span><button onClick={()=>document.querySelector('.create-shell')?.scrollIntoView({behavior:'smooth'})}>+ New strategy</button></div>
    </header>

    <main className="terminal-main">
      {market.last_error?<div className="error-banner"><strong>Market data error</strong><span>{market.last_error}</span></div>:null}
      {globalMessage?<div className="message-banner">{globalMessage}</div>:null}

      <section className="overview-title"><div><div className="section-kicker">PORTFOLIO</div><h2>Strategies</h2><p>Switch between active strategies. The selected strategy opens in the risk workspace below.</p></div><div className="portfolio-total"><span>Total paper P&L</span><strong className={dashboard.total_pnl>=0?'value-positive':'value-negative'}>{money(dashboard.total_pnl)}</strong></div></section>

      <section className="strategy-tabs">
        {dashboard.strategies.map(s=><StrategyCard key={s.id} strategy={{...s,risk_band:s.id===selectedId&&risk?risk.risk_band:'NORMAL'}} selected={s.id===selectedId} onSelect={setSelectedId}/> )}
        {!dashboard.strategies.length?<div className="empty-tabs">No strategies yet.</div>:null}
      </section>

      {selectedStrategy&&risk?<RiskDetails strategy={selectedStrategy} risk={risk} onAction={strategyAction}/>:<section className="workspace-empty"><strong>Select a strategy to open the risk workspace</strong><span>Create a paper strategy or select one from the portfolio tabs above.</span></section>}

      <CreateStrategy onCreated={async id=>{setSelectedId(id);await refresh()}} />

      <div className="workspace-footer"><span>StrikeWatch-style terminal layout adapted for this paper-trading risk engine.</span><span>Feed: {dashboard.market_data_mode.toUpperCase()}</span></div>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App />)
