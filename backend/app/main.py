from datetime import date
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from .alerts import AlertService
from .config import settings
from .db import Base, engine, get_db
from .instrument import InstrumentResolutionError, UpstoxInstrumentResolver
from .market import MarketDataService
from .models import PaperOrder, Strategy
from .pnl import order_pnl, strategy_pnl
from .schemas import DashboardView, OrderView, StrategyCreate, StrategyView

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Paper Trader", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

market = MarketDataService(
    use_mock=settings.use_mock_market_data,
    access_token=settings.upstox_access_token,
    verify_ssl=settings.upstox_verify_ssl,
)
resolver = UpstoxInstrumentResolver(
    settings.upstox_access_token,
    settings.upstox_verify_ssl,
)
alerts = AlertService(settings, market)


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

        orders.append(
            OrderView(
                id=order.id,
                symbol=order.symbol,
                instrument_key=order.instrument_key,
                trading_symbol=order.trading_symbol,
                expiry=date.fromisoformat(order.expiry),
                strike=order.strike,
                option_type=order.option_type,
                side=order.side,
                entry_price=order.entry_price,
                lots=order.lots,
                lot_size=order.lot_size,
                quantity=quantity,
                status=order.status,
                current_ltp=ltp,
                pnl=pnl,
            )
        )

    return StrategyView(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        status=strategy.status,
        created_at=strategy.created_at,
        orders=orders,
        pnl=round(total, 2),
        priced_legs=priced,
        total_legs=len(orders),
    )


@app.on_event("startup")
def startup():
    # Re-subscribe persisted open paper positions after backend restart.
    db = next(get_db())
    try:
        keys = [
            row[0]
            for row in db.query(PaperOrder.instrument_key)
            .filter(PaperOrder.status == "OPEN")
            .distinct()
            .all()
        ]
        if keys:
            market.subscribe(keys)
            alerts.start()
    finally:
        db.close()


@app.on_event("shutdown")
def shutdown():
    alerts.stop()
    market.stop()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "market_data": market.status,
        "mode": "mock" if settings.use_mock_market_data else "upstox",
        "telegram_configured": alerts.configured,
        "upstox_configured": bool(settings.upstox_access_token),
        "last_market_error": market.last_error,
    }


@app.get("/api/dashboard", response_model=DashboardView)
def dashboard(db: Session = Depends(get_db)):
    strategies = (
        db.query(Strategy)
        .options(joinedload(Strategy.orders))
        .order_by(Strategy.id.desc())
        .all()
    )
    views = [strategy_to_view(s) for s in strategies]
    return DashboardView(
        strategies=views,
        total_pnl=round(sum(s.pnl for s in views), 2),
        open_orders=sum(
            1
            for s in views
            for o in s.orders
            if o.status == "OPEN"
        ),
        market_data_mode="mock" if settings.use_mock_market_data else "upstox",
    )


@app.get("/api/strategies", response_model=list[StrategyView])
def list_strategies(db: Session = Depends(get_db)):
    strategies = (
        db.query(Strategy)
        .options(joinedload(Strategy.orders))
        .order_by(Strategy.id.desc())
        .all()
    )
    return [strategy_to_view(s) for s in strategies]


@app.get("/api/strategies/{strategy_id}", response_model=StrategyView)
def get_strategy(strategy_id: int, db: Session = Depends(get_db)):
    strategy = (
        db.query(Strategy)
        .options(joinedload(Strategy.orders))
        .filter(Strategy.id == strategy_id)
        .first()
    )
    if not strategy:
        raise HTTPException(404, "Strategy not found")
    return strategy_to_view(strategy)


