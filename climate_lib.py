# ============================================================
# EarthScape Climate Agency - climate data and projection engine
#
# Pure Python (no numpy) so the Vercel serverless bundle stays tiny.
#  - Open-Meteo archive (ERA5 reanalysis, 1960 to last month): monthly history
#  - Open-Meteo forecast: current conditions and a 16 day forecast
#  - Open-Meteo climate API (CMIP6 HighResMIP, to 2050): model cross-check
#  - Our own statistical projection: monthly climatology + linear trend fitted
#    on anomalies, with prediction intervals that widen with the horizon, and a
#    backtest (train to 2015, predict 2016 onward) to show honest error.
# Every response is cached in memory and in the temp folder.
# ============================================================
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.request

CACHE_DIR = os.path.join(tempfile.gettempdir(), "earthscape_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
_MEM = {}
_LOCK = threading.Lock()

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
CLIMATE = "https://climate-api.open-meteo.com/v1/climate"
CMIP_MODELS = ["EC_Earth3P_HR", "MPI_ESM1_2_XR", "MRI_AGCM3_2_S"]
HISTORY_START = 1970
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

WEATHER_CODES = {
    0: ("Clear sky", "sun"), 1: ("Mainly clear", "sun"), 2: ("Partly cloudy", "partly"), 3: ("Overcast", "cloud"),
    45: ("Fog", "fog"), 48: ("Rime fog", "fog"), 51: ("Light drizzle", "drizzle"), 53: ("Drizzle", "drizzle"),
    55: ("Dense drizzle", "drizzle"), 56: ("Freezing drizzle", "drizzle"), 57: ("Freezing drizzle", "drizzle"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"), 66: ("Freezing rain", "rain"),
    67: ("Freezing rain", "rain"), 71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"), 80: ("Rain showers", "rain"), 81: ("Rain showers", "rain"),
    82: ("Violent showers", "storm"), 85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm, hail", "storm"), 99: ("Thunderstorm, hail", "storm"),
}


# ---------------- caching + http ----------------
def _key(url):
    return hashlib.sha1(url.encode()).hexdigest()


def cached_json(url, ttl, timeout=20):
    """GET a JSON url with a memory + disk cache (ttl seconds). Raises on failure
    unless a stale copy exists, which is then returned instead."""
    k = _key(url)
    now = time.time()
    with _LOCK:
        hit = _MEM.get(k)
    if hit and now - hit[0] < ttl:
        return hit[1]
    path = os.path.join(CACHE_DIR, k + ".json")
    stale = None
    try:
        if os.path.exists(path):
            age = now - os.path.getmtime(path)
            with open(path) as f:
                data = json.load(f)
            if age < ttl:
                with _LOCK:
                    _MEM[k] = (now - age, data)
                return data
            stale = data
    except Exception:
        stale = None
    last_err = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "EarthScapeClimateAgency/2.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            if isinstance(data, dict) and data.get("error"):
                raise ValueError(data.get("reason", "API error"))
            with _LOCK:
                _MEM[k] = (time.time(), data)
                if len(_MEM) > 400:
                    for old in sorted(_MEM, key=lambda x: _MEM[x][0])[:100]:
                        _MEM.pop(old, None)
            try:
                with open(path, "w") as f:
                    json.dump(data, f)
            except OSError:
                pass
            return data
        except Exception as e:  # network or API error
            last_err = e
            time.sleep(0.4)
    if stale is not None:
        return stale
    raise last_err


def _q(**params):
    return urllib.parse.urlencode(params, safe=",")


def rnd(v, n=2):
    return None if v is None else round(v, n)


# ---------------- small statistics helpers ----------------
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def stdev(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def quantile(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def ols(xs, ys):
    """Ordinary least squares y = a + b x. Returns dict with slope, intercept,
    residual sd, xbar, sxx, n and lag-1 autocorrelation of the residuals."""
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
    n = len(pts)
    if n < 3:
        return None
    xbar = sum(x for x, _ in pts) / n
    ybar = sum(y for _, y in pts) / n
    sxx = sum((x - xbar) ** 2 for x, _ in pts)
    sxy = sum((x - xbar) * (y - ybar) for x, y in pts)
    b = sxy / sxx if sxx else 0.0
    a = ybar - b * xbar
    res = [y - (a + b * x) for x, y in pts]
    s = math.sqrt(sum(r * r for r in res) / max(1, n - 2))
    num = sum(res[i] * res[i - 1] for i in range(1, n))
    den = sum(r * r for r in res) or 1.0
    r1 = max(0.0, min(0.95, num / den))
    neff = max(3.0, n * (1 - r1) / (1 + r1))
    se_b = s / math.sqrt(sxx) * math.sqrt(n / neff) if sxx else 0.0
    return {"a": a, "b": b, "s": s, "xbar": xbar, "sxx": sxx, "n": n, "r1": r1, "neff": neff, "se_b": se_b,
            "res": res}


# ---------------- monthly history (Open-Meteo archive, ERA5) ----------------
def _last_full_month():
    today = dt.date.today()
    # the archive lags about 5 days; use the last month that is complete by then
    ref = today - dt.timedelta(days=6)
    first = ref.replace(day=1)
    last = first - dt.timedelta(days=1)
    return last


POWER = "https://power.larc.nasa.gov/api/temporal/monthly/point"
_SOURCE = {}


def history_source(lat, lon):
    return _SOURCE.get((round(float(lat), 2), round(float(lon), 2)), "Open-Meteo Historical Weather API (ERA5 reanalysis)")


def monthly_history(lat, lon):
    """Monthly history for a point. Primary: Open-Meteo archive (ERA5, 1970 to
    last month). If Open-Meteo is rate-limiting or down, fall back to NASA POWER
    monthly (MERRA-2 based, 1981 to last full year) so the app keeps working."""
    lat = round(float(lat), 2); lon = round(float(lon), 2)
    try:
        rows = _openmeteo_history(lat, lon)
        if rows:
            _SOURCE[(lat, lon)] = "Open-Meteo Historical Weather API (ERA5 reanalysis)"
            return rows
    except Exception:
        pass
    rows = _power_history(lat, lon)
    _SOURCE[(lat, lon)] = "NASA POWER monthly (MERRA-2), used because Open-Meteo was rate-limited"
    return rows


def _power_history(lat, lon):
    last_year = dt.date.today().year - 1
    url = POWER + "?" + _q(parameters="T2M,PRECTOTCORR", community="AG", latitude=lat, longitude=lon,
                           start=1981, end=last_year, format="JSON")
    data = cached_json(url, ttl=14 * 86400, timeout=25)
    par = data["properties"]["parameter"]
    t, p = par.get("T2M", {}), par.get("PRECTOTCORR", {})
    elev = (data.get("geometry", {}).get("coordinates") or [None, None, None])[2]
    out = []
    for k in sorted(t):
        y, m = int(k[:4]), int(k[4:])
        if m > 12 or t[k] is None or t[k] <= -900:
            continue
        days = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.date(y, m, 1)).days
        pv = p.get(k)
        out.append({"ym": "%04d-%02d" % (y, m), "y": y, "m": m, "t": rnd(t[k]),
                    "p": rnd(pv * days, 1) if pv is not None and pv > -900 else None, "elev": elev})
    return out


def _openmeteo_history(lat, lon):
    end = _last_full_month()
    url = ARCHIVE + "?" + _q(latitude=lat, longitude=lon, start_date="%d-01-01" % HISTORY_START,
                             end_date=end.isoformat(),
                             daily="temperature_2m_mean,precipitation_sum",
                             timezone="GMT")
    data = cached_json(url, ttl=7 * 86400, timeout=25)
    d = data.get("daily") or {}
    times = d.get("time") or []
    tm, pr = d.get("temperature_2m_mean") or [], d.get("precipitation_sum") or []
    acc = {}
    for i, t in enumerate(times):
        ym = t[:7]
        row = acc.setdefault(ym, [[], [], [], [], 0])
        row[4] += 1
        if i < len(tm) and tm[i] is not None: row[0].append(tm[i])
        if i < len(pr) and pr[i] is not None: row[3].append(pr[i])
    out = []
    for ym in sorted(acc):
        a = acc[ym]
        if len(a[0]) < 20:
            continue
        out.append({"ym": ym, "y": int(ym[:4]), "m": int(ym[5:7]), "t": rnd(mean(a[0])),
                    "p": rnd(sum(a[3]), 1) if len(a[3]) >= 20 else None, "elev": data.get("elevation")})
    return out


def climatology(rows, y0, y1, key="t"):
    clim = {}
    for m in range(1, 13):
        clim[m] = mean([r[key] for r in rows if r["m"] == m and y0 <= r["y"] <= y1])
    return clim


def annual(rows, key="t", agg="mean"):
    by = {}
    for r in rows:
        by.setdefault(r["y"], []).append(r[key])
    out = []
    for y in sorted(by):
        vals = [v for v in by[y] if v is not None]
        if len(vals) == 12:
            out.append([y, rnd(sum(vals) / 12 if agg == "mean" else sum(vals), 2 if agg == "mean" else 1)])
    return out


def past_summary(lat, lon):
    rows = monthly_history(lat, lon)
    if not rows:
        raise ValueError("No history for this place")
    clim = climatology(rows, 1991, 2020)
    climp = climatology(rows, 1991, 2020, "p")
    b0 = max(1971, rows[0]["y"] if rows[0]["m"] == 1 else rows[0]["y"] + 1)
    b1 = b0 + 29
    base_label = "%d-%d" % (b0, b1)
    clim_old = climatology(rows, b0, b1)
    ann_t = annual(rows, "t")
    ann_p = annual(rows, "p", "sum")
    base = mean([v for y, v in ann_t if b0 <= y <= b1])
    stripes = [[y, rnd(v - base)] for y, v in ann_t] if base is not None else []
    anoms = [{"ym": r["ym"], "y": r["y"], "m": r["m"], "a": rnd(r["t"] - clim[r["m"]]) if clim[r["m"]] is not None else None}
             for r in rows]
    trend = ols([y for y, _ in ann_t if y >= 1980], [v for y, v in ann_t if y >= 1980])
    hottest = max(rows, key=lambda r: r["t"]); coldest = min(rows, key=lambda r: r["t"])
    wettest = max((r for r in rows if r["p"] is not None), key=lambda r: r["p"], default=None)
    biggest = max((a for a in anoms if a["a"] is not None), key=lambda a: a["a"], default=None)
    recent10 = [r for r in rows if r["y"] >= rows[-1]["y"] - 9]
    return {
        "monthly": [[r["ym"], r["t"], r["p"]] for r in rows],
        "climatology": {"t": [rnd(clim[m]) for m in range(1, 13)], "p": [rnd(climp[m], 1) for m in range(1, 13)],
                        "t_base": [rnd(clim_old[m]) for m in range(1, 13)],
                        "t_recent10": [rnd(mean([r["t"] for r in recent10 if r["m"] == m])) for m in range(1, 13)],
                        },
        "annual_t": ann_t, "annual_p": ann_p, "stripes": stripes,
        "anomalies": [[a["ym"], a["a"]] for a in anoms],
        "trend_per_decade": rnd(trend["b"] * 10, 3) if trend else None,
        "trend_se_per_decade": rnd(trend["se_b"] * 10, 3) if trend else None,
        "base_label": base_label,
        "warming_vs_base": rnd(mean([v for y, v in ann_t[-10:]]) - base) if base is not None and ann_t else None,
        "extremes": {
            "hottest_month": [hottest["ym"], hottest["t"]], "coldest_month": [coldest["ym"], coldest["t"]],
            "wettest_month": [wettest["ym"], wettest["p"]] if wettest else None,
            "biggest_anomaly": [biggest["ym"], biggest["a"]] if biggest else None,
            "hottest_year": max(ann_t, key=lambda x: x[1]) if ann_t else None,
            "wettest_year": max(ann_p, key=lambda x: x[1]) if ann_p else None,
            "driest_year": min(ann_p, key=lambda x: x[1]) if ann_p else None,
        },
        "range": [rows[0]["ym"], rows[-1]["ym"]],
        "elevation": rows[0].get("elev"),
        "source": history_source(lat, lon),
    }


# ---------------- present: current + 16 day forecast ----------------
def present(lat, lon):
    lat = round(float(lat), 3); lon = round(float(lon), 3)
    url = FORECAST + "?" + _q(
        latitude=lat, longitude=lon, timezone="auto", forecast_days=16,
        current="temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,surface_pressure,precipitation,cloud_cover,is_day",
        hourly="temperature_2m,precipitation_probability",
        daily="weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,uv_index_max,sunrise,sunset")
    w = cached_json(url, ttl=900, timeout=12)
    cur = w.get("current") or {}
    d = w.get("daily") or {}
    days = []
    for i, t in enumerate(d.get("time") or []):
        code = (d.get("weather_code") or [None])[i]
        lab, icon = WEATHER_CODES.get(code, ("Unknown", "cloud"))
        g = lambda k: (d.get(k) or [None] * (i + 1))[i]
        days.append({"date": t, "code": code, "sky": lab, "icon": icon, "tmax": g("temperature_2m_max"),
                     "tmin": g("temperature_2m_min"), "rain": g("precipitation_sum"),
                     "pop": g("precipitation_probability_max"), "wind": g("wind_speed_10m_max"),
                     "uv": g("uv_index_max"), "sunrise": (g("sunrise") or "")[11:16], "sunset": (g("sunset") or "")[11:16]})
    h = w.get("hourly") or {}
    now_iso = cur.get("time", "")
    hours = []
    for i, t in enumerate(h.get("time") or []):
        if t >= now_iso[:13] and len(hours) < 48:
            hours.append([t, (h.get("temperature_2m") or [None])[i], (h.get("precipitation_probability") or [None])[i]])
    lab, icon = WEATHER_CODES.get(cur.get("weather_code"), ("Unknown", "cloud"))
    return {"current": {"time": now_iso, "temp": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"),
                        "humidity": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m"),
                        "wind_dir": cur.get("wind_direction_10m"), "pressure": cur.get("surface_pressure"),
                        "rain": cur.get("precipitation"), "cloud": cur.get("cloud_cover"), "is_day": cur.get("is_day"),
                        "code": cur.get("weather_code"), "sky": lab, "icon": icon},
            "timezone": w.get("timezone"), "days": days, "hours": hours,
            "source": "Open-Meteo Forecast API"}


# ---------------- many cities at once (live board) ----------------
def live_cities(cities):
    lats = ",".join(str(c[2]) for c in cities)
    lons = ",".join(str(c[3]) for c in cities)
    url = FORECAST + "?" + _q(latitude=lats, longitude=lons, timezone="auto", forecast_days=1,
                              current="temperature_2m,weather_code,wind_speed_10m,precipitation,relative_humidity_2m",
                              daily="temperature_2m_max,temperature_2m_min")
    data = cached_json(url, ttl=900, timeout=15)
    if isinstance(data, dict):
        data = [data]
    out = []
    for c, w in zip(cities, data):
        cur = w.get("current") or {}
        d = w.get("daily") or {}
        lab, icon = WEATHER_CODES.get(cur.get("weather_code"), ("Unknown", "cloud"))
        out.append({"city": c[0], "country": c[1], "lat": c[2], "lon": c[3], "temp": cur.get("temperature_2m"),
                    "wind": cur.get("wind_speed_10m"), "rain": cur.get("precipitation"),
                    "humidity": cur.get("relative_humidity_2m"), "sky": lab, "icon": icon,
                    "tmax": (d.get("temperature_2m_max") or [None])[0], "tmin": (d.get("temperature_2m_min") or [None])[0],
                    "time": cur.get("time")})
    return out


# ---------------- projection engine ----------------
Z80, Z95 = 1.2816, 1.96


def _fit(rows, train_from, train_to, clim_from, clim_to):
    """Fit climatology + linear trend on monthly anomalies for temperature and
    a climatology + annual-total trend for rain."""
    tr = [r for r in rows if train_from <= r["y"] <= train_to]
    clim = climatology(tr, clim_from, clim_to)
    climp = climatology(tr, clim_from, clim_to, "p")
    xs, ys, months = [], [], []
    for r in tr:
        if clim[r["m"]] is None:
            continue
        xs.append(r["y"] + (r["m"] - 0.5) / 12.0)
        ys.append(r["t"] - clim[r["m"]])
        months.append(r["m"])
    fit = ols(xs, ys)
    # residual spread per calendar month (winter months vary more than summer)
    sd_m = {}
    for m in range(1, 13):
        res_m = [fit["res"][i] for i in range(len(xs)) if months[i] == m]
        sd_m[m] = stdev(res_m) or fit["s"]
    # annual residual spread
    by_year = {}
    for i, x in enumerate(xs):
        by_year.setdefault(int(x), []).append(fit["res"][i])
    yr_means = [sum(by_year[y]) / 12 for y in sorted(by_year) if len(by_year[y]) == 12]
    sd_year = stdev(yr_means) or fit["s"] / 2
    # decadal wobble: spread of 5-year mean residuals (slow natural variability
    # such as ENSO phases that a straight trend cannot follow)
    runs = [sum(yr_means[i:i + 5]) / 5 for i in range(0, max(0, len(yr_means) - 4))]
    sd_dec = stdev(runs) if len(runs) > 3 else sd_year / 2
    # rain: annual totals, trend as a percentage of the climatological total
    ann_p = {}
    for r in tr:
        if r["p"] is not None:
            ann_p.setdefault(r["y"], []).append(r["p"])
    pyears = [y for y, v in ann_p.items() if len(v) == 12]
    ptot = [sum(ann_p[y]) for y in pyears]
    pfit = ols(pyears, ptot) if len(pyears) > 5 else None
    clim_total = sum(v for v in climp.values() if v is not None) or 1.0
    pq = {}
    for m in range(1, 13):
        vals = [r["p"] for r in tr if r["m"] == m and r["p"] is not None and clim_from <= r["y"] <= clim_to]
        pq[m] = (quantile(vals, 0.1), quantile(vals, 0.9))
    return {"clim": clim, "climp": climp, "fit": fit, "sd_m": sd_m, "sd_year": sd_year, "sd_dec": sd_dec, "pfit": pfit,
            "clim_total": clim_total, "pq": pq, "clim_years": "%d to %d" % (clim_from, clim_to),
            "train_years": "%d to %d" % (max(train_from, tr[0]["y"]), train_to)}


def _predict_month(model, y, m):
    f = model["fit"]
    x = y + (m - 0.5) / 12.0
    trend = f["a"] + f["b"] * x
    se_fit = f["s"] * math.sqrt(1.0 / f["neff"] + (x - f["xbar"]) ** 2 / f["sxx"] * (f["n"] / f["neff"]))
    se = math.sqrt(model["sd_m"][m] ** 2 + se_fit ** 2 + model["sd_dec"] ** 2)
    t = model["clim"][m] + trend
    # rain: scale climatology by the fitted change in annual totals
    climp = model["climp"][m] or 0.0
    factor = 1.0
    if model["pfit"]:
        p0 = model["pfit"]["a"] + model["pfit"]["b"] * model["pfit"]["xbar"]
        p1 = model["pfit"]["a"] + model["pfit"]["b"] * y
        if p0 > 0:
            factor = max(0.6, min(1.4, p1 / p0))
    lo, hi = model["pq"][m]
    return {"t": t, "se": se, "se_fit": se_fit, "p": climp * factor,
            "p_lo": (lo or 0) * factor, "p_hi": (hi or climp) * factor}


def _predict_year(model, y):
    f = model["fit"]
    x = y + 0.5
    se_fit = f["s"] * math.sqrt(1.0 / f["neff"] + (x - f["xbar"]) ** 2 / f["sxx"] * (f["n"] / f["neff"]))
    t = mean([model["clim"][m] for m in range(1, 13)]) + f["a"] + f["b"] * x
    return t, math.sqrt(model["sd_year"] ** 2 + se_fit ** 2 + model["sd_dec"] ** 2)


def cmip6(lat, lon, first_year, last_year, obs_annual):
    """Annual mean temperature and rain from 3 CMIP6 HighResMIP models (Open-Meteo
    climate API, already downscaled and bias-corrected to ERA5-Land). We also
    remove any remaining offset against our ERA5 observations over 2015 to 2024."""
    last_year = min(last_year, 2049)
    url = CLIMATE + "?" + _q(latitude=round(float(lat), 2), longitude=round(float(lon), 2),
                             start_date="2015-01-01", end_date="%d-12-31" % last_year,
                             models=",".join(CMIP_MODELS), daily="temperature_2m_mean")
    data = cached_json(url, ttl=30 * 86400, timeout=25)
    d = data.get("daily") or {}
    times = d.get("time") or []
    obs = dict(obs_annual)
    models = {}
    for mname in CMIP_MODELS:
        tv = d.get("temperature_2m_mean_" + mname) or []
        by = {}
        for i, t in enumerate(times):
            y = int(t[:4])
            row = by.setdefault(y, [[], []])
            if i < len(tv) and tv[i] is not None: row[0].append(tv[i])
        ann = {y: (sum(v[0]) / len(v[0]), None) for y, v in by.items() if len(v[0]) > 300}
        if not ann:
            continue
        overlap = [ann[y][0] - obs[y] for y in range(2015, 2025) if y in ann and y in obs]
        off = mean(overlap) or 0.0
        models[mname] = {y: (v[0] - off, v[1]) for y, v in ann.items()}
    years = list(range(2015, last_year + 1))
    ens = []
    for y in years:
        vals = [models[m][y][0] for m in models if y in models[m]]
        if vals:
            ens.append({"year": y, "t": rnd(mean(vals)), "t_min": rnd(min(vals)), "t_max": rnd(max(vals)),
                        })
    return {"models": list(models.keys()), "ensemble": ens,
            "per_model": {m: [[y, rnd(v[0])] for y, v in sorted(models[m].items())] for m in models},
            "note": "CMIP6 HighResMIP models via the Open-Meteo Climate API (high-emission pathway, close to RCP8.5), "
                    "downscaled to about 10 km and bias-corrected to ERA5-Land. Remaining offset to our ERA5 record removed using 2015 to 2024."}


def projection(lat, lon, years=10, with_cmip=True):
    years = max(2, min(10, int(years)))
    rows = monthly_history(lat, lon)
    if len(rows) < 240:
        raise ValueError("Not enough monthly history for a projection")
    last = rows[-1]
    model = _fit(rows, 1980, last["y"], 1991, 2020)
    # months ahead
    out_m = []
    y, m = last["y"], last["m"]
    for _ in range(years * 12):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        p = _predict_month(model, y, m)
        out_m.append({"ym": "%04d-%02d" % (y, m), "t": rnd(p["t"]), "lo80": rnd(p["t"] - Z80 * p["se"]),
                      "hi80": rnd(p["t"] + Z80 * p["se"]), "lo95": rnd(p["t"] - Z95 * p["se"]),
                      "hi95": rnd(p["t"] + Z95 * p["se"]), "p": rnd(p["p"], 1), "p_lo": rnd(p["p_lo"], 1),
                      "p_hi": rnd(p["p_hi"], 1)})
    first_future = last["y"] + 1 if last["m"] == 12 else last["y"] + 1
    out_y = []
    for yy in range(first_future, last["y"] + years + 1):
        t, se = _predict_year(model, yy)
        prain = sum(_predict_month(model, yy, mm)["p"] for mm in range(1, 13))
        out_y.append({"year": yy, "t": rnd(t), "lo80": rnd(t - Z80 * se), "hi80": rnd(t + Z80 * se),
                      "lo95": rnd(t - Z95 * se), "hi95": rnd(t + Z95 * se), "p": rnd(prain, 0)})
    ann_t = annual(rows, "t")
    ann_p = annual(rows, "p", "sum")

    # backtest: train to 2015, predict 2016 onward month by month
    bt_model = _fit(rows, 1980, 2015, 1986, 2015)
    bt = []
    for r in rows:
        if r["y"] >= 2016:
            p = _predict_month(bt_model, r["y"], r["m"])
            bt.append({"ym": r["ym"], "actual": r["t"], "pred": rnd(p["t"]), "err": rnd(p["t"] - r["t"]),
                       "clim_only": rnd(bt_model["clim"][r["m"]]),
                       "inside80": abs(p["t"] - r["t"]) <= Z80 * p["se"]})
    errs = [b["err"] for b in bt]
    cl_errs = [b["clim_only"] - b["actual"] for b in bt]
    bt_years = []
    for yy in sorted({b["ym"][:4] for b in bt}):
        part = [b for b in bt if b["ym"][:4] == yy]
        if len(part) == 12:
            bt_years.append({"year": int(yy), "actual": rnd(mean([b["actual"] for b in part])),
                             "pred": rnd(mean([b["pred"] for b in part])),
                             "clim_only": rnd(mean([b["clim_only"] for b in part]))})
    metrics = {
        "months": len(bt),
        "mae": rnd(mean([abs(e) for e in errs])), "rmse": rnd(math.sqrt(mean([e * e for e in errs]))) if errs else None,
        "bias": rnd(mean(errs)),
        "mae_climatology_only": rnd(mean([abs(e) for e in cl_errs])),
        "annual_mae": rnd(mean([abs(b["pred"] - b["actual"]) for b in bt_years])) if bt_years else None,
        "annual_mae_climatology_only": rnd(mean([abs(b["clim_only"] - b["actual"]) for b in bt_years])) if bt_years else None,
        "coverage80": rnd(100.0 * sum(1 for b in bt if b["inside80"]) / len(bt), 1) if bt else None,
    }
    cm = None
    if with_cmip:
        try:
            cm = cmip6(lat, lon, first_future, last["y"] + years, ann_t)
        except Exception:
            cm = {"error": "CMIP6 models are busy (free API rate limit). Try again in a minute."}
    f = model["fit"]
    return {
        "monthly": out_m, "annual": out_y,
        "history_annual_t": ann_t, "history_annual_p": ann_p,
        "history_monthly_recent": [[r["ym"], r["t"], r["p"]] for r in rows[-60:]],
        "model": {"trend_per_decade": rnd(f["b"] * 10, 3), "trend_se_per_decade": rnd(f["se_b"] * 10, 3),
                  "train_years": model["train_years"], "climatology_years": model["clim_years"],
                  "residual_sd": rnd(f["s"]), "decadal_sd": rnd(model["sd_dec"]), "autocorr_lag1": rnd(f["r1"]),
                  "rain_trend_pct_per_decade": rnd(100.0 * model["pfit"]["b"] * 10 / model["clim_total"], 1) if model["pfit"] else None,
                  "climatology_t": [rnd(model["clim"][mm]) for mm in range(1, 13)],
                  "climatology_p": [rnd(model["climp"][mm], 1) for mm in range(1, 13)]},
        "backtest": {"train_years": "1980 to 2015", "test_from": "2016-01", "test_to": last["ym"],
                     "metrics": metrics, "monthly": bt, "annual": bt_years},
        "cmip6": cm,
        "last_observed": last["ym"], "source": history_source(lat, lon),
        "horizon_years": years,
        "method": "Monthly climatology (1991 to 2020) plus a linear warming trend fitted on 1980-onward monthly anomalies "
                  "(ERA5 via Open-Meteo). Bands are 80% and 95% prediction intervals: month-to-month weather noise plus "
                  "trend uncertainty (corrected for autocorrelation), so they widen the further ahead we look.",
    }


# ---------------- geocoding ----------------
def geocode(name):
    url = "https://geocoding-api.open-meteo.com/v1/search?" + _q(name=name, count=1, language="en", format="json")
    res = (cached_json(url, ttl=30 * 86400, timeout=8).get("results") or [])
    return res[0] if res else None


def cmip6_for(lat, lon, years=10):
    rows = monthly_history(lat, lon)
    last = rows[-1]
    return cmip6(lat, lon, last["y"] + 1, last["y"] + max(2, min(10, int(years))), annual(rows, "t"))
