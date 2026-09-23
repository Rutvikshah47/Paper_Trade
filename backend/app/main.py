from datetime import date, datetime, timezone
from pathlib import Path
from threading import Event, Thread, RLock
import time
from typing import Any
import json

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from .alerts import AlertService
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .instrument import InstrumentResolutionError, UpstoxInstrumentResolver
from .market import MarketDataService
from .models import MarketBar, PaperOrder, RiskSnapshot, Strategy, StrategyEvent
from .pnl import order_pnl
from .risk import calculate_strategy_risk
from .schemas import AdjustmentCreate, DashboardView, ExitCreate, OrderView, RiskSnapshotView, RiskView, StrategyCreate, StrategyView, StrategyEventView

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Paper Trader", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

market = MarketDataService(
    use_mock=settings.use_mock_market_data,
    access_token=settings.upstox_access_token,
    verify_ssl=settings.upstox_verify_ssl,
)
resolver = UpstoxInstrumentResolver(settings.upstox_access_token, settings.upstox_verify_ssl)
alerts = AlertService(settings, market)

_underlying_keys: dict[str, str] = {}
_tick_lock = RLock()
_running = Event()
_risk_thread: Thread | None = None
_current_bars: dict[str, dict[str, Any]] = {}


def _ensure_underlying(symbol: str) -> str | None:
    symbol = symbol.upper()
    if symbol in _underlying_keys:
        return _underlying_keys[symbol]
    try:
        if settings.use_mock_market_data:
            key = f"MOCK|{symbol}|UNDERLYING"
        else:
            key = resolver.resolve_underlying(symbol)["instrument_key"]
        _underlying_keys[symbol] = key
        market.subscribe([key])
        return key
    except Exception as exc:
        print(f"[Risk] Underlying resolution failed for {symbol}: {exc}")
        return None


def _on_market_tick(key: str, ltp: float) -> None:
    alerts.on_market_tick(key, ltp)
    with _tick_lock:
        symbol = next((s for s, k in _underlying_keys.items() if k == key), None)
        if not symbol:
            return
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        row = _current_bars.get(symbol)
        if row is None or row["timestamp"] != now:
            if row is not None:
                db = SessionLocal()
                try:
                    db.add(MarketBar(**row))
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()
            _current_bars[symbol] = {
                "symbol": symbol, "timestamp": now, "open": ltp,
                "high": ltp, "low": ltp, "close": ltp, "volume": market.get_volumes().get(key),
            }
        else:
            row["high"] = max(row["high"], ltp)
            row["low"] = min(row["low"], ltp)
            row["close"] = ltp
            volume = market.get_volumes().get(key)
            if volume is not None:
                row["volume"] = volume


market.set_callback(_on_market_tick)


def _wait_for_live_ltps(keys: list[str], timeout: float = 4.0) -> dict[str, float]:
    """Wait briefly for the websocket to populate live prices after a new subscription."""
    deadline = time.monotonic() + timeout
    wanted = {k for k in keys if k}
    while time.monotonic() < deadline:
        ltps = market.get_ltps()
        if wanted.issubset(ltps.keys()):
            return {k: ltps[k] for k in wanted}
        time.sleep(0.1)
    ltps = market.get_ltps()
    return {k: ltps[k] for k in wanted if k in ltps}


def strategy_to_view(strategy: Strategy) -> StrategyView:
    ltps = market.get_ltps()
    orders = []
    total = 0.0
    priced = 0
    for order in strategy.orders:
        ltp = ltps.get(order.instrument_key, order.current_ltp)
        quantity = order.lots * order.lot_size
        pnl = order_pnl(order.side, order.entry_price, ltp, quantity)
        if pnl is not None:
            total += pnl
            priced += 1
        orders.append(OrderView(
            id=order.id, symbol=order.symbol, instrument_key=order.instrument_key,
            trading_symbol=order.trading_symbol, expiry=date.fromisoformat(order.expiry),
            strike=order.strike, option_type=order.option_type, side=order.side,
            entry_price=order.entry_price, lots=order.lots, lot_size=order.lot_size,
            quantity=quantity, status=order.status, current_ltp=ltp, pnl=pnl,
        ))
    return StrategyView(
        id=strategy.id, name=strategy.name, description=strategy.description,
        status=strategy.status, created_at=strategy.created_at, orders=orders,
        pnl=round(total, 2), priced_legs=priced, total_legs=len(orders),
    )



