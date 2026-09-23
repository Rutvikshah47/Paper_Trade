import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const apiUrl = path => `${API_BASE_URL}${path}`

const emptyOrder = () => ({ symbol:'', expiry:'', strike:'', option_type:'CE', side:'SELL', entry_price:'', lots:1 })
const money = value => value === null || value === undefined ? '—' : `${value >= 0 ? '+' : '-'}₹${Math.abs(value).toFixed(2)}`
const num = (value, digits=2) => value === null || value === undefined ? '—' : Number(value).toFixed(digits)
const pct = value => value === null || value === undefined ? '—' : `${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`

const RISK_META = {
  distance: 'Distance to the nearest short strike. Smaller distance means less price cushion before the short option is threatened.',
  delta: 'Absolute strategy delta normalized by open quantity. Higher magnitude means the strategy is more exposed to directional moves.',
  gamma: 'Gamma measures how quickly Delta changes as the underlying moves. Higher Gamma means risk can accelerate near the strike.',
  iv: 'Implied volatility contribution. Higher IV represents a larger option-price volatility environment and can increase risk for short premium strategies.',
  technical: 'Aggregate technical pressure from momentum, RSI, ADX, ATR and volume context. It reflects market conditions, not a buy/sell signal.',
}

const TECH_META = {
  rsi: 'Relative Strength Index. A momentum oscillator from 0 to 100; this dashboard uses it as market-context input.',
  adx: 'Average Directional Index. Measures trend strength, not direction.',
  atr: 'Average True Range. Measures typical price range in rupees.',
  atr_pct: 'ATR expressed as a percentage of the underlying price.',
  vwap: 'Volume-weighted average price calculated from the available technical bars.',
  volume_ratio: 'Latest volume divided by the recent average volume. Values above 1 indicate higher-than-average participation.',
  momentum_pct: 'Five-bar percentage price change over the current technical data set.',
  plus_di: 'Plus Directional Indicator. Measures positive directional movement relative to smoothed True Range.',
  minus_di: 'Minus Directional Indicator. Measures negative directional movement relative to smoothed True Range.',
  rolling_vwap_20: 'Twenty-bar rolling volume-weighted price proxy used only when daily history is being used. Traditional session VWAP is intraday and resets each session.',
}

function InfoTip({ text }) {
  return <span className="info-tip" tabIndex="0" aria-label={text}>i<span className="tooltip">{text}</span></span>
}

function RiskGauge({ score, band }) {
  const value = Math.max(0, Math.min(100, Number(score) || 0))
  return <div className="risk-gauge">
    <div className="gauge-track">
      <div className="gauge-fill" style={{ width: value + '%' }} />
      <span className="gauge-marker" style={{ left: value + '%' }} />
    </div>
    <div className="gauge-scale"><span>0 Normal</span><span>40 Warning</span><span>70 Critical</span><span>100</span></div>
    <div className="gauge-caption"><strong>{num(value,0)}/100</strong><span className={'band-text ' + String(band || 'NORMAL').toLowerCase()}>{band || 'NORMAL'}</span></div>
  </div>
}