@app.post("/api/strategies", response_model=StrategyView, status_code=201)
def create_strategy(payload: StrategyCreate, db: Session = Depends(get_db)):
    strategy = Strategy(
        name=payload.name.strip(),
        description=payload.description.strip(),
    )
    db.add(strategy)
    db.flush()

    try:
        for item in payload.orders:
            if settings.use_mock_market_data:
                instrument_key = (
                    f"MOCK|{item.symbol}|{item.expiry.isoformat()}|"
                    f"{item.strike:g}|{item.option_type}"
                )
                lot_size = 400 if item.symbol == "INFY" else 1
                trading_symbol = (
                    f"{item.symbol} {item.strike:g} {item.option_type} "
                    f"{item.expiry.strftime('%d %b %y').upper()}"
                )
            else:
                resolved = resolver.resolve_option(
                    item.symbol,
                    item.expiry,
                    item.strike,
                    item.option_type,
                )
                instrument_key = resolved["instrument_key"]
                lot_size = int(resolved["lot_size"])
                trading_symbol = resolved.get("trading_symbol")

            db.add(
                PaperOrder(
                    strategy_id=strategy.id,
                    symbol=item.symbol,
                    instrument_key=instrument_key,
                    trading_symbol=trading_symbol,
                    expiry=item.expiry.isoformat(),
                    strike=item.strike,
                    option_type=item.option_type,
                    side=item.side,
                    entry_price=item.entry_price,
                    lots=item.lots,
                    lot_size=lot_size,
                )
            )

        db.commit()
        db.refresh(strategy)
    except (InstrumentResolutionError, KeyError, ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc

    keys = [o.instrument_key for o in strategy.orders]
    market.subscribe(keys)
    alerts.start()
    return strategy_to_view(strategy)


@app.delete("/api/strategies/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(404, "Strategy not found")
    db.delete(strategy)
    db.commit()
    return None


@app.post("/api/market/connect")
def connect_market(db: Session = Depends(get_db)):
    keys = [
        x[0]
        for x in db.query(PaperOrder.instrument_key)
        .filter(PaperOrder.status == "OPEN")
        .distinct()
        .all()
    ]
    if not keys:
        return {
            "status": market.status,
            "subscribed": 0,
            "message": "No open paper legs to subscribe",
        }
    market.subscribe(keys)
    alerts.start()
    return {
        "status": market.status,
        "subscribed": len(keys),
        "instrument_keys": keys,
    }


@app.get("/api/market/status")
def market_status():
    return {
        "status": market.status,
        "ltps": market.get_ltps(),
        "subscribed": market.subscribed_keys(),
        "mode": "mock" if settings.use_mock_market_data else "upstox",
        "last_error": market.last_error,
    }


@app.get("/api/upstox/underlying")
def upstox_underlying(symbol: str = Query(min_length=1, max_length=30)):
    try:
        return resolver.resolve_underlying(symbol)
    except InstrumentResolutionError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/upstox/expiries")
def upstox_expiries(symbol: str = Query(min_length=1, max_length=30)):
    try:
        expiries = resolver.get_expiries(symbol)
        today = date.today().isoformat()
        return {"symbol": symbol.upper(), "expiries": [x for x in expiries if x >= today]}
    except InstrumentResolutionError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/upstox/contracts")
def upstox_contracts(
    symbol: str = Query(min_length=1, max_length=30),
    expiry: date | None = None,
):
    try:
        contracts = resolver.get_option_contracts(symbol, expiry)
        return {
            "symbol": symbol.upper(),
            "expiry": expiry.isoformat() if expiry else None,
            "contracts": contracts,
        }
    except InstrumentResolutionError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/upstox/resolve-option")
def upstox_resolve_option(
    symbol: str = Query(min_length=1, max_length=30),
    expiry: date = Query(...),
    strike: float = Query(..., gt=0),
    option_type: str = Query(..., pattern="^(CE|PE)$"),
):
    try:
        return resolver.resolve_option(
            symbol,
            expiry,
            strike,
            option_type,
        )
    except InstrumentResolutionError as exc:
        raise HTTPException(400, str(exc)) from exc


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if FRONTEND_DIST.exists():
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIST / "index.html")