def _event_view(row: StrategyEvent) -> StrategyEventView:
    return StrategyEventView(
        timestamp=row.timestamp, event_type=row.event_type, spot=row.spot,
        risk_score=row.risk_score, message=row.message,
        metadata=json.loads(row.metadata_json) if row.metadata_json else {},
    )


def _record_event(db: Session, strategy_id: int, event_type: str, spot: float | None,
                  risk_score: float | None, message: str, metadata: dict | None = None,
                  dedupe: bool = True) -> None:
    if dedupe:
        latest = db.query(StrategyEvent).filter(
            StrategyEvent.strategy_id == strategy_id,
            StrategyEvent.event_type == event_type,
        ).order_by(StrategyEvent.timestamp.desc()).first()
        if latest and latest.metadata_json == json.dumps(metadata or {}, sort_keys=True):
            return
    db.add(StrategyEvent(
        strategy_id=strategy_id, timestamp=datetime.now(timezone.utc),
        event_type=event_type, spot=spot, risk_score=risk_score,
        message=message, metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


def _entry_baseline(db: Session, strategy: Strategy, spot: float | None) -> None:
    existing = db.query(StrategyEvent).filter(
        StrategyEvent.strategy_id == strategy.id, StrategyEvent.event_type == "ENTRY"
    ).first()
    if existing:
        return
    pnl = strategy_to_view(strategy).pnl
    db.add(RiskSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc), spot=spot,
        risk_score=0.0, risk_band="NORMAL", pnl=pnl,
        delta=None, gamma=None, theta=None, vega=None,
        expected_move=None, distance_to_short_pct=None, avg_iv=None,
    ))
    _record_event(db, strategy.id, "ENTRY", spot, 0.0, "Strategy entered paper tracking")


def _threat_states(strategy: Strategy, result: dict[str, Any]) -> tuple[bool, bool, bool, bool]:
    spot, move = result.get("spot"), result.get("expected_move")
    if spot is None or not move or move <= 0:
        return False, False, False, False
    short_ce = [o.strike for o in strategy.orders if o.status == "OPEN" and o.side == "SELL" and o.option_type == "CE"]
    short_pe = [o.strike for o in strategy.orders if o.status == "OPEN" and o.side == "SELL" and o.option_type == "PE"]
    ce_threat = any(spot >= strike - move for strike in short_ce)
    pe_threat = any(spot <= strike + move for strike in short_pe)
    ce_break = any(spot >= strike for strike in short_ce)
    pe_break = any(spot <= strike for strike in short_pe)
    return ce_threat, pe_threat, ce_break, pe_break


def _save_event_transitions(db: Session, strategy: Strategy, result: dict[str, Any],
                            previous: RiskSnapshot | None) -> None:
    previous_band = previous.risk_band if previous else "NORMAL"
    current_band = result["risk_band"]
    if current_band in ("WARNING", "CRITICAL") and current_band != previous_band:
        _record_event(db, strategy.id, current_band, result.get("spot"), result.get("risk_score"),
                      f"Risk band changed to {current_band}", dedupe=False)
    current = _threat_states(strategy, result)
    prior = _threat_states(strategy, {
        "spot": previous.spot if previous else None,
        "expected_move": previous.expected_move if previous else None,
    })
    for idx, name in enumerate(("CE_THREATENED", "PE_THREATENED", "CE_RANGE_BREAK", "PE_RANGE_BREAK")):
        if current[idx] and not prior[idx]:
            _record_event(db, strategy.id, name, result.get("spot"), result.get("risk_score"),
                          name.replace("_", " ").title(), dedupe=False)



