# ============================================================
# EarthScape live heat alerts for Pakistan
# - Recent months (2014 to the last full month) for 6 major cities and their
#   average, compared with the 1991-2020 normal of the same calendar month
#   (ERA5 daily means from the Open-Meteo archive, one batched request).
# - Upcoming: the next 16 forecast days compared with each city's daily normal
#   (1991-2020 day-of-year mean, smoothed over +/- 7 days).
# Results are cached for 6 hours; the threshold is applied per request, so a
# new threshold changes the counts immediately without refetching.
# ============================================================
import datetime as dt
import threading
import time

import climate_lib as cl

CITIES = [("Karachi", 24.86, 67.01), ("Lahore", 31.55, 74.34), ("Islamabad", 33.69, 73.06),
          ("Peshawar", 34.01, 71.58), ("Quetta", 30.18, 66.99), ("Multan", 30.2, 71.47)]
COUNTRY_LABEL = "Pakistan (6-city average)"
NORMAL = (1991, 2020)
TTL = 6 * 3600
_CACHE = {"t": 0, "data": None}
_LOCK = threading.Lock()


def _as_list(data):
    return data if isinstance(data, list) else [data]


def _power_daily(lat, lon, end):
    url = cl.POWER.replace("/monthly/", "/daily/") + "?" + cl._q(parameters="T2M", community="AG", latitude=lat, longitude=lon,
                                                                start="19910101", end=end.strftime("%Y%m%d"), format="JSON")
    t = cl.cached_json(url, ttl=86400, timeout=25)["properties"]["parameter"]["T2M"]
    keys = sorted(k for k in t if t[k] is not None and t[k] > -900)
    return {"daily": {"time": ["%s-%s-%s" % (k[:4], k[4:6], k[6:]) for k in keys], "temperature_2m_mean": [t[k] for k in keys]}}