function RiskChart({ history=[], events=[], entrySpot=null }) {
  const [hoverIndex, setHoverIndex] = useState(null)
  const entryRisk = Number(history[0]?.risk_score) || 0
  if (!history.length) {
    return <div className="chart-empty"><strong>Waiting for first risk snapshot</strong><span>The risk engine will plot the strategy once live market data is available.</span></div>
  }

  const width = 1040
  const height = 420
  const left = 68
  const right = 78
  const top = 34
  const bottom = 52
  const chartWidth = width - left - right
  const chartHeight = height - top - bottom

  const timestamps = history.map(h => new Date(h.timestamp).getTime()).filter(Number.isFinite)
  const firstTime = timestamps.length ? Math.min(...timestamps) : Date.now()
  const lastTime = timestamps.length ? Math.max(...timestamps) : firstTime + 60000
  const spanMs = Math.max(60000, lastTime - firstTime)

  const x = i => {
    const ts = new Date(history[i].timestamp).getTime()
    const ratio = Number.isFinite(ts) ? (ts - firstTime) / spanMs : i / Math.max(1, history.length - 1)
    return left + Math.max(0, Math.min(1, ratio)) * chartWidth
  }

  const tickCount = spanMs <= 30*60*1000 ? 6 : spanMs <= 2*60*60*1000 ? 7 : spanMs <= 6*60*60*1000 ? 7 : 8
  const tickTimes = Array.from({length: tickCount}, (_,i) => firstTime + spanMs * i / Math.max(1, tickCount-1))
  const formatTick = ms => {
    const d = new Date(ms)
    if (spanMs >= 24*60*60*1000) {
      return d.toLocaleDateString([], {day:'2-digit', month:'short'}) + ' ' + d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})
    }
    return d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})
  }

  const riskY = value => top + (1 - Math.max(0, Math.min(100, value)) / 100) * chartHeight
  const riskTicks = [0,20,40,60,70,80,100]
  const riskPoints = history.map((h,i) => {
    const value = Number(h.risk_score)
    return Number.isFinite(value) ? x(i)+','+riskY(value) : ''
  }).filter(Boolean).join(' ')

  const spotValues = history.map(h => h.spot).filter(v => v != null).map(Number)
  const spotMinRaw = spotValues.length ? Math.min(...spotValues) : 0
  const spotMaxRaw = spotValues.length ? Math.max(...spotValues) : 1
  const spotPadding = Math.max(1, (spotMaxRaw - spotMinRaw) * 0.12)
  const spotMin = Math.max(0, spotMinRaw - spotPadding)
  const spotMax = spotMaxRaw + spotPadding
  const spotY = value => top + (1 - ((value - spotMin) / Math.max(0.0001, spotMax - spotMin))) * chartHeight
  const spotPoints = history.map((h,i) => {
    const value = Number(h.spot)
    return Number.isFinite(value) ? x(i)+','+spotY(value) : ''
  }).filter(Boolean).join(' ')

  const formatSpot = value => value == null ? '—' : '₹'+Number(value).toFixed(2)
  const formatSpotAxis = value => value >= 1000 ? '₹'+(value/1000).toFixed(2)+'k' : '₹'+value.toFixed(0)
  const spotTicks = spotValues.length ? Array.from({length:5},(_,i) => spotMin + (spotMax-spotMin)*i/4) : []

  const eventIndexes = events.slice(-6).map(e => {
    let best = 0, bestDiff = Infinity
    history.forEach((h,i) => {
      const diff = Math.abs(new Date(h.timestamp) - new Date(e.timestamp))
      if (diff < bestDiff) { bestDiff = diff; best = i }
    })
    return { ...e, index: best }
  })

  const hovered = hoverIndex == null ? null : history[hoverIndex]
  const hoverX = hoverIndex == null ? null : x(hoverIndex)
  const hoverRisk = hovered ? Number(hovered.risk_score) : null
  const hoverSpot = hovered?.spot != null ? Number(hovered.spot) : null
  const spotChange = hovered && entrySpot && hoverSpot ? ((hoverSpot / entrySpot) - 1) * 100 : null
  const tooltipLeft = hoverX == null ? 0 : Math.max(11, Math.min(89, hoverX / width * 100))

  const handleMove = event => {
    const rect = event.currentTarget.getBoundingClientRect()
    const svgX = ((event.clientX - rect.left) / rect.width) * width
    let nearest = 0, best = Infinity
    history.forEach((h,i) => {
      const distance = Math.abs(x(i) - svgX)
      if (distance < best) { best = distance; nearest = i }
    })
    setHoverIndex(nearest)
  }

  return <div className="chart-card combined-chart-card">
    <div className="chart-head">
      <div><div className="section-kicker">MARKET TIMELINE</div><h4>Risk vs underlying LTP</h4><p>One shared time axis. Left Y-axis = risk score (0–100). Right Y-axis = underlying price (₹). Hover any point to compare both values.</p></div>
      <div className="chart-summary">
        <span>Entry risk</span><strong>{num(entryRisk,0)}/100</strong>
        <span>Current risk</span><strong>{num(history[history.length-1]?.risk_score,0)}/100</strong>
        <span>Current spot</span><strong>{spotValues.length ? formatSpot(spotValues[spotValues.length-1]) : '—'}</strong>
      </div>
    </div>

    <div className="combined-plot">
      <svg viewBox={'0 0 '+width+' '+height} className="risk-chart combined-risk-chart" role="img" aria-label="Risk and underlying spot over time" onMouseMove={handleMove} onMouseLeave={() => setHoverIndex(null)}>
        {riskTicks.map(tick => <g key={'r'+tick}>
          <line x1={left} x2={width-right} y1={riskY(tick)} y2={riskY(tick)} className={tick === 0 ? 'chart-zero' : tick === 40 || tick === 70 ? 'risk-threshold' : 'chart-grid'} />
          <text x={left-10} y={riskY(tick)+4} textAnchor="end" className="axis-label risk-axis-label">{tick}</text>
        </g>)}

        {spotTicks.map((tick,i) => <g key={'s'+i}>
          <text x={width-right+10} y={spotY(tick)+4} textAnchor="start" className="axis-label spot-axis-label">{formatSpotAxis(tick)}</text>
        </g>)}

        {tickTimes.map((ms,i) => {
          const tx = left + ((ms-firstTime)/spanMs) * chartWidth
          return <g key={ms}>
            {i > 0 && i < tickTimes.length-1 ? <line x1={tx} x2={tx} y1={top} y2={height-bottom} className="time-grid" /> : null}
            <text x={tx} y={height-15} textAnchor={i===0?'start':i===tickTimes.length-1?'end':'middle'} className="axis-label">{formatTick(ms)}</text>
          </g>
        })}

        <text x={left} y={17} className="axis-title left">Risk / 100</text>
        <text x={width-right} y={17} textAnchor="end" className="axis-title right">Underlying LTP</text>

        {spotValues.length ? <polyline points={spotPoints} fill="none" className="spot-line" /> : null}
        <polyline points={riskPoints} fill="none" className="risk-line" />

        {history.map((h,i) => <circle key={'rp'+i} cx={x(i)} cy={riskY(Number(h.risk_score)||0)} r={i === history.length-1 ? 4.5 : 1.8} className="risk-point" />)}
        {history.map((h,i) => h.spot != null ? <circle key={'sp'+i} cx={x(i)} cy={spotY(Number(h.spot))} r={i === history.length-1 ? 4.5 : 1.8} className="spot-point" /> : null)}

        <line x1={left} x2={width-right} y1={riskY(entryRisk)} y2={riskY(entryRisk)} className="entry-line" />
        <text x={left+6} y={riskY(entryRisk)-7} className="entry-label">Entry risk {num(entryRisk,0)}</text>
        {entrySpot != null && spotValues.length ? <line x1={left} x2={width-right} y1={spotY(entrySpot)} y2={spotY(entrySpot)} className="entry-line spot-entry-line" /> : null}
        {entrySpot != null && spotValues.length ? <text x={width-right-6} y={spotY(entrySpot)-7} textAnchor="end" className="entry-label">Entry ₹{num(entrySpot)}</text> : null}

        {eventIndexes.map((e,n) => <circle key={'ev'+n} cx={x(e.index)} cy={riskY(Number(history[e.index]?.risk_score)||0)} r="5" className="event-dot" />)}

        {hoverIndex != null ? <g>
          <line x1={hoverX} x2={hoverX} y1={top} y2={height-bottom} className="hover-line" />
          <circle cx={hoverX} cy={riskY(hoverRisk)} r="5.5" className="hover-risk-point" />
          {hoverSpot != null ? <circle cx={hoverX} cy={spotY(hoverSpot)} r="5.5" className="hover-spot-point" /> : null}
        </g> : null}

        <rect x={left} y={top} width={chartWidth} height={chartHeight} fill="transparent" className="hover-capture" />
      </svg>

      {hovered && <div className="chart-tooltip" style={{left: tooltipLeft+'%'}}>
        <div className="tooltip-time">{new Date(hovered.timestamp).toLocaleString()}</div>
        <div className="tooltip-grid">
          <div><span>Risk</span><strong>{num(hoverRisk,0)}/100</strong><small>{hovered.risk_band || 'NORMAL'}</small></div>
          <div><span>Underlying</span><strong>{formatSpot(hoverSpot)}</strong><small>{spotChange == null ? '—' : pct(spotChange)+' from entry'}</small></div>
        </div>
      </div>}
    </div>

    <div className="chart-legend"><span><i className="legend-risk"/> Risk score · left axis</span><span><i className="legend-spot"/> Underlying LTP · right axis</span><span><i className="legend-entry"/> Entry reference</span></div>
  </div>
}