def _risk_for_strategy(db: Session, strategy: Strategy) -> dict[str, Any]:
    key = _ensure_underlying(strategy.orders[0].symbol) if strategy.orders else None
    ltps = market.get_ltps()
    for order in strategy.orders:
        live_ltp = ltps.get(order.instrument_key)
        if live_ltp is not None:
            order.current_ltp = live_ltp

    spot = ltps.get(key) if key else None
    bars = []
    if key:
        bars = db.query(MarketBar).filter(MarketBar.symbol == strategy.orders[0].symbol).order_by(MarketBar.timestamp.desc()).limit(120).all()[::-1]
    result = calculate_strategy_risk(strategy, spot, bars) if spot is not None else {
        'risk_score':0.0,'risk_band':'NORMAL','spot':None,'expected_move':None,
        'distance_to_short_pct':None,'distance_to_upper_short_pct':None,'distance_to_lower_short_pct':None,
        'delta':None,'gamma':None,'theta':None,'vega':None,
        'avg_iv':None,'technical':{},'components':{},'legs':[],
    }
    history_rows = db.query(RiskSnapshot).filter(RiskSnapshot.strategy_id == strategy.id).order_by(RiskSnapshot.timestamp.desc()).limit(180).all()
    history = [RiskSnapshotView(
        timestamp=x.timestamp, spot=x.spot, risk_score=x.risk_score, risk_band=x.risk_band,
        pnl=x.pnl, delta=x.delta, gamma=x.gamma, theta=x.theta, vega=x.vega,
        expected_move=x.expected_move, distance_to_short_pct=x.distance_to_short_pct,
        distance_to_upper_short_pct=None, distance_to_lower_short_pct=None, avg_iv=x.avg_iv
    ) for x in reversed(history_rows)]
    entry = db.query(StrategyEvent).filter(
        StrategyEvent.strategy_id == strategy.id, StrategyEvent.event_type == "ENTRY"
    ).order_by(StrategyEvent.timestamp.asc()).first()
    entry_spot = entry.spot if entry and entry.spot is not None else (history[0].spot if history else spot)
    events = db.query(StrategyEvent).filter(StrategyEvent.strategy_id == strategy.id).order_by(StrategyEvent.timestamp.asc()).limit(300).all()
    result['entry_spot'] = entry_spot
    result['spot_change_pct'] = ((spot / entry_spot)-1)*100 if spot and entry_spot else None
    result['history'] = history
    result['strategy_id'] = strategy.id
    result['probability'] = _historical_probability(db, strategy.id)
    result['events'] = [_event_view(x) for x in events]
    return result


