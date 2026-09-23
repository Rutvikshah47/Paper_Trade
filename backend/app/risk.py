import math
from datetime import datetime, timezone
from statistics import mean


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


def technical_metrics(closes, volumes=None):
    if not closes:
        return {}
    metrics = {}
    if len(closes) >= 15:
        gains = [max(closes[i]-closes[i-1], 0) for i in range(1, len(closes))][-14:]
        losses = [max(closes[i-1]-closes[i], 0) for i in range(1, len(closes))][-14:]
        avg_gain, avg_loss = mean(gains), mean(losses)
        metrics['rsi'] = 100.0 if avg_loss == 0 and avg_gain > 0 else (0.0 if avg_gain == 0 else 100 - 100/(1 + avg_gain/avg_loss))
        ups = [max(closes[i]-closes[i-1], 0) for i in range(1, len(closes))][-14:]
        downs = [max(closes[i-1]-closes[i], 0) for i in range(1, len(closes))][-14:]
        denom = sum(ups) + sum(downs)
        metrics['adx'] = 100 * abs(sum(ups)-sum(downs)) / denom if denom else 0.0
    if volumes and len(volumes) >= 10:
        current = volumes[-1]
        avg = mean(volumes[-11:-1])
        metrics['volume_ratio'] = current / avg if avg else None
        metrics['vwap'] = sum(c*v for c, v in zip(closes[-20:], volumes[-20:])) / sum(volumes[-20:]) if sum(volumes[-20:]) else None
    metrics['momentum_pct'] = ((closes[-1] / closes[-6]) - 1) * 100 if len(closes) >= 6 and closes[-6] else None
    return metrics


def risk_band(score):
    if score >= 70: return 'CRITICAL'
    if score >= 40: return 'WARNING'
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
    closes = [b.close for b in bars] if bars else []
    volumes = [b.volume for b in bars] if bars else []
    tech = technical_metrics(closes, volumes)
    momentum_score = min(100.0, abs(tech.get('momentum_pct') or 0) * 12)
    tech_score = max(momentum_score, min(100.0, (tech.get('adx') or 0) * 1.2))
    score = round(0.35*distance_score + 0.20*delta_score + 0.15*gamma_score + 0.15*iv_score + 0.15*tech_score, 1)
    if short_strikes:
        upper = max(short_strikes)
        lower = min(short_strikes)
        upper_short_distance = abs(upper - spot) / spot * 100.0
        lower_short_distance = abs(spot - lower) / spot * 100.0
        if avg_iv and avg_iv > 0:
            nearest_expiry = min(datetime.fromisoformat(o.expiry).replace(tzinfo=timezone.utc) for o in strategy.orders if o.status == 'OPEN')
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
        'components': {'distance':round(distance_score,1),'delta':round(delta_score,1),'gamma':round(gamma_score,1),'iv':round(iv_score,1),'technical':round(tech_score,1)},
        'legs': legs,
    }