function RiskPanel({ strategy }) {
  const [risk,setRisk] = useState(null)
  const load = async () => {
    try {
      const r = await fetch(apiUrl('/api/strategies/' + strategy.id + '/risk'))
      if (r.ok) setRisk(await r.json())
    } catch {}
  }
  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [strategy.id])

  if (!risk) return <div className="risk-loading">Loading risk engine…</div>

  const band = String(risk.risk_band || 'NORMAL').toLowerCase()
  const probability = risk.probability
  const components = Object.entries(risk.components || {})
  const technical = Object.entries(risk.technical || {})
  const currentSpot = risk.spot
  const shortDistance = risk.distance_to_short_pct

  return <div className="risk-panel">
    <div className="risk-hero">
      <div>
        <div className="section-kicker">RISK ENGINE</div>
        <h3>Live strategy risk</h3>
        <p>Calculated from current option data, underlying price and technical context.</p>
      </div>
      <div className="risk-hero-score">
        <span className={'status-pill ' + band}>{risk.risk_band}</span>
        <strong>{num(risk.risk_score,0)}<small>/100</small></strong>
      </div>
    </div>

    <RiskGauge score={risk.risk_score} band={risk.risk_band} />

    <div className="risk-section">
      <div className="section-title-row">
        <div><h4>Market position</h4><span>Live underlying and strategy reference levels</span></div>
        <span className="data-source">{risk.entry_spot_source || 'Underlying entry reference'}</span>
      </div>
      <div className="metric-grid six">
        <div className="metric-card metric-primary"><span>Current spot</span><strong>{currentSpot == null ? 'Waiting…' : '₹'+num(currentSpot)}</strong><small>Live underlying · now</small></div>
        <div className="metric-card"><span>Entry baseline</span><strong>{risk.entry_spot == null ? 'Waiting…' : '₹'+num(risk.entry_spot)}</strong><small>Change {pct(risk.spot_change_pct)}</small></div>
        <div className="metric-card"><span>Expected move <InfoTip text="Estimated one-standard-deviation move using current IV and time to the nearest open expiry." /></span><strong>{risk.expected_move == null ? '—' : '±₹'+num(risk.expected_move)}</strong><small>1σ estimated range</small></div>
        <div className="metric-card"><span>Nearest short <InfoTip text="Percentage distance from the underlying to the closest open short strike." /></span><strong>{shortDistance == null ? '—' : num(shortDistance)+'%'}</strong><small>Strike cushion</small></div>
        <div className="metric-card"><span>Average IV <InfoTip text="Average implied volatility across open option legs where IV can be solved from the live premium." /></span><strong>{risk.avg_iv == null ? '—' : num(risk.avg_iv*100,1)+'%'}</strong><small>Current option IV</small></div>
        <div className="metric-card"><span>Risk state</span><strong className={'value-'+band}>{risk.risk_band}</strong><small>Score {num(risk.risk_score,0)}/100</small></div>
      </div>
    </div>

    <div className="risk-section">
      <div className="section-title-row"><div><h4>Risk drivers</h4><span>Each component contributes to the 0–100 risk score</span></div><InfoTip text="The score is a monitoring model. Higher component values mean that factor contributes more risk; it is not a probability of loss." /></div>
      <div className="driver-grid">
        {components.map(([key,value]) => <div className="driver-card" key={key}>
          <div className="driver-top"><div><strong>{key.replaceAll('_',' ')}</strong><InfoTip text={RISK_META[key] || 'Risk contribution component.'}/></div><b>{num(value,0)}</b></div>
          <div className="driver-track"><span style={{width:Math.max(0,Math.min(100,Number(value)||0))+'%'}}/></div>
          <small>{key === 'distance' ? 'Strike proximity' : key === 'delta' ? 'Directional exposure' : key === 'gamma' ? 'Acceleration' : key === 'iv' ? 'Volatility environment' : 'Market pressure'}</small>
        </div>)}
      </div>
    </div>

    <div className="risk-section">
      <div className="section-title-row"><div><h4>Strategy Greeks</h4><span>Signed across all open legs</span></div><span className="data-source">Live option premiums + IV</span></div>
      <div className="greek-grid">
        {[['Delta',risk.delta,'Directional sensitivity'],['Gamma',risk.gamma,'Delta acceleration'],['Theta',risk.theta,'Time decay per day'],['Vega',risk.vega,'Volatility sensitivity']].map(([key,value,desc]) =>
          <div className="greek-card" key={key}>
            <div><span>{key}</span><InfoTip text={desc + '.'}/></div>
            <strong>{num(value,3)}</strong><small>{desc}</small>
          </div>
        )}
      </div>
    </div>

    <div className="risk-section">
      <div className="section-title-row"><div><h4>Technical context</h4><span>Underlying market conditions used by the risk engine</span></div><span className="data-source">{risk.technical_source || 'Historical / live bars'}</span></div>
      {technical.length ? <div className="tech-grid">
        {technical.map(([key,value]) => <div className="tech-card" key={key}>
          <div><span>{key.replaceAll('_',' ')}</span><InfoTip text={TECH_META[key] || 'Technical market context.'}/></div>
          <strong>{value == null ? '—' : key === 'volume_ratio' ? num(value,2)+'×' : key.includes('pct') || key === 'plus_di' || key === 'minus_di' ? num(value,1)+'%' : key === 'atr' || key === 'vwap' || key === 'rolling_vwap_20' ? '₹'+num(value,2) : num(value,1)}</strong>
        </div>)}
      </div> : <div className="empty-state"><strong>Technical context is still building</strong><span>The service is waiting for historical or live underlying bars. Risk still uses the available option data.</span></div>}
    </div>

    <RiskChart history={risk.history} events={risk.events || []} entrySpot={risk.entry_spot}/>

    <details className="advanced-section">
      <summary>Events & historical calibration <span>Expand</span></summary>
      <div className="advanced-content">
        <div>
          <div className="mini-heading">Recent events</div>
          {(risk.events || []).slice(-10).reverse().map((e,i) => <div className="event-row" key={i}><span className="event-time">{new Date(e.timestamp).toLocaleTimeString()}</span><b>{e.event_type.replaceAll('_',' ')}</b><span>{e.message}</span></div>)}
          {!(risk.events || []).length && <div className="empty-state compact">No risk events yet.</div>}
        </div>
        <div>
          <div className="mini-heading">Historical calibration <InfoTip text="Strategy-specific observations built only from stored real risk snapshots. It is intentionally blank until enough data exists."/></div>
          {probability && probability.buckets?.length ? <div className="prob-grid">{probability.buckets.map(b => <div key={b.risk_min}><span>Risk {b.risk_min}–{b.risk_max}</span><strong>{b.event_rate_pct}%</strong><small>{b.observations} observations</small></div>)}</div> : <div className="empty-state compact"><strong>Not available yet</strong><span>More real snapshots are needed before historical rates are calculated.</span></div>}
        </div>
      </div>
    </details>

    <div className="risk-foot"><span>Monitoring score only · not a loss probability and not an order signal.</span><span>Updated {new Date().toLocaleTimeString()}</span></div>
  </div>
}