def _historical_probability(db: Session, strategy_id: int) -> dict[str, Any] | None:
    rows = db.query(RiskSnapshot).filter(RiskSnapshot.strategy_id == strategy_id).order_by(RiskSnapshot.timestamp.asc()).all()
    if len(rows) < 20:
        return None
    buckets = {}
    for i, row in enumerate(rows):
        bucket = min(100, int(row.risk_score // 10) * 10)
        future = rows[i+1:i+31]
        if not future or row.spot is None:
            continue
        threshold = row.expected_move
        if not threshold or threshold <= 0:
            continue
        event = any(x.spot is not None and abs(x.spot-row.spot) >= threshold for x in future)
        buckets.setdefault(bucket, [0, 0]); buckets[bucket][1] += 1; buckets[bucket][0] += int(event)
    if not buckets:
        return None
    return {'sample_count': len(rows), 'buckets': [
        {'risk_min': k, 'risk_max': k+9, 'observations': v[1], 'event_rate_pct': round(v[0]/v[1]*100, 1)}
        for k, v in sorted(buckets.items()) if v[1] >= 3
    ]}


def _save_risk_snapshots() -> None:
    db = SessionLocal()
    try:
        strategies = db.query(Strategy).options(joinedload(Strategy.orders)).filter(Strategy.status == 'OPEN').all()
        for strategy in strategies:
            result = _risk_for_strategy(db, strategy)
            previous = db.query(RiskSnapshot).filter(
                RiskSnapshot.strategy_id == strategy.id
            ).order_by(RiskSnapshot.timestamp.desc()).first()
            _save_event_transitions(db, strategy, result, previous)
            pnl = strategy_to_view(strategy).pnl
            db.add(RiskSnapshot(
                strategy_id=strategy.id, timestamp=datetime.now(timezone.utc),
                spot=result['spot'], risk_score=result['risk_score'], risk_band=result['risk_band'],
                pnl=pnl, delta=result['delta'], gamma=result['gamma'], theta=result['theta'], vega=result['vega'],
                expected_move=result['expected_move'], distance_to_short_pct=result['distance_to_short_pct'], avg_iv=result['avg_iv'],
            ))
        db.commit()
    except Exception as exc:
        db.rollback(); print(f"[Risk] snapshot failed: {exc}")
    finally:
        db.close()


def _risk_loop():
    while _running.wait(60):
        _save_risk_snapshots()


@app.on_event('startup')
def startup():
    db = next(get_db())
    try:
        keys = [row[0] for row in db.query(PaperOrder.instrument_key).filter(PaperOrder.status == 'OPEN').distinct().all()]
        symbols = [row[0] for row in db.query(PaperOrder.symbol).filter(PaperOrder.status == 'OPEN').distinct().all()]
        if keys: market.subscribe(keys)
        for symbol in symbols: _ensure_underlying(symbol)
        if keys or symbols: alerts.start()
        _running.set()
        global _risk_thread
        _risk_thread = Thread(target=_risk_loop, daemon=True, name='risk-snapshot-service')
        _risk_thread.start()
        _save_risk_snapshots()
    finally:
        db.close()


@app.on_event('shutdown')
def shutdown():
    _running.clear()
    alerts.stop(); market.stop()


@app.get('/api/health')
def health() -> dict[str, Any]:
    return {'status':'ok','market_data':market.status,'mode':'mock' if settings.use_mock_market_data else 'upstox',
            'telegram_configured':alerts.configured,'upstox_configured':bool(settings.upstox_access_token),
            'last_market_error':market.last_error}


@app.get('/api/dashboard', response_model=DashboardView)
def dashboard(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).options(joinedload(Strategy.orders)).order_by(Strategy.id.desc()).all()
    views = [strategy_to_view(s) for s in strategies]
    return DashboardView(strategies=views,total_pnl=round(sum(s.pnl for s in views),2),
        open_orders=sum(1 for s in views for o in s.orders if o.status == 'OPEN'),
        market_data_mode='mock' if settings.use_mock_market_data else 'upstox')


@app.get('/api/strategies', response_model=list[StrategyView])
def list_strategies(db: Session = Depends(get_db)):
    strategies = db.query(Strategy).options(joinedload(Strategy.orders)).order_by(Strategy.id.desc()).all()
    return [strategy_to_view(s) for s in strategies]


@app.get('/api/strategies/{strategy_id}', response_model=StrategyView)
def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    strategy = db.query(Strategy).options(joinedload(Strategy.orders)).filter(Strategy.id == strategy_id).first()
    if not strategy: raise HTTPException(404, 'Strategy not found')
    return strategy_to_view(strategy)


@app.post('/api/strategies', response_model=StrategyView, status_code=201)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)):
    strategy = Strategy(name=payload.name.strip(), description=payload.description.strip())
    db.add(strategy); db.flush()
    try:
        for item in payload.orders:
            if settings.use_mock_market_data:
                instrument_key=f'MOCK|{item.symbol}|{item.expiry.isoformat()}|{item.strike:g}|{item.option_type}'
                lot_size=400 if item.symbol == 'INFY' else 1
                trading_symbol=f'{item.symbol} {item.strike:g} {item.option_type} {item.expiry.strftime("%d %b %y").upper()}'
            else:
                resolved=resolver.resolve_option(item.symbol,item.expiry,item.strike,item.option_type)
                instrument_key=resolved['instrument_key']; lot_size=int(resolved['lot_size']); trading_symbol=resolved.get('trading_symbol')
            db.add(PaperOrder(strategy_id=strategy.id,symbol=item.symbol,instrument_key=instrument_key,trading_symbol=trading_symbol,
                expiry=item.expiry.isoformat(),strike=item.strike,option_type=item.option_type,side=item.side,
                entry_price=item.entry_price,lots=item.lots,lot_size=lot_size))
        db.commit(); db.refresh(strategy)
    except (InstrumentResolutionError, KeyError, ValueError, TypeError) as exc:
        db.rollback(); raise HTTPException(400,str(exc)) from exc
    keys=[o.instrument_key for o in strategy.orders]
    market.subscribe(keys)
    underlying_keys=[_ensure_underlying(symbol) for symbol in {o.symbol for o in strategy.orders}]
    live_keys=keys + [k for k in underlying_keys if k]
    live_prices=_wait_for_live_ltps(live_keys)

    # If entry price is 0, use the actual option LTP captured immediately after subscription.
    # A paper trade should never silently start with a zero premium.
    for order in strategy.orders:
        if order.entry_price == 0:
            live=live_prices.get(order.instrument_key)
            if live is None:
                db.delete(strategy)
                db.commit()
                raise HTTPException(409, f'Live LTP unavailable for {order.trading_symbol or order.symbol}. Please connect the market feed and try again.')
            order.entry_price=live
            order.current_ltp=live

    entry_key=_underlying_keys.get(strategy.orders[0].symbol)
    entry_spot=live_prices.get(entry_key) if entry_key else None
    if entry_spot is None:
        db.delete(strategy)
        db.commit()
        raise HTTPException(409, 'Live underlying LTP unavailable. Please connect the market feed and try again.')
    _entry_baseline(db, strategy, entry_spot)
    db.commit()
    alerts.start(); return strategy_to_view(strategy)


