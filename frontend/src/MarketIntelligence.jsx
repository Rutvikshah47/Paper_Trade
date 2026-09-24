import React, { useEffect, useMemo, useState } from 'react'

const fmtNum = (value, digits=2) => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toFixed(digits)
const fmtPct = value => value == null || !Number.isFinite(Number(value)) ? '—' : (Number(value)>=0?'+':'')+Number(value).toFixed(2)+'%'
const fmtCr = value => value == null || !Number.isFinite(Number(value)) ? '—' : (Number(value)>=0?'+':'')+Number(value).toFixed(0)+' Cr'

function toneForPct(value){
  if(value == null || !Number.isFinite(Number(value)) || Math.abs(Number(value)) < .15) return 'neutral'
  return Number(value)>0?'positive':'negative'
}

function CueCard({item}){
  const pct=item?.pct
  return <div className="mi-cue">
    <div className="mi-cue-name">{item.name}</div>
    <strong>{item.name==='US 10Y'?fmtNum(item.last,2)+'%':item.name==='USD/INR'?'₹'+fmtNum(item.last):item.name==='GIFT Nifty'?fmtNum(item.last,0):fmtNum(item.last,2)}</strong>
    <span className={'mi-change '+toneForPct(pct)}>{item.vs_nifty_close_pct!=null?fmtPct(item.vs_nifty_close_pct)+' vs Nifty close':fmtPct(pct)}</span>
  </div>
}

function SectorImpact({item}){
  const score=Number(item.score)||0
  const width=Math.min(100,Math.abs(score))
  return <div className="mi-sector">
    <div className="mi-sector-top"><strong>{item.sector}</strong><span className={score>10?'positive':score<-10?'negative':'neutral'}>{score>0?'+':''}{fmtNum(score,0)}</span></div>
    <div className="mi-sector-bar"><span className={score>10?'positive-bar':score<-10?'negative-bar':'neutral-bar'} style={{width:width+'%'}}/></div>
    <div className="mi-sector-bottom"><span>{item.direction}</span><small>{item.reason}</small></div>
    {Number(item.ai_adjustment)!==0?<div className="mi-ai-adjustment">AI news adjustment {item.ai_adjustment>0?'+':''}{fmtNum(item.ai_adjustment,0)}</div>:null}
  </div>
}

function NewsCard({item}){
  const impact=item.impact||'medium'
  return <article className={'mi-news-card '+impact}>
    <div className="mi-news-meta"><span className={'impact-badge '+impact}>{impact}</span><span>{item.source||'Google News'}</span></div>
    <h4>{item.headline}</h4>
    <p>{item.summary||'Fresh market headline captured from the configured news feed.'}</p>
    {item.sectors?.length?<div className="mi-tags">{item.sectors.map(x=><span key={x}>{x}</span>)}</div>:null}
  </article>
}

function GlobalCoverage({items}){
  const expected=['Nasdaq','Dow','S&P 500','Nikkei','Hang Seng','FTSE 100','DAX','CAC 40','Brent','WTI','USD/INR']
  const byName=new Map((items||[]).map(x=>[x.name,x]))
  return <div className="mi-global-coverage">
    {expected.map(name=>{
      const item=byName.get(name)
      const value=item?.name==='USD/INR' ? '₹'+fmtNum(item.last,2) : fmtNum(item?.last,2)
      return <div className={'mi-global-card '+(item?'available':'missing')} key={name}>
        <div className="mi-global-name">{name}</div>
        <strong>{item?value:'Not available'}</strong>
        <span className={item?toneForPct(item.pct):'neutral'}>
          {item ? (fmtPct(item.pct)+' · '+(item.source||'Upstox')) : 'Not published by Upstox'}
        </span>
      </div>
    })}
  </div>
}