def _build():
    end = cl._last_full_month()                      # last complete month for monthly alerts
    recent_end = dt.date.today() - dt.timedelta(days=5)  # daily history runs closer to today (for the offset)
    lats = ",".join(str(c[1]) for c in CITIES)
    lons = ",".join(str(c[2]) for c in CITIES)
    source = "ERA5 via Open-Meteo archive (months) and Open-Meteo forecast (next 16 days)"
    fallback = False
    try:
        hist = _as_list(cl.cached_json(cl.ARCHIVE + "?" + cl._q(latitude=lats, longitude=lons, start_date="1991-01-01",
                                                               end_date=recent_end.isoformat(), daily="temperature_2m_mean",
                                                               timezone="GMT"),
                                       ttl=7 * 86400, timeout=25, backoff=(1.5, 4.0)))
    except Exception:
        # Open-Meteo's free quota is per IP; fall back to NASA POWER daily (MERRA-2, near real time)
        hist = [_power_daily(lat, lon, recent_end) for _, lat, lon in CITIES]
        fallback = True
        source = ("NASA POWER daily (MERRA-2) for months, because the Open-Meteo ERA5 archive was rate-limited. "
                  "Upcoming forecast alerts are paused until ERA5 is back, because a forecast can only be compared "
                  "fairly with a normal from the same model family")
    fc = _as_list(cl.cached_json(cl.FORECAST + "?" + cl._q(latitude=lats, longitude=lons, forecast_days=16, past_days=14,
                                                          daily="temperature_2m_mean,temperature_2m_max", timezone="auto"),
                                 ttl=TTL, timeout=15, backoff=(1.0, 3.0)))
    places, months_all, days_all = [], {}, {}
    for (name, lat, lon), h, f in zip(CITIES, hist, fc):
        d = h.get("daily") or {}
        times, vals = d.get("time") or [], d.get("temperature_2m_mean") or []
        # monthly means
        acc = {}
        doy = {}
        for t, v in zip(times, vals):
            if v is None:
                continue
            acc.setdefault(t[:7], []).append(v)
            y = int(t[:4])
            if NORMAL[0] <= y <= NORMAL[1]:
                k = dt.date.fromisoformat(t).timetuple().tm_yday
                k = min(k, 365)
                doy.setdefault(k, []).append(v)
        last_ym = end.strftime("%Y-%m")
        monthly = {ym: sum(v) / len(v) for ym, v in acc.items() if len(v) >= 20 and ym <= last_ym}
        normal_m = {}
        for m in range(1, 13):
            xs = [v for ym, v in monthly.items() if int(ym[5:7]) == m and NORMAL[0] <= int(ym[:4]) <= NORMAL[1]]
            normal_m[m] = sum(xs) / len(xs) if xs else None
        # smoothed daily normal (+/- 7 days, circular)
        raw = {k: sum(v) / len(v) for k, v in doy.items()}
        normal_d = {}
        for k in range(1, 366):
            win = [raw.get(((k - 1 + o) % 365) + 1) for o in range(-7, 8)]
            win = [w for w in win if w is not None]
            normal_d[k] = sum(win) / len(win) if win else None
        rows = []
        for ym in sorted(monthly):
            if ym < "2014-01":
                continue
            nm = normal_m[int(ym[5:7])]
            if nm is None:
                continue
            rows.append({"place": name, "ym": ym, "actual": round(monthly[ym], 2), "normal": round(nm, 2),
                         "diff": round(monthly[ym] - nm, 2)})
            months_all.setdefault(ym, []).append(rows[-1])
        fd = f.get("daily") or {}
        # The forecast model and the history dataset can sit on different grid
        # cells/elevations. Remove that offset using the last 14 days, which
        # both sources cover, so "forecast vs normal" compares like with like.
        obs = dict(zip(times, vals))
        today = dt.date.today().isoformat()
        pairs = [(v - obs[t]) for t, v in zip(fd.get("time") or [], fd.get("temperature_2m_mean") or [])
                 if t < today and v is not None and obs.get(t) is not None]
        offset = sum(pairs) / len(pairs) if len(pairs) >= 5 else 0.0
        days = []
        for t, v, vx in zip(fd.get("time") or [], fd.get("temperature_2m_mean") or [], fd.get("temperature_2m_max") or []):
            if v is None or t < today or fallback:
                continue
            v = v - offset
            k = min(dt.date.fromisoformat(t).timetuple().tm_yday, 365)
            nd = normal_d.get(k)
            if nd is None:
                continue
            days.append({"place": name, "date": t, "forecast": round(v, 1), "max": vx, "normal": round(nd, 1),
                         "diff": round(v - nd, 1)})
            days_all.setdefault(t, []).append(days[-1])
        places.append({"name": name, "lat": lat, "lon": lon, "months": rows, "days": days, "offset": round(offset, 2), "offset_days": len(pairs)})
    # country = average of the six cities (only where all six report)
    crow, cday = [], []
    for ym in sorted(months_all):
        r = months_all[ym]
        if len(r) == len(CITIES):
            a = sum(x["actual"] for x in r) / len(r); n = sum(x["normal"] for x in r) / len(r)
            crow.append({"place": COUNTRY_LABEL, "ym": ym, "actual": round(a, 2), "normal": round(n, 2), "diff": round(a - n, 2)})
    for t in sorted(days_all):
        r = days_all[t]
        if len(r) == len(CITIES):
            a = sum(x["forecast"] for x in r) / len(r); n = sum(x["normal"] for x in r) / len(r)
            cday.append({"place": COUNTRY_LABEL, "date": t, "forecast": round(a, 1), "max": None, "normal": round(n, 1), "diff": round(a - n, 1)})
    places.insert(0, {"name": COUNTRY_LABEL, "lat": 30.4, "lon": 69.3, "months": crow, "days": cday})
    last_ym = max((r["ym"] for p in places for r in p["months"]), default=None)
    return {"places": places, "last_month": last_ym, "built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "normal": "%d-%d" % NORMAL, "source": source, "fallback": fallback}


def cached():
    d = _CACHE["data"]
    return d if d and time.time() - _CACHE["t"] < TTL else None


def get():
    d = cached()
    if d:
        return d
    with _LOCK:
        d = cached()
        if d:
            return d
        try:
            d = _build()
            _CACHE.update(t=time.time(), data=d)
        except Exception:
            if _CACHE["data"]:          # serve the last good copy rather than nothing
                return _CACHE["data"]
            raise
    return d


def level(diff):
    return "Severe" if diff >= 3 else "High" if diff >= 2 else "Moderate"


def _months_back(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    m -= n - 1
    while m <= 0:
        m += 12; y -= 1
    return "%04d-%02d" % (y, m)


def summarize(data, threshold):
    """Apply a threshold: recent-12-month alerts, all alerts since 2014, and one
    upcoming alert per place whose forecast has any day at or above it."""
    last = data["last_month"]
    start12 = _months_back(last, 12) if last else "9999"
    recent, since2014, spells = [], [], []
    for p in data["places"]:
        for r in p["months"]:
            if r["diff"] >= threshold:
                row = dict(r, level=level(r["diff"]))
                since2014.append(row)
                if r["ym"] >= start12:
                    recent.append(row)
        hot = [x for x in p["days"] if x["diff"] >= threshold]
        if hot:
            # one upcoming alert per place (so a higher threshold never adds alerts)
            peak = max(hot, key=lambda x: x["diff"])
            spells.append({"place": p["name"], "start": hot[0]["date"], "end": hot[-1]["date"], "days": len(hot),
                           "peak_date": peak["date"], "forecast": peak["forecast"], "normal": peak["normal"],
                           "diff": peak["diff"], "level": level(peak["diff"])})
    recent.sort(key=lambda r: (-r["diff"]))
    since2014.sort(key=lambda r: (r["ym"], -r["diff"]), reverse=True)
    spells.sort(key=lambda s: (s["start"], -s["diff"]))
    months_checked = sum(len(p["months"]) for p in data["places"])
    return {"threshold": threshold, "recent": recent, "since2014": since2014, "upcoming": spells,
            "badge": len(recent) + len(spells), "months_checked": months_checked,
            "window": [start12, last]}