@app.delete('/api/strategies/{strategy_id}', status_code=204)
def delete_strategy(strategy_id:int, db:Session=Depends(get_db)):
    strategy=db.query(Strategy).filter(Strategy.id==strategy_id).first()
    if not strategy: raise HTTPException(404,'Strategy not found')
    db.query(RiskSnapshot).filter(RiskSnapshot.strategy_id == strategy_id).delete(synchronize_session=False)
    db.query(StrategyEvent).filter(StrategyEvent.strategy_id == strategy_id).delete(synchronize_session=False)
    db.delete(strategy); db.commit(); return None



@app.get('/api/strategies/{strategy_id}/events', response_model=list[StrategyEventView])
def strategy_events(strategy_id: int, limit: int = Query(300, ge=1, le=1000), db: Session = Depends(get_db)):
    if not db.query(Strategy).filter(Strategy.id == strategy_id).first():
        raise HTTPException(404, 'Strategy not found')
    rows = db.query(StrategyEvent).filter(StrategyEvent.strategy_id == strategy_id).order_by(StrategyEvent.timestamp.asc()).limit(limit).all()
    return [_event_view(x) for x in rows]


@app.post('/api/strategies/{strategy_id}/adjust', response_model=StrategyView)
def adjust_strategy(strategy_id: int, payload: AdjustmentCreate, db: Session = Depends(get_db)):
    strategy = db.query(Strategy).options(joinedload(Strategy.orders)).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(404, 'Strategy not found')
    if strategy.status != 'OPEN':
        raise HTTPException(400, 'Only open strategies can be adjusted')
    if payload.action == 'CLOSE_LEG':
        if payload.order_id is None:
            raise HTTPException(400, 'order_id is required')
        order = next((x for x in strategy.orders if x.id == payload.order_id and x.status == 'OPEN'), None)
        if not order:
            raise HTTPException(404, 'Open order not found')
        live = market.get_ltps().get(order.instrument_key)
        if live is not None:
            order.current_ltp = live
        order.status = 'CLOSED'
        order.closed_at = datetime.now(timezone.utc)
        message = payload.reason or f'Closed leg {order.id}'
        _record_event(db, strategy.id, 'ADJUSTMENT', market.get_ltps().get(_underlying_keys.get(order.symbol)), None, message,
                      {'action':'CLOSE_LEG','order_id':order.id}, dedupe=False)
    else:
        if payload.order is None:
            raise HTTPException(400, 'order is required')
        item = payload.order
        if settings.use_mock_market_data:
            instrument_key=f'MOCK|{item.symbol}|{item.expiry.isoformat()}|{item.strike:g}|{item.option_type}'
            lot_size=400 if item.symbol == 'INFY' else 1
            trading_symbol=f'{item.symbol} {item.strike:g} {item.option_type} {item.expiry.strftime("%d %b %y").upper()}'
        else:
            try:
                resolved=resolver.resolve_option(item.symbol,item.expiry,item.strike,item.option_type)
            except (InstrumentResolutionError, KeyError, ValueError, TypeError) as exc:
                raise HTTPException(400,str(exc)) from exc
            instrument_key=resolved['instrument_key']; lot_size=int(resolved['lot_size']); trading_symbol=resolved.get('trading_symbol')
        order=PaperOrder(strategy_id=strategy.id,symbol=item.symbol,instrument_key=instrument_key,trading_symbol=trading_symbol,
            expiry=item.expiry.isoformat(),strike=item.strike,option_type=item.option_type,side=item.side,
            entry_price=item.entry_price,lots=item.lots,lot_size=lot_size)
        db.add(order); db.flush()
        market.subscribe([instrument_key]); _ensure_underlying(item.symbol)
        _record_event(db, strategy.id, 'ADJUSTMENT', market.get_ltps().get(_underlying_keys.get(item.symbol)), None,
                      payload.reason or f'Added leg {order.id}', {'action':'ADD_LEG','order_id':order.id}, dedupe=False)
    db.commit(); db.refresh(strategy)
    return strategy_to_view(strategy)


