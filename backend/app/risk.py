import math
from datetime import datetime, timezone
from statistics import mean, median


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot, strike, t, rate, vol, option_type):
    if spot <= 0 or strike <= 0 or t <= 0 or vol <= 0:
        return max((spot - strike) if option_type == 'CE' else (strike - spot), 0.0)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if option_type == 'CE':
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * t) * _norm_cdf(d2)
    return strike * math.exp(-rate * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def implied_vol(premium, spot, strike, t, rate, option_type):
    if premium is None or premium <= 0 or spot <= 0 or strike <= 0 or t <= 0:
        return None
    intrinsic = max(spot - strike, 0.0) if option_type == 'CE' else max(strike - spot, 0.0)
    if premium < intrinsic * 0.999:
        return None

    # Black-Scholes option value is monotonic in volatility. Reject premiums
    # outside a practical numerical range instead of silently returning 500% IV.
    max_price = bs_price(spot, strike, t, rate, 5.0, option_type)
    if premium > max_price * 1.001:
        return None

    lo, hi = 1e-5, 5.0
    for _ in range(70):
        mid = (lo + hi) / 2
        p = bs_price(spot, strike, t, rate, mid, option_type)
        if p > premium:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def greeks(spot, strike, t, rate, vol, option_type):
    if spot <= 0 or strike <= 0 or t <= 0 or vol <= 0:
        return {'delta': None, 'gamma': None, 'theta': None, 'vega': None}
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * t) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    pdf = _norm_pdf(d1)
    if option_type == 'CE':
        delta = _norm_cdf(d1)
        theta = (-spot * pdf * vol / (2 * sqrt_t) - rate * strike * math.exp(-rate*t) * _norm_cdf(d2)) / 365
    else:
        delta = _norm_cdf(d1) - 1
        theta = (-spot * pdf * vol / (2 * sqrt_t) + rate * strike * math.exp(-rate*t) * _norm_cdf(-d2)) / 365
    gamma = pdf / (spot * vol * sqrt_t)
    vega = spot * pdf * sqrt_t / 100
    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega}


def signed(side):
    return 1 if side == 'BUY' else -1


def _wilder_smooth(values, period):
    if len(values) < period:
        return []
    smoothed = [sum(values[:period])]
    for value in values[period:]:
        smoothed.append(smoothed[-1] - (smoothed[-1] / period) + value)
    return smoothed


def atr_wilder(highs, lows, closes, period=14):
    if len(closes) < period + 1 or len(highs) != len(closes) or len(lows) != len(closes):
        return None

    true_ranges = []
    for i in range(1, len(closes)):
        true_ranges.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        ))

    smoothed = _wilder_smooth(true_ranges, period)
    if not smoothed:
        return None
    return smoothed[-1] / period


def _rsi_wilder(closes, period=14):
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _adx_wilder(highs, lows, closes, period=14):
    if len(closes) < period * 2 + 1 or len(highs) != len(closes) or len(lows) != len(closes):
        return None, None, None

    tr, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1]),
        ))

    tr_s = _wilder_smooth(tr, period)
    plus_s = _wilder_smooth(plus_dm, period)
    minus_s = _wilder_smooth(minus_dm, period)

    dx = []
    plus_di_values = []
    minus_di_values = []
    for tr_value, plus_value, minus_value in zip(tr_s, plus_s, minus_s):
        if tr_value <= 0:
            plus_di = minus_di = 0.0
        else:
            plus_di = 100.0 * (plus_value / tr_value)
            minus_di = 100.0 * (minus_value / tr_value)
        plus_di_values.append(plus_di)
        minus_di_values.append(minus_di)
        denom = plus_di + minus_di
        dx.append(100.0 * abs(plus_di - minus_di) / denom if denom else 0.0)

    if len(dx) < period:
        return None, plus_di_values[-1] if plus_di_values else None, minus_di_values[-1] if minus_di_values else None

    adx_seed = sum(dx[:period]) / period
    adx = adx_seed
    for value in dx[period:]:
        adx = ((adx * (period - 1)) + value) / period

    return adx, plus_di_values[-1], minus_di_values[-1]