function MarketIntelligence({apiUrl}){
  const [report,setReport]=useState(null)
  const [history,setHistory]=useState([])
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')
  const [health,setHealth]=useState(null)

  const load=async()=>{
    try{
      const [latest,hist,status]=await Promise.all([
        fetch(apiUrl('/api/market-intelligence/latest')),
        fetch(apiUrl('/api/market-intelligence/history?limit=8')),
        fetch(apiUrl('/api/health'))
      ])
      if(latest.ok)setReport(await latest.json())
      if(hist.ok)setHistory(await hist.json())
      if(status.ok)setHealth(await status.json())
    }catch(e){setError('Unable to load market intelligence: '+e.message)}
  }
  useEffect(()=>{load()},[])

  const generate=async()=>{
    setLoading(true);setError('')
    try{
      const response=await fetch(apiUrl('/api/market-intelligence/generate'),{method:'POST'})
      const body=await response.json()
      if(!response.ok)throw new Error(body.detail||'Report generation failed')
      setReport(body)
      await load()
    }catch(e){setError(e.message)}
    finally{setLoading(false)}
  }

  const global=report?.global_cues||[]
  const india=report?.india_snapshot||[]
  const sectors=useMemo(()=>[...(report?.sector_impacts||[])].sort((a,b)=>Math.abs(Number(b.score)||0)-Math.abs(Number(a.score)||0)),[report])
  const positiveSectors=sectors.filter(x=>Number(x.score)>10).slice(0,5)
  const negativeSectors=sectors.filter(x=>Number(x.score)<-10).slice(0,5)
  const fii=india.find(x=>x.name==='FII')
  const dii=india.find(x=>x.name==='DII')
  const breadth=india.find(x=>x.name==='Breadth')
  const nifty=india.find(x=>x.name==='Nifty 50')
  const vix=india.find(x=>x.name==='India VIX')
  const primaryIndia=useMemo(()=>india.filter(x=>!['FII','DII','Breadth'].includes(x.name)),[india])

  return <main className="mi-page">
    <section className="mi-header">
      <div><div className="section-kicker">MARKET INTELLIGENCE</div><h1>India pre-market report</h1><p>Fresh global cues, India data, grounded news and sector read-through in one view.</p></div>
      <div className="mi-header-actions">
        {report?<span className="mi-updated">{report.generated_by?.includes('Gemini failed')?'Gemini failed · Rule engine fallback':report.generated_by?.includes('Gemini')?'Gemini + Google Search':'Rule engine only'} · Updated {new Date(report.generated_at).toLocaleString()}</span>:null}
        {health?<span className="mi-updated">Service: {health.gemini_configured?'Gemini configured':'Gemini not configured'} · {health.gemini_model||'no model'} · {health.environment||'env unknown'} · {health.deployment||'deployment unknown'}</span>:null}
        <button className="button-primary" onClick={generate} disabled={loading}>{loading?'Gathering markets + news…':'↻ Generate fresh report'}</button>
      </div>
    </section>

    {error?<div className="banner error-banner">{error}</div>:null}

    {!report?<div className="mi-empty"><strong>No report generated yet</strong><span>Click Generate fresh report to fetch current market data and Gemini-grounded news.</span><button className="button-primary" onClick={generate} disabled={loading}>{loading?'Generating…':'Generate report'}</button></div>:
    <>
      <section className="mi-mood">
        <div className="mi-mood-main"><span className="mi-label">MARKET MOOD</span><h2>{report.market_mood}</h2><p>{report.summary}</p></div>
        <div className="mi-score"><span>Market pressure</span><strong className={(report.market_pressure||0)>=0?'positive':'negative'}>{report.market_pressure>0?'+':''}{fmtNum(report.market_pressure,0)}</strong><small>-100 bearish · 0 neutral · +100 positive</small></div>
        <div className="mi-score"><span>Confidence</span><strong>{fmtNum(report.confidence,0)}%</strong><small>Based on data coverage + news agreement</small></div>
      </section>

      <section className="mi-section">
        <div className="mi-section-head"><div><h2>Global overnight cues</h2><span>Latest fetched values used as inputs to the analysis</span></div><span className="mi-source">LIVE DATA</span></div>
        <div className="mi-cue-grid">{global.map(x=><CueCard item={x} key={x.name}/>)}</div>
        <div className="mi-subsection-title">Global market coverage</div>
        <GlobalCoverage items={[...global, ...india.filter(x=>x.name==='USD/INR')]}/>
      </section>

      <section className="mi-section">
        <div className="mi-section-head"><div><h2>India market snapshot</h2><span>NSE indices, breadth and institutional flows</span></div></div>
        <div className="mi-india-grid">
          {primaryIndia.map(x=><div className="mi-big-stat" key={x.name}><span>{x.name}</span><strong>{fmtNum(x.last, x.name.includes('VIX')?2:0)}</strong><small className={toneForPct(x.pct)}>{fmtPct(x.pct)}</small></div>)}
          <div className="mi-big-stat institutional"><span>FII</span><strong>{fmtCr(fii?.last)}</strong><small>Latest reported session</small></div>
          <div className="mi-big-stat institutional"><span>DII</span><strong>{fmtCr(dii?.last)}</strong><small>Latest reported session</small></div>
          <div className="mi-big-stat institutional"><span>Market breadth</span><strong>{breadth?breadth.advances+':'+breadth.declines:'—'}</strong><small>{breadth?breadth.advances+' advances · '+breadth.declines+' declines · '+(breadth.unchanged||0)+' unchanged':'No breadth data'}</small></div>
        </div>
      </section>

      <section className="mi-section">
        <div className="mi-section-head"><div><h2>Why is the market moving?</h2><span>Largest positive and negative drivers identified from the current inputs</span></div><span className="mi-source">RULES + GEMINI</span></div>
        <div className="mi-driver-list">{(report.drivers||[]).map((d,i)=><div className="mi-driver" key={i}><span className={'driver-symbol '+d.direction}>{d.direction==='positive'?'↑':d.direction==='negative'?'↓':'→'}</span><div><strong>{d.title}</strong><p>{d.explanation}</p></div><b>{d.impact>0?'+':''}{fmtNum(d.impact,0)}</b></div>)}</div>
      </section>

      <section className="mi-section">
        <div className="mi-section-head"><div><h2>Sector impact radar</h2><span>Rule-based sensitivity anchored to fresh market data, with explicit AI news adjustments</span></div></div>
        <div className="mi-sector-columns">
          <div><div className="mi-column-title positive">Potential support</div>{positiveSectors.length?positiveSectors.map(x=><SectorImpact key={x.sector} item={x}/>):<div className="mi-muted">No strong positive sector signal.</div>}</div>
          <div><div className="mi-column-title negative">Potential pressure</div>{negativeSectors.length?negativeSectors.map(x=><SectorImpact key={x.sector} item={x}/>):<div className="mi-muted">No strong negative sector signal.</div>}</div>
        </div>
        {sectors.length>10?<details className="mi-more"><summary>Show all sectors</summary><div className="mi-all-sectors">{sectors.map(x=><SectorImpact key={x.sector} item={x}/>)}</div></details>:null}
      </section>

      <section className="mi-section">
        <div className="mi-section-head"><div><h2>News intelligence</h2><span>Fresh web-grounded news with India sector read-through</span></div><span className="mi-source">{report.generated_by?.includes('Google News RSS')?'GOOGLE NEWS RSS':'GROUNDED SEARCH'}</span></div>
        {report.news_items?.length?<div className="mi-news-grid">{report.news_items.map((x,i)=><NewsCard item={x} key={i}/>)}</div>:<div className="mi-muted">No grounded news returned. Check data quality below and refresh.</div>}
        {report.sources?.length?<div className="mi-sources"><strong>Sources</strong>{report.sources.slice(0,10).map((x,i)=><a href={x.url} target="_blank" rel="noreferrer" key={i}>{x.title||x.url}</a>)}</div>:null}
      </section>

      <section className="mi-section">
        <div className="mi-section-head"><div><h2>Market scenarios</h2><span>Conditional paths based on observable triggers · no made-up probabilities</span></div><span className="mi-source">AI OUTLOOK</span></div>
        <div className="mi-scenario-grid">{(report.scenarios||[]).map((x,i)=><div className={'mi-scenario scenario-'+i} key={x.name||i}><div className="mi-scenario-name">{x.name}</div><div className="mi-scenario-label">Trigger</div><strong>{x.trigger||x.observable_trigger||'No trigger returned.'}</strong><div className="mi-scenario-label">India read-through</div><p>{x.read_through||x.india_market_readthrough||'No read-through returned.'}</p></div>)}{!(report.scenarios||[]).length?<div className="mi-muted">No scenario analysis returned.</div>:null}</div>
      </section>

      <section className="mi-bottom-grid">
        <div className="mi-section">
          <div className="mi-section-head"><div><h2>Today's outlook</h2><span>Conditional read-through, not a guaranteed prediction</span></div></div>
          <p className="mi-outlook">{report.outlook}</p>
          <div className="mi-subheading">Watch</div>
          <div className="mi-watch">{(report.watchlist||[]).map(x=><span key={x}>{x}</span>)}</div>
        </div>
        <div className="mi-section">
          <div className="mi-section-head"><div><h2>Events & data quality</h2><span>Items that can change the read</span></div></div>
          <div className="mi-event-list">{(report.events||[]).map((x,i)=><div key={i}>• {x}</div>)}{!(report.events||[]).length?<div className="mi-muted">No additional events returned.</div>:null}</div>
          {report.data_quality?.length?<div className="mi-quality"><strong>Data notes</strong>{report.data_quality.map((x,i)=><div key={i}>• {x}</div>)}</div>:<div className="mi-quality good">All configured market-data sources returned without recorded quality warnings.</div>}
        </div>
      </section>

      <section className="mi-section mi-history">
        <div className="mi-section-head"><div><h2>Previous reports</h2><span>Every manual generation is saved for comparison</span></div></div>
        <div className="mi-history-list">{history.map(x=><button key={x.id} onClick={()=>setReport(x)} className={x.id===report.id?'active':''}><strong>{new Date(x.generated_at).toLocaleDateString()}</strong><span>{x.market_mood}</span><b>{x.market_pressure>0?'+':''}{fmtNum(x.market_pressure,0)}</b></button>)}</div>
      </section>
    </>}
  </main>
}

export default MarketIntelligence