@app.post('/api/strategies/{strategy_id}/exit', response_model=StrategyView)
def exit_strategy(strategy_id: int, payload: ExitCreate, db: Session = Depends(get_db)):
    strategy = db.query(Strategy).options(joinedload(Strategy.orders)).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(404, 'Strategy not found')
    if strategy.status != 'OPEN':
        raise HTTPException(400, 'Strategy already closed')
    underlying_key = _underlying_keys.get(strategy.orders[0].symbol) if strategy.orders else None
    spot = market.get_ltps().get(underlying_key) if underlying_key else None
    result = _risk_for_strategy(db, strategy)
    for order in strategy.orders:
        if order.status == 'OPEN':
            live = market.get_ltps().get(order.instrument_key)
            if live is not None:
                order.current_ltp = live
            order.status = 'CLOSED'
            order.closed_at = datetime.now(timezone.utc)
    strategy.status = 'CLOSED'
    _record_event(db, strategy.id, 'EXIT', spot, result.get('risk_score'), payload.reason, {'reason':payload.reason}, dedupe=False)
    db.add(RiskSnapshot(
        strategy_id=strategy.id, timestamp=datetime.now(timezone.utc), spot=spot,
        risk_score=result.get('risk_score',0), risk_band=result.get('risk_band','NORMAL'),
        pnl=strategy_to_view(strategy).pnl, delta=result.get('delta'), gamma=result.get('gamma'),
        theta=result.get('theta'), vega=result.get('vega'), expected_move=result.get('expected_move'),
        distance_to_short_pct=result.get('distance_to_short_pct'), avg_iv=result.get('avg_iv'),
    ))
    db.commit(); db.refresh(strategy)
    return strategy_to_view(strategy)