def _is_intraday_bars(bars):
    timestamps = []
    for bar in bars[-80:]:
        value = getattr(bar, 'timestamp', None)
        if value is None:
            continue
        try:
            timestamps.append(datetime.fromisoformat(str(value).replace('Z', '+00:00')))
        except ValueError:
            continue
    if len(timestamps) < 3:
        return False
    timestamps.sort()
    deltas = [(timestamps[i] - timestamps[i-1]).total_seconds() / 60 for i in range(1, len(timestamps))]
    if not deltas:
        return False
    return median(deltas) <= 30


def technical_metrics(closes, volumes=None, highs=None, lows=None, bars=None):
    if not closes:
        return {}

    metrics = {}
    highs = highs or closes
    lows = lows or closes
    bars = bars or []

    metrics['rsi'] = _rsi_wilder(closes, 14)

    atr = atr_wilder(highs, lows, closes, 14)
    metrics['atr'] = atr
    metrics['atr_pct'] = atr / closes[-1] * 100 if atr is not None and closes[-1] else None

    adx, plus_di, minus_di = _adx_wilder(highs, lows, closes, 14)
    metrics['adx'] = adx
    metrics['plus_di'] = plus_di
    metrics['minus_di'] = minus_di

    valid_volumes = [float(v) for v in (volumes or []) if v is not None]
    if len(valid_volumes) >= 11:
        current = valid_volumes[-1]
        avg = mean(valid_volumes[-11:-1])
        metrics['volume_ratio'] = current / avg if avg else None

    if valid_volumes and len(valid_volumes) == len(closes):
        if _is_intraday_bars(bars):
            # Traditional VWAP is session-based and should reset at the
            # beginning of each trading day.
            latest_day = str(getattr(bars[-1], 'timestamp', ''))[:10] if bars else ''
            pairs = [
                (h, l, c, v)
                for h, l, c, v, b in zip(highs, lows, closes, valid_volumes, bars)
                if str(getattr(b, 'timestamp', ''))[:10] == latest_day
            ]
            if pairs:
                total_volume = sum(v for _, _, _, v in pairs)
                metrics['vwap'] = (
                    sum(((h + l + c) / 3.0) * v for h, l, c, v in pairs) / total_volume
                    if total_volume else None
                )
        else:
            # VWAP is fundamentally an intraday/session measure. On daily
            # fallback data expose a clearly named 20-bar rolling proxy rather
            # than pretending it is today's VWAP.
            pairs = list(zip(highs[-20:], lows[-20:], closes[-20:], valid_volumes[-20:]))
            total_volume = sum(v for _, _, _, v in pairs)
            metrics['rolling_vwap_20'] = (
                sum(((h + l + c) / 3.0) * v for h, l, c, v in pairs) / total_volume
                if total_volume else None
            )

    metrics['momentum_pct'] = (
        ((closes[-1] / closes[-6]) - 1) * 100
        if len(closes) >= 6 and closes[-6] else None
    )
    return metrics


def risk_band(score):
    if score >= 70:
        return 'CRITICAL'
    if score >= 40:
        return 'WARNING'
    return 'NORMAL'


