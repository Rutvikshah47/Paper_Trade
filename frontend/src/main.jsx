import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

function apiUrl(path) {
  return `${API_BASE_URL}${path}`
}

const emptyOrder = () => ({
  symbol: '',
  expiry: '',
  strike: '',
  option_type: 'CE',
  side: 'SELL',
  entry_price: '',
  lots: 1,
})

function money(value) {
  if (value === null || value === undefined) return '—'
  const sign = value >= 0 ? '+' : '-'
  return `${sign}₹${Math.abs(value).toFixed(2)}`
}

function App() {
  const [dashboard, setDashboard] = useState({
    strategies: [],
    total_pnl: 0,
    open_orders: 0,
    market_data_mode: 'upstox',
  })
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [orders, setOrders] = useState([emptyOrder()])
  const [message, setMessage] = useState('')
  const [market, setMarket] = useState({
    status: 'DISCONNECTED',
    mode: 'upstox',
    subscribed: [],
    last_error: null,
  })
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(false)

  async function refresh() {
    try {
      const [d, m] = await Promise.all([
        fetch(apiUrl('/api/dashboard')),
        fetch(apiUrl('/api/market/status')),
      ])
      if (d.ok) setDashboard(await d.json())
      if (m.ok) setMarket(await m.json())
    } catch (err) {
      setMessage(`Backend unavailable: ${err.message}`)
    }
  }

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 1500)
    return () => clearInterval(timer)
  }, [])

  const createStrategy = async (e) => {
    e.preventDefault()
    setLoading(true)
    setMessage('')
    try {
      const normalized = orders.map(o => ({
        ...o,
        strike: Number(o.strike),
        entry_price: Number(o.entry_price),
        lots: Number(o.lots),
      }))
      const response = await fetch(apiUrl('/api/strategies'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description, orders: normalized }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Failed to create strategy')
      setName('')
      setDescription('')
      setOrders([emptyOrder()])
      setMessage(`Created paper strategy #${body.id}`)
      await refresh()
    } catch (err) {
      setMessage(err.message)
    } finally {
      setLoading(false)
    }
  }

  const connectMarket = async () => {
    setConnecting(true)
    setMessage('')
    try {
      const response = await fetch(apiUrl('/api/market/connect'), { method: 'POST' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Market connection failed')
      setMessage(body.message || `Subscribed to ${body.subscribed} instrument(s)`)
      await refresh()
    } catch (err) {
      setMessage(err.message)
    } finally {
      setConnecting(false)
    }
  }

  const deleteStrategy = async (id) => {
    if (!window.confirm('Delete this paper strategy?')) return
    const response = await fetch(apiUrl(`/api/strategies/${id}`), { method: 'DELETE' })
    if (response.ok) refresh()
  }

  const updateOrder = (index, field, value) => {
    setOrders(current =>
      current.map((o, i) => (i === index ? { ...o, [field]: value } : o))
    )
  }

  const addOrder = () => setOrders(current => [...current, emptyOrder()])
  const removeOrder = (index) =>
    setOrders(current =>
      current.length === 1 ? current : current.filter((_, i) => i !== index)
    )

  const pnlClass = value => (value >= 0 ? 'positive' : 'negative')
  const connectionClass =
    market.status === 'CONNECTED' || market.status === 'CONNECTED (MOCK)'
      ? 'connected'
      : market.status.startsWith('ERROR')
        ? 'error'
        : 'connecting'

  return (
    <div className="app">
      <header>
        <div>
          <div className="eyebrow">PAPER TRADING TERMINAL</div>
          <h1>Paper Trader</h1>
          <p>Multi-leg options strategy tracker · market data only · no order placement</p>
        </div>
        <div className={`status ${connectionClass}`}>
          <span className="dot" /> {market.status}
        </div>
      </header>

      <main>
        <section className="toolbar panel">
          <div>
            <strong>Upstox Market Data</strong>
            <span className="hint">
              {market.subscribed.length} instrument(s) subscribed
            </span>
          </div>
          <button className="primary" onClick={connectMarket} disabled={connecting}>
            {connecting ? 'Connecting…' : 'Connect / Refresh Feed'}
          </button>
        </section>

        {market.last_error && (
          <div className="error-box">
            <strong>Market data error:</strong> {market.last_error}
          </div>
        )}

        <section className="stats">
          <div className="card">
            <span>Total Paper P&L</span>
            <strong className={pnlClass(dashboard.total_pnl)}>
              {money(dashboard.total_pnl)}
            </strong>
          </div>
          <div className="card">
            <span>Strategies</span>
            <strong>{dashboard.strategies.length}</strong>
          </div>
          <div className="card">
            <span>Open Legs</span>
            <strong>{dashboard.open_orders}</strong>
          </div>
          <div className="card">
            <span>Feed</span>
            <strong>{dashboard.market_data_mode.toUpperCase()}</strong>
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">
            <div>
              <h2>Create Strategy</h2>
              <span>One strategy can contain any number of CE/PE BUY/SELL legs.</span>
            </div>
          </div>

          <form onSubmit={createStrategy}>
            <div className="grid2">
              <label>
                Strategy name
                <input
                  required
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="INFY Short Strangle"
                />
              </label>
              <label>
                Description
                <input
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Optional"
                />
              </label>
            </div>

            <div className="orders-header">
              <h3>Paper legs</h3>
              <button type="button" onClick={addOrder}>+ Add leg</button>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th><th>Expiry</th><th>Strike</th><th>Type</th>
                    <th>Side</th><th>Entry</th><th>Lots</th><th />
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o, i) => (
                    <tr key={i}>
                      <td><input required value={o.symbol} onChange={e => updateOrder(i, 'symbol', e.target.value)} placeholder="INFY" /></td>
                      <td><input required type="date" value={o.expiry} onChange={e => updateOrder(i, 'expiry', e.target.value)} /></td>
                      <td><input required type="number" min="0.01" step="0.01" value={o.strike} onChange={e => updateOrder(i, 'strike', e.target.value)} /></td>
                      <td><select value={o.option_type} onChange={e => updateOrder(i, 'option_type', e.target.value)}><option>CE</option><option>PE</option></select></td>
                      <td><select value={o.side} onChange={e => updateOrder(i, 'side', e.target.value)}><option>SELL</option><option>BUY</option></select></td>
                      <td><input required type="number" min="0" step="0.01" value={o.entry_price} onChange={e => updateOrder(i, 'entry_price', e.target.value)} /></td>
                      <td><input required type="number" min="1" step="1" value={o.lots} onChange={e => updateOrder(i, 'lots', e.target.value)} /></td>
                      <td><button className="danger" type="button" onClick={() => removeOrder(i)}>×</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="form-footer">
              <span className="hint">Live mode resolves the exact Upstox instrument and lot size automatically.</span>
              <button className="primary" type="submit" disabled={loading}>
                {loading ? 'Resolving…' : 'Create paper strategy'}
              </button>
            </div>
            {message && <div className="message">{message}</div>}
          </form>
        </section>

        <section>
          <div className="section-title">
            <div>
              <h2>Strategies</h2>
              <span className="hint">LTP and P&L refresh automatically.</span>
            </div>
            <button onClick={refresh}>Refresh</button>
          </div>

          {dashboard.strategies.length === 0 ? (
            <div className="empty">No strategies yet. Create your first paper strategy above.</div>
          ) : (
            dashboard.strategies.map(s => (
              <StrategyCard
                key={s.id}
                strategy={s}
                onDelete={deleteStrategy}
                pnlClass={pnlClass}
              />
            ))
          )}
        </section>
      </main>
    </div>
  )
}

function StrategyCard({ strategy, onDelete, pnlClass }) {
  const priced = `${strategy.priced_legs}/${strategy.total_legs} legs priced`
  return (
    <article className="strategy card">
      <div className="strategy-head">
        <div>
          <div className="strategy-id">STRATEGY #{strategy.id}</div>
          <h2>{strategy.name}</h2>
          <p>{strategy.description || 'No description'}</p>
        </div>
        <div className="actions">
          <div>
            <div className="hint">{priced}</div>
            <strong className={`strategy-pnl ${pnlClass(strategy.pnl)}`}>
              {money(strategy.pnl)}
            </strong>
          </div>
          <button className="danger" onClick={() => onDelete(strategy.id)}>Delete</button>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Leg</th><th>Side</th><th>Entry</th><th>LTP</th>
              <th>Lots</th><th>Lot size</th><th>Qty</th><th>P&L</th>
            </tr>
          </thead>
          <tbody>
            {strategy.orders.map(o => (
              <tr key={o.id}>
                <td>
                  <strong>{o.symbol} {o.strike} {o.option_type}</strong>
                  <small>{o.trading_symbol || o.instrument_key}</small>
                </td>
                <td><span className={`badge ${o.side.toLowerCase()}`}>{o.side}</span></td>
                <td>₹{o.entry_price.toFixed(2)}</td>
                <td>{o.current_ltp === null ? '—' : `₹${o.current_ltp.toFixed(2)}`}</td>
                <td>{o.lots}</td>
                <td>{o.lot_size}</td>
                <td>{o.quantity}</td>
                <td className={o.pnl === null ? '' : pnlClass(o.pnl)}>{money(o.pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  )
}

createRoot(document.getElementById('root')).render(<App />)