@app.get('/api/strategies/{strategy_id}/risk', response_model=RiskView)
def strategy_risk(strategy_id:int, db:Session=Depends(get_db)):
    strategy=db.query(Strategy).options(joinedload(Strategy.orders)).filter(Strategy.id==strategy_id).first()
    if not strategy: raise HTTPException(404,'Strategy not found')
    return _risk_for_strategy(db,strategy)


@app.get('/api/strategies/{strategy_id}/risk/history', response_model=list[RiskSnapshotView])
def risk_history(strategy_id:int, limit:int=Query(180,ge=1,le=1000), db:Session=Depends(get_db)):
    rows=db.query(RiskSnapshot).filter(RiskSnapshot.strategy_id==strategy_id).order_by(RiskSnapshot.timestamp.desc()).limit(limit).all()
    return [RiskSnapshotView(timestamp=x.timestamp,spot=x.spot,risk_score=x.risk_score,risk_band=x.risk_band,pnl=x.pnl,
        delta=x.delta,gamma=x.gamma,theta=x.theta,vega=x.vega,expected_move=x.expected_move,
        distance_to_short_pct=x.distance_to_short_pct,avg_iv=x.avg_iv) for x in reversed(rows)]


@app.post('/api/market/connect')
def connect_market(db:Session=Depends(get_db)):
    keys=[x[0] for x in db.query(PaperOrder.instrument_key).filter(PaperOrder.status=='OPEN').distinct().all()]
    symbols=[x[0] for x in db.query(PaperOrder.symbol).filter(PaperOrder.status=='OPEN').distinct().all()]
    for symbol in symbols: _ensure_underlying(symbol)
    if keys: market.subscribe(keys); alerts.start()
    return {'status':market.status,'subscribed':len(keys),'instrument_keys':keys}


@app.get('/api/market/status')
def market_status():
    return {'status':market.status,'ltps':market.get_ltps(),'subscribed':market.subscribed_keys(),
            'mode':'mock' if settings.use_mock_market_data else 'upstox','last_error':market.last_error}

@app.get('/api/upstox/underlying')
def upstox_underlying(symbol:str=Query(min_length=1,max_length=30)):
    try: return resolver.resolve_underlying(symbol)
    except InstrumentResolutionError as exc: raise HTTPException(400,str(exc)) from exc

@app.get('/api/upstox/expiries')
def upstox_expiries(symbol:str=Query(min_length=1,max_length=30)):
    try:
        expiries=resolver.get_expiries(symbol); today=date.today().isoformat()
        return {'symbol':symbol.upper(),'expiries':[x for x in expiries if x>=today]}
    except InstrumentResolutionError as exc: raise HTTPException(400,str(exc)) from exc

@app.get('/api/upstox/contracts')
def upstox_contracts(symbol:str=Query(min_length=1,max_length=30),expiry:date|None=None):
    try: return {'symbol':symbol.upper(),'expiry':expiry.isoformat() if expiry else None,'contracts':resolver.get_option_contracts(symbol,expiry)}
    except InstrumentResolutionError as exc: raise HTTPException(400,str(exc)) from exc

@app.get('/api/upstox/resolve-option')
def upstox_resolve_option(symbol:str=Query(min_length=1,max_length=30),expiry:date=Query(...),strike:float=Query(...,gt=0),option_type:str=Query(...,pattern='^(CE|PE)$')):
    try: return resolver.resolve_option(symbol,expiry,strike,option_type)
    except InstrumentResolutionError as exc: raise HTTPException(400,str(exc)) from exc

FRONTEND_DIST=Path(__file__).resolve().parents[2]/'frontend'/'dist'

@app.get('/{path:path}')
def frontend(path:str):
    if path.startswith('api/'): raise HTTPException(404,'Not found')
    index=FRONTEND_DIST/'index.html'
    if not index.exists(): raise HTTPException(404,'Frontend build not found')
    requested=FRONTEND_DIST/path
    return FileResponse(requested if requested.is_file() else index)