function StrategyCard({strategy,onDelete,pnlClass,onAction}) {
  return <article className="strategy-card">
    <div className="strategy-head">
      <div className="strategy-name"><div className="strategy-id">STRATEGY #{strategy.id} <span>•</span> {strategy.status}</div><h2>{strategy.name}</h2><p>{strategy.description || 'No description'}</p></div>
      <div className="strategy-actions">
        <div className="strategy-pnl-wrap"><span>{strategy.priced_legs}/{strategy.total_legs} legs priced</span><strong className={'strategy-pnl '+pnlClass(strategy.pnl)}>{money(strategy.pnl)}</strong></div>
        {strategy.status === 'OPEN' && <button className="danger" onClick={() => onAction(strategy.id,'exit')}>Exit</button>}
        <button className="danger muted-danger" onClick={() => onDelete(strategy.id)}>Delete</button>
      </div>
    </div>
    <div className="position-strip">
      {strategy.orders.map(o => <div className="leg-chip" key={o.id}><span className={'side-dot '+o.side.toLowerCase()}></span><strong>{o.symbol} {o.strike} {o.option_type}</strong><span>{o.side}</span><b>₹{o.current_ltp == null ? '—' : o.current_ltp.toFixed(2)}</b></div>)}
    </div>
    <div className="table-wrap strategy-table">
      <table><thead><tr><th>Leg</th><th>Side</th><th>Entry</th><th>LTP</th><th>Lots</th><th>Qty</th><th>P&L</th><th/></tr></thead>
      <tbody>{strategy.orders.map(o => <tr key={o.id}>
        <td><strong>{o.symbol} {o.strike} {o.option_type}</strong><small>{o.trading_symbol || o.instrument_key}</small></td>
        <td><span className={'badge '+o.side.toLowerCase()}>{o.side}</span></td>
        <td>₹{o.entry_price.toFixed(2)}</td><td>{o.current_ltp == null ? '—' : '₹'+o.current_ltp.toFixed(2)}</td><td>{o.lots}</td><td>{o.quantity}</td>
        <td className={o.pnl == null ? '' : pnlClass(o.pnl)}>{money(o.pnl)}</td>
        <td>{strategy.status === 'OPEN' && o.status === 'OPEN' && <button className="danger table-action" onClick={() => onAction(strategy.id,'close',o.id)}>Close</button>}</td>
      </tr>)}</tbody></table>
    </div>
    <RiskPanel strategy={strategy}/>
  </article>
}