def calculate_strategy_risk(strategy, spot, bars, risk_free_rate=0.06):
    now = datetime.now(timezone.utc)
    legs = []
    delta = gamma = theta = vega = 0.0
    greek_count = 0
    short_distances = []
    short_strikes = []
    expected_move = None
    upper_short_distance = None
    lower_short_distance = None

    for order in strategy.orders:
        if order.status != 'OPEN':
            continue
        ltp = order.current_ltp
        if ltp is None:
            continue
        expiry = datetime.fromisoformat(order.expiry).replace(tzinfo=timezone.utc)
        t = max((expiry - now).total_seconds() / (365*24*3600), 1/(365*24*3600))
        iv = implied_vol(ltp, spot, order.strike, t, risk_free_rate, order.option_type)
        g = greeks(spot, order.strike, t, risk_free_rate, iv, order.option_type) if iv else {'delta':None,'gamma':None,'theta':None,'vega':None}
        qty = order.lots * order.lot_size
        s = signed(order.side)
        if g['delta'] is not None:
            delta += g['delta'] * qty * s
            gamma += g['gamma'] * qty * s
            theta += g['theta'] * qty * s
            vega += g['vega'] * qty * s
            greek_count += 1
        if order.side == 'SELL':
            short_strikes.append(order.strike)
            short_distances.append(abs(order.strike - spot) / spot * 100)
        legs.append({'id':order.id,'iv':iv,'delta':g['delta'],'gamma':g['gamma'],'theta':g['theta'],'vega':g['vega']})

    if short_distances:
        nearest = min(short_distances)
        distance_score = max(0.0, min(100.0, (5.0 - nearest) / 5.0 * 100.0))
    else:
        nearest = None
        distance_score = 0.0

    avg_iv = mean([x['iv'] for x in legs if x['iv'] is not None]) if legs else None
    iv_score = max(0.0, min(100.0, ((avg_iv or 0.20) - 0.15) / 0.35 * 100.0))
    open_qty = sum(o.lots*o.lot_size for o in strategy.orders if o.status == 'OPEN')
    delta_score = min(100.0, abs(delta) / max(1.0, open_qty * 0.75) * 100)
    gamma_score = min(100.0, abs(gamma) / max(0.001, open_qty * 0.001) * 100)

    bar_rows = bars or []
    closes = [b.close for b in bar_rows if b.close is not None]
    volumes = [b.volume for b in bar_rows] if bar_rows else []
    highs = [b.high for b in bar_rows if b.high is not None]
    lows = [b.low for b in bar_rows if b.low is not None]
    # Keep OHLC aligned. Bars loaded by the backend are complete, but this
    # guard avoids subtle mismatches if a future source returns partial rows.
    aligned = [b for b in bar_rows if b.close is not None and b.high is not None and b.low is not None]
    closes = [b.close for b in aligned]
    highs = [b.high for b in aligned]
    lows = [b.low for b in aligned]
    volumes = [b.volume for b in aligned]
    tech = technical_metrics(closes, volumes, highs, lows, bars=aligned)

    momentum_score = min(100.0, abs(tech.get('momentum_pct') or 0) * 12)
    rsi_score = min(100.0, abs((tech.get('rsi') or 50) - 50) * 2)
    adx_score = min(100.0, (tech.get('adx') or 0) * 1.2)
    atr_score = min(100.0, (tech.get('atr_pct') or 0) * 20)
    volume_score = min(100.0, max(0.0, ((tech.get('volume_ratio') or 1) - 1) * 50))
    tech_score = 0.25*momentum_score + 0.20*rsi_score + 0.20*adx_score + 0.20*atr_score + 0.15*volume_score

    score = round(
        0.35*distance_score
        + 0.20*delta_score
        + 0.15*gamma_score
        + 0.15*iv_score
        + 0.15*tech_score,
        1,
    )

    if short_strikes:
        upper = max(short_strikes)
        lower = min(short_strikes)
        upper_short_distance = abs(upper - spot) / spot * 100.0
        lower_short_distance = abs(spot - lower) / spot * 100.0
        if avg_iv and avg_iv > 0:
            nearest_expiry = min(
                datetime.fromisoformat(o.expiry).replace(tzinfo=timezone.utc)
                for o in strategy.orders if o.status == 'OPEN'
            )
            t_move = max((nearest_expiry - now).total_seconds() / (365*24*3600), 1/(365*24*3600))
            expected_move = spot * avg_iv * math.sqrt(t_move)
        elif len(short_strikes) >= 2:
            expected_move = (upper - lower) / 2

    return {
        'risk_score': score,
        'risk_band': risk_band(score),
        'spot': spot,
        'expected_move': expected_move,
        'distance_to_short_pct': nearest,
        'distance_to_upper_short_pct': upper_short_distance,
        'distance_to_lower_short_pct': lower_short_distance,
        'delta': delta if greek_count else None,
        'gamma': gamma if greek_count else None,
        'theta': theta if greek_count else None,
        'vega': vega if greek_count else None,
        'avg_iv': avg_iv,
        'technical': tech,
        'components': {
            'distance': round(distance_score,1),
            'delta': round(delta_score,1),
            'gamma': round(gamma_score,1),
            'iv': round(iv_score,1),
            'technical': round(tech_score,1),
        },
        'legs': legs,
    }