function App() {
  const [dashboard,setDashboard] = useState({strategies:[],total_pnl:0,open_orders:0,market_data_mode:'upstox'})
  const [market,setMarket] = useState({status:'DISCONNECTED',mode:'upstox',subscribed:[],last_error:null})
  const [name,setName] = useState(''),[description,setDescription] = useState(''),[orders,setOrders] = useState([emptyOrder()]),[message,setMessage] = useState(''),[loading,setLoading] = useState(false),[connecting,setConnecting] = useState(false)

  const refresh = async () => {
    try {
      const [d,m] = await Promise.all([fetch(apiUrl('/api/dashboard')),fetch(apiUrl('/api/market/status'))])
      if(d.ok) setDashboard(await d.json())
      if(m.ok) setMarket(await m.json())
    } catch(e) { setMessage('Backend unavailable: '+e.message) }
  }
  useEffect(() => { refresh(); const t=setInterval(refresh,3000); return () => clearInterval(t) }, [])

  const createStrategy = async e => {
    e.preventDefault(); setLoading(true); setMessage('')
    try {
      const normalized = orders.map(o => ({...o,strike:Number(o.strike),entry_price:Number(o.entry_price),lots:Number(o.lots)}))
      const r = await fetch(apiUrl('/api/strategies'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description,orders:normalized})})
      const b=await r.json(); if(!r.ok) throw new Error(b.detail||'Failed')
      setName('');setDescription('');setOrders([emptyOrder()]);setMessage(`Created paper strategy #${b.id}`);await refresh()
    } catch(e){setMessage(e.message)} finally{setLoading(false)}
  }

  const connectMarket = async () => {
    setConnecting(true)
    try {
      const r=await fetch(apiUrl('/api/market/connect'),{method:'POST'}); const b=await r.json()
      if(!r.ok) throw new Error(b.detail||'Market connection failed')
      setMessage(b.message || `Feed refreshed · ${b.subscribed} option instruments`); await refresh()
    } catch(e){setMessage(e.message)} finally{setConnecting(false)}
  }

  const deleteStrategy = async id => { if(!window.confirm('Delete this paper strategy and its risk history?')) return; const r=await fetch(apiUrl(`/api/strategies/${id}`),{method:'DELETE'}); if(r.ok) refresh() }
  const strategyAction = async (id,action,orderId) => {
    const confirmText = action === 'exit' ? 'Exit this paper strategy?' : 'Close this paper leg?'
    if(!window.confirm(confirmText)) return
    const path=action==='exit'?'/exit':'/adjust'; const body=action==='exit'?{reason:'Manual paper exit'}:{action:'CLOSE_LEG',order_id:orderId,reason:'Manual paper adjustment'}
    const r=await fetch(apiUrl(`/api/strategies/${id}${path}`),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    if(!r.ok){const b=await r.json();setMessage(b.detail||'Action failed');return}; await refresh()
  }

  const updateOrder=(i,f,v)=>setOrders(c=>c.map((o,j)=>j===i?{...o,[f]:v}:o))
  const addOrder=()=>setOrders(c=>[...c,emptyOrder()])
  const removeOrder=i=>setOrders(c=>c.length===1?c:c.filter((_,j)=>j!==i))
  const pnlClass=v=>v>=0?'positive':'negative'
  const connectionClass=market.status.includes('CONNECTED')?'connected':market.status.startsWith('ERROR')?'error':'connecting'

  return <div className="app">
    <header className="topbar">
      <div className="topbar-inner">
        <div><div className="brand-kicker">PAPER TRADING · RISK ENGINE</div><h1>Paper Trader</h1><p>Multi-leg NSE options · live monitoring · paper only</p></div>
        <div className="topbar-right"><div className={'status '+connectionClass}><span className="dot"/>{market.status}</div><button className="topbar-button" onClick={connectMarket} disabled={connecting}>{connecting?'Refreshing…':'Refresh feed'}</button></div>
      </div>
    </header>

    <main>
      {market.last_error && <div className="error-box"><strong>Market data error</strong><span>{market.last_error}</span></div>}

      <section className="overview-grid">
        <div className="overview-card overview-pnl"><span>Total paper P&L</span><strong className={pnlClass(dashboard.total_pnl)}>{money(dashboard.total_pnl)}</strong><small>Across all strategies</small></div>
        <div className="overview-card"><span>Strategies</span><strong>{dashboard.strategies.length}</strong><small>Tracked strategies</small></div>
        <div className="overview-card"><span>Open legs</span><strong>{dashboard.open_orders}</strong><small>Live paper positions</small></div>
        <div className="overview-card"><span>Market feed</span><strong>{dashboard.market_data_mode.toUpperCase()}</strong><small>{market.subscribed.length} instruments subscribed</small></div>
      </section>

      <section className="panel create-panel">
        <div className="panel-heading"><div><div className="section-kicker">NEW POSITION</div><h2>Create strategy</h2><p>Build any CE/PE combination and start risk tracking immediately.</p></div><span className="paper-badge">PAPER ONLY</span></div>
        <form onSubmit={createStrategy}>
          <div className="form-grid">
            <label>Strategy name<input required value={name} onChange={e=>setName(e.target.value)} placeholder="INFY Short Strangle"/></label>
            <label>Description<input value={description} onChange={e=>setDescription(e.target.value)} placeholder="Optional"/></label>
          </div>
          <div className="orders-heading"><div><h3>Option legs</h3><span>Use entry price 0 to capture the live option LTP.</span></div><button type="button" onClick={addOrder}>+ Add leg</button></div>
          <div className="table-wrap"><table className="entry-table"><thead><tr><th>Symbol</th><th>Expiry</th><th>Strike</th><th>Type</th><th>Side</th><th>Entry premium</th><th>Lots</th><th/></tr></thead>
          <tbody>{orders.map((o,i)=><tr key={i}>
            <td><input required value={o.symbol} onChange={e=>updateOrder(i,'symbol',e.target.value)} placeholder="INFY"/></td>
            <td><input required type="date" value={o.expiry} onChange={e=>updateOrder(i,'expiry',e.target.value)}/></td>
            <td><input required type="number" min="0.01" step="0.01" value={o.strike} onChange={e=>updateOrder(i,'strike',e.target.value)}/></td>
            <td><select value={o.option_type} onChange={e=>updateOrder(i,'option_type',e.target.value)}><option>CE</option><option>PE</option></select></td>
            <td><select value={o.side} onChange={e=>updateOrder(i,'side',e.target.value)}><option>SELL</option><option>BUY</option></select></td>
            <td><input required type="number" min="0" step="0.01" value={o.entry_price} onChange={e=>updateOrder(i,'entry_price',e.target.value)} placeholder="0"/></td>
            <td><input required type="number" min="1" step="1" value={o.lots} onChange={e=>updateOrder(i,'lots',e.target.value)}/></td>
            <td><button className="danger icon-button" type="button" onClick={()=>removeOrder(i)}>×</button></td>
          </tr>)}</tbody></table></div>
          <div className="form-footer"><span>Underlying entry baseline is captured separately from the live stock LTP.</span><button className="primary" type="submit" disabled={loading}>{loading?'Resolving…':'Create paper strategy'}</button></div>
          {message && <div className="message">{message}</div>}
        </form>
      </section>

      <section className="strategies-section">
        <div className="section-title-main"><div><div className="section-kicker">PORTFOLIO</div><h2>Strategies</h2><p>LTP and P&L refresh automatically. Risk snapshots are stored every minute.</p></div><button onClick={refresh}>Refresh</button></div>
        {dashboard.strategies.length===0 ? <div className="empty-global">No strategies yet. Create your first paper strategy above.</div> : dashboard.strategies.map(s=><StrategyCard key={s.id} strategy={s} onDelete={deleteStrategy} onAction={strategyAction} pnlClass={pnlClass}/>)}
      </section>
    </main>
  </div>
}

createRoot(document.getElementById('root')).render(<App />)
