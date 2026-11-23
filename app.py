# ============================================================
# EarthScape Climate Agency - Web Application
# eProject: Big Data - EarthScape Climate Agency
# Submitted by: Taha Kazmi (student1514118)
#
# Run:  pip install flask   then   python app.py
# Open: http://127.0.0.1:5000
# Demo logins:  admin / admin123  (Administrator)
#               analyst / analyst123  (Analyst)
# ============================================================

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import csv, io, json, os, re, secrets, statistics, tempfile, time, urllib.parse, urllib.request, uuid
import climate_lib
import live_alerts
from itsdangerous import URLSafeSerializer, BadSignature
from analyst import Analyst

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "earthscape-secret-key")
BASE = os.path.dirname(os.path.abspath(__file__))

def load(name):
    with open(os.path.join(BASE, "data", name)) as f:
        return json.load(f)

YEARLY = load("yearly_by_country.json")
MODEL = load("pakistan_model.json")
ALERTS = load("alerts.json")
ANOM_PER_YEAR = load("anomalies_per_year.json")
CO2 = load("co2.json")
BASELINE = load("pakistan_baseline.json")
MONTHS_CHECKED = load("months_checked.json")
RECENT = load("recent_data.json")
ERA5 = load("era5_by_country.json")  # ERA5 country averages 1940 to now (prep_era5.py)
with open(os.path.join(BASE, "static", "es", "countries.geojson")) as _f:
    COUNTRY_GEO = {ft["properties"]["name"].lower(): ft["properties"] for ft in json.load(_f)["features"]}
ANALYST = Analyst(YEARLY, MODEL, MONTHS_CHECKED, CO2, RECENT, COUNTRY_GEO)
FIRST_YEAR = min(p[0][0] for p in YEARLY.values() if p)

def country_name(raw):
    """Turn a name from a URL into the key used in the data. Vercel can hand Flask the path
    still percent-encoded ("United%20States"), so decode it and match case-insensitively."""
    from urllib.parse import unquote
    n = unquote(unquote(raw or "")).replace("+", " ").strip()
    if n in YEARLY or n in ERA5:
        return n
    low = n.lower()
    for k in list(YEARLY) + list(ERA5):
        if k.lower() == low:
            return k
    return n

BERKELEY_LAST_FULL = 2012  # the Berkeley Earth file stops in Sept 2013, so 2013 is a part-year

def berkeley_full(name):
    return [p for p in YEARLY.get(name, []) if p[0] <= BERKELEY_LAST_FULL]

def recent_extension(name):
    """Years after the Berkeley file ends (2014 onward), taken from ERA5 and shifted onto
    Berkeley's level by the average gap between the two over the years both cover (1951-2013).
    Returns (points, offset, ytd) or ([], None, None) when ERA5 has no data for the country."""
    e = ERA5.get(name)
    b = dict(YEARLY.get(name, []))
    if not e:
        return [], None, None
    ey = dict(e["years"])
    both = [y for y in range(1951, BERKELEY_LAST_FULL + 1) if y in b and y in ey]
    if len(both) < 20:
        return [], None, None
    off = sum(b[y] - ey[y] for y in both) / len(both)
    pts = [[y, round(t + off, 2)] for y, t in e["years"] if y > BERKELEY_LAST_FULL]
    ytd = None
    if e.get("ytd"):
        z = e["ytd"]
        ytd = {"year": z["year"], "months": z["months"], "last_month": z["last_month"],
               "mean": round(z["mean"] + off, 2),
               "anomaly_vs_1991_2020": round(z["mean"] - z["normal_same_months"], 2) if z["normal_same_months"] is not None else None}
    return pts, round(off, 2), ytd

def full_series(name):
    """Berkeley Earth yearly averages plus the ERA5 extension, one point per year."""
    ext, _, _ = recent_extension(name)
    return (berkeley_full(name) if ext else list(YEARLY.get(name, []))) + ext

SETTINGS_FILE = os.path.join(BASE, "data", "settings.json")
_threshold_global = [None]

THRESHOLD_COOKIE = "es_threshold"

def _threshold_signer():
    return URLSafeSerializer(app.secret_key, salt="es-alert-threshold")

def threshold_info():
    """The alert threshold and where it came from, in priority order:
    1. a signed cookie written when an admin saves it (survives logout and cold starts, this browser only);
    2. the value saved on this server instance (lost on a serverless cold start);
    3. data/settings.json (works locally; Vercel's filesystem is read-only);
    4. the ALERT_THRESHOLD environment variable (deployment-wide default);
    5. 1.5 C, the project's default.
    A setting shared by every user on every instance needs a database or KV store."""
    raw = request.cookies.get(THRESHOLD_COOKIE) if request else None
    if raw:
        try:
            v = float(_threshold_signer().loads(raw))
            if 0.5 <= v <= 5.0:
                return v, "saved by an administrator in this browser"
        except (BadSignature, ValueError, TypeError):
            pass
    if _threshold_global[0] is not None:
        return _threshold_global[0], "set by an administrator on this server"
    try:
        with open(SETTINGS_FILE) as f:
            return float(json.load(f)["threshold"]), "saved in data/settings.json"
    except Exception:
        pass
    try:
        v = float(os.environ.get("ALERT_THRESHOLD", ""))
        if 0.5 <= v <= 5.0:
            return v, "deployment default (ALERT_THRESHOLD)"
    except ValueError:
        pass
    return ALERT_THRESHOLD, "project default"

def current_threshold():
    return threshold_info()[0]

def historical_alerts(th=None):
    """Pakistan months 2001-2013 at or above the threshold (Berkeley Earth, 1951-1980 normal),
    the same filter the Alerts page uses."""
    th = current_threshold() if th is None else th
    return [r for r in MONTHS_CHECKED if r[3] >= th]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]

@app.context_processor
def inject_alert_count():
    """Sidebar badge: live alerts at the current threshold when the 6-hour live cache is
    warm; otherwise a placeholder that the page fills from /api/alerts/summary."""
    th = current_threshold()
    live = live_alerts.cached()
    s = live_alerts.summarize(live, th) if live else None
    badge = {"count": s["badge"] if s else None, "threshold": th,
             "recent": len(s["recent"]) if s else None, "upcoming": len(s["upcoming"]) if s else None}
    return {"alert_count": badge["count"] if s else "", "alert_badge": badge, "site_stats": {"countries": len(YEARLY), "first_year": FIRST_YEAR,
            "globe_countries": len(COUNTRY_GEO), "records": "10M+"}}

def wants_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json"

# ---------------- Users and roles ----------------
USERS_FILE = os.path.join(BASE, "data", "users.json")

def load_users():
    """User accounts. Passwords start from the built-in defaults below and can
    later be changed by the Administrator (Admin page). New accounts made on
    the Sign Up page are added here too. Changes are kept in data/users.json
    when the filesystem allows it, and in memory otherwise."""
    users = {
        "admin":   {"password": generate_password_hash("admin123"),   "role": "Administrator", "name": "System Administrator", "email": ""},
        "analyst": {"password": generate_password_hash("analyst123"), "role": "Analyst",       "name": "Climate Analyst",      "email": ""},
    }
    try:
        with open(USERS_FILE) as f:
            saved = json.load(f)
        for uname, rec in saved.items():
            if rec.get("password_hash"):
                users[uname] = {
                    "password": rec["password_hash"],
                    "role": rec.get("role", users.get(uname, {}).get("role", "Analyst")),
                    "name": rec.get("name", users.get(uname, {}).get("name", uname)),
                    "email": rec.get("email", users.get(uname, {}).get("email", "")),
                }
    except Exception:
        pass
    return users

USERS = load_users()

def save_users():
    try:
        saved = {}
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE) as f:
                saved = json.load(f)
        for uname, rec in USERS.items():
            saved[uname] = {"password_hash": rec["password"], "role": rec["role"],
                            "name": rec["name"], "email": rec.get("email", "")}
        with open(USERS_FILE, "w") as f:
            json.dump(saved, f, indent=2)
    except OSError:
        pass  # read-only hosting: the in-memory change still applies

def save_user_password(uname):
    save_users()

# Password recovery requests: username -> {"code": hashed code, "expires": ts}
RECOVERY_REQUESTS = {}
ALERT_THRESHOLD = 1.5  # degrees C above the 1951-1980 baseline

def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please sign in again (your session has ended)."}), 401
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if session.get("role") != "Administrator":
            return render_template("denied.html"), 403
        return f(*a, **kw)
    return wrap

# ---------------- Authentication ----------------
_FAILED = {}  # (ip, username) -> list of failure times, for a simple lockout

def _too_many(key, window=600, limit=5):
    now = time.time()
    _FAILED[key] = [t for t in _FAILED.get(key, []) if now - t < window]
    return len(_FAILED[key]) >= limit

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        key = ((request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip(), u.lower())
        if _too_many(key):
            msg = "Too many failed attempts. Please wait 10 minutes and try again."
            if wants_json():
                return jsonify({"ok": False, "error": msg}), 429
            flash(msg, "error")
            return redirect(url_for("login"))
        picked = request.form.get("role", "")
        user = USERS.get(u)
        if user and check_password_hash(user["password"], p):
            if picked in ("Analyst", "Administrator") and picked != user["role"]:
                msg = "This is an %s account. Choose %s above and sign in again." % (user["role"], user["role"])
                if wants_json():
                    return jsonify({"ok": False, "error": msg, "field": "role"}), 400
                flash(msg, "error")
                return redirect(url_for("login"))
            _FAILED.pop(key, None)
            get_flashed_messages()  # never carry an old error past a good login
            session["user"] = u
            session["role"] = user["role"]
            session["name"] = user["name"]
            if wants_json():
                return jsonify({"ok": True, "redirect": url_for("dashboard"), "name": user["name"], "role": user["role"]})
            return redirect(url_for("dashboard"))
        _FAILED.setdefault(key, []).append(time.time())
        if wants_json():
            return jsonify({"ok": False, "error": "Invalid username or password."}), 401
        flash("Invalid username or password.", "error")
        return redirect(url_for("login"))
    # A successful login, or landing here while already signed in, must never
    # carry an old error message onto the dashboard: clear any pending ones.
    get_flashed_messages()
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- Sign up ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        u = request.form.get("username", "").strip().lower()
        pw = request.form.get("password", "")
        confirm_pw = request.form.get("confirm_password", "")
        problem = None
        if not full_name or not u or not email or not pw:
            problem = "Please fill every field before creating your account."
        elif not re.match(r"^[a-z0-9_.]{3,20}$", u):
            problem = "Choose a username of 3 to 20 characters: small letters, numbers, dot or underscore only."
        elif "@" not in email or "." not in email:
            problem = "Please enter a valid email address."
        elif u in USERS:
            problem = "That username is already taken. Please choose another one."
        elif any(rec.get("email", "").lower() == email.lower() for rec in USERS.values()):
            problem = "An account with that email already exists. Please sign in instead."
        elif len(pw) < 6:
            problem = "The password must be at least 6 characters long."
        elif pw != confirm_pw:
            problem = "The two passwords do not match. Please type them again."
        if problem:
            if wants_json():
                return jsonify({"ok": False, "error": problem}), 400
            flash(problem, "error")
            return render_template("signup.html", full_name=full_name, email=email, username=u)
        USERS[u] = {"password": generate_password_hash(pw), "role": "Analyst",
                    "name": full_name, "email": email}
        save_users()
        session["user"] = u
        session["role"] = "Analyst"
        session["name"] = full_name
        flash("Welcome to EarthScape, %s. Your account has been created." % full_name)
        if wants_json():
            return jsonify({"ok": True, "redirect": url_for("dashboard"), "name": full_name})
        return redirect(url_for("dashboard"))
    return render_template("signup.html")

# ---------------- Password recovery ----------------
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        if u in USERS:
            code = "%06d" % secrets.randbelow(1000000)
            RECOVERY_REQUESTS[u] = {"code": generate_password_hash(code),
                                     "expires": time.time() + 1800}
            return render_template("forgot.html", step="code", username=u, code=code)
        flash("No account found with that username.", "error")
    return render_template("forgot.html", step="request")

@app.route("/reset", methods=["POST"])
def reset_password():
    u = request.form.get("username", "").strip()
    code = request.form.get("code", "").strip()
    new_pw = request.form.get("new_password", "")
    confirm_pw = request.form.get("confirm_password", "")
    rec = RECOVERY_REQUESTS.get(u)
    if not rec or time.time() > rec["expires"] or not check_password_hash(rec["code"], code):
        flash("That recovery code is wrong or has expired. Please request a new one.", "error")
        return redirect(url_for("forgot"))
    if len(new_pw) < 6:
        flash("The new password must be at least 6 characters long.", "error")
        return render_template("forgot.html", step="code", username=u, code=None)
    if new_pw != confirm_pw:
        flash("The two passwords do not match. Please type them again.", "error")
        return render_template("forgot.html", step="code", username=u, code=None)
    USERS[u]["password"] = generate_password_hash(new_pw)
    save_user_password(u)
    RECOVERY_REQUESTS.pop(u, None)
    flash("Password updated. Please sign in with your new password.")
    return redirect(url_for("login"))

# ---------------- Dashboard ----------------
@app.route("/")
@login_required
def dashboard():
    stats = {
        "total_records": "10,064,718",
        "cleaned_rows": "544,811",
        "countries": len(YEARLY),
        "anomalies": len(historical_alerts()),
        "threshold": current_threshold(),
        "correlation": "0.9655",
        "forecast_2050": MODEL["forecasts"]["2050"],
    }
    pak = YEARLY["Pakistan"]
    per_year = {}
    for r in historical_alerts():
        per_year[r[0][:4]] = per_year.get(r[0][:4], 0) + 1
    per_year = {str(y): per_year.get(str(y), 0) for y in range(2001, 2014)}
    return render_template("dashboard.html", stats=stats, pakistan=pak,
                           model=MODEL, anom_per_year=per_year,
                           recent=RECENT, dash=dashboard_data())

COMPARE_COUNTRIES = ["Pakistan", "India", "Afghanistan", "Iran", "China", "Saudi Arabia",
                     "United Arab Emirates", "Bangladesh", "United Kingdom", "United States", "Russia", "Brazil"]

def dashboard_data():
    """Everything the dashboard charts need, computed from the project data."""
    pak = dict(full_series("Pakistan"))
    base = statistics.mean(t for y, t in pak.items() if 1951 <= y <= 1980)
    stripes = [[y, round(t - base, 2)] for y, t in sorted(pak.items()) if y >= 1900]
    # month x year heatmap of Pakistan anomalies (2001 to 2013) from the checked months
    heat = [[r[0][:4], int(r[0][5:7]), r[3]] for r in MONTHS_CHECKED]
    # warming rate per decade for comparison countries (1950 to 2013)
    rates = []
    for c in COMPARE_COUNTRIES:
        pts = [p for p in full_series(c) if p[0] >= 1950]
        fit = climate_lib.ols([p[0] for p in pts], [p[1] for p in pts])
        if fit:
            b = [t for y, t in pts if 1951 <= y <= 1980]
            last = [t for y, t in pts if y > pts[-1][0] - 10]
            rates.append({"country": c, "per_decade": round(fit["b"] * 10, 3),
                          "warming": round(statistics.mean(last) - statistics.mean(b), 2) if b and last else None,
                          "mean": round(statistics.mean(t for _, t in pts), 2)})
    rates.sort(key=lambda r: r["per_decade"], reverse=True)
    # countries warming the most overall (1951-1980 vs 2004-2013), from all project countries
    warm_all = []
    for c in YEARLY:
        pts = full_series(c)
        b = [t for y, t in pts if 1951 <= y <= 1980]
        last = [t for y, t in pts if y > pts[-1][0] - 10] if pts else []
        if len(b) >= 25 and len(last) >= 8:
            warm_all.append([c, round(statistics.mean(last) - statistics.mean(b), 2)])
    warm_all.sort(key=lambda r: r[1], reverse=True)
    rec = RECENT["pakistan_yearly"]
    yrs = sorted(rec)
    yoy = [[y, round(rec[y] - rec[p], 2)] for p, y in zip(yrs, yrs[1:])]
    errs = [[y, round(p - a, 2)] for y, a, p in MODEL["test_years"]]
    return {"stripes": stripes, "baseline": round(base, 2), "heat": heat, "rates": rates,
            "top_warming": warm_all[:10], "warming_count": sum(1 for r in warm_all if r[1] > 0),
            "warming_total": len(warm_all), "yoy": yoy, "errors": errs,
            "climatology": [BASELINE[str(m)] for m in range(1, 13)],
            "extremes": sorted(MONTHS_CHECKED, key=lambda r: -r[3])[:8],
            "pak_last": stripes[-1], "warmest": max(stripes, key=lambda r: r[1]),
            "last_year": stripes[-1][0], "ytd": recent_extension("Pakistan")[2]}

# ---------------- Data explorer ----------------
@app.route("/explorer")
@login_required
def explorer():
    return render_template("explorer.html", countries=sorted(YEARLY.keys()))

@app.route("/api/country")
@app.route("/api/country/<name>")
@login_required
def api_country(name=None):
    name = name or request.args.get("name", "")
    name = country_name(name)
    pts = YEARLY.get(name)
    if not pts:
        return jsonify({"error": "country not found", "country": name}), 404
    ext, off, ytd = recent_extension(name)
    if ext:
        pts = berkeley_full(name)
    temps = [t for _, t in pts + ext]
    allp = pts + ext
    return jsonify({
        "country": name, "points": pts, "recent": ext, "offset": off, "ytd": ytd,
        "records": len(allp), "from": allp[0][0], "to": allp[-1][0], "berkeley_to": pts[-1][0],
        "average": round(sum(temps) / len(temps), 2),
        "minimum": min(temps), "maximum": max(temps),
    })

# ---------------- Predictions ----------------
@app.route("/predictions")
@login_required
def predictions():
    ext, _, _ = recent_extension("Pakistan")
    check = [[y, t, round(MODEL["slope"] * y + MODEL["intercept"], 2)] for y, t in ext]
    mae = round(sum(abs(a - p) for _, a, p in check) / len(check), 2) if check else None
    return render_template("predictions.html", model=MODEL, countries=sorted(YEARLY.keys()),
                           check=check, check_mae=mae)

# ---------------- Alerts (anomaly detection output) ----------------
@app.route("/alerts")
@login_required
def alerts():
    th = current_threshold()
    rows = historical_alerts(th)
    th_source = threshold_info()[1]
    return render_template("alerts.html", alerts=rows, threshold=th, threshold_source=th_source,
                           months_checked=len(MONTHS_CHECKED),
                           countries=sorted(YEARLY.keys()))

# ---------------- Correlation ----------------
@app.route("/correlation")
@login_required
def correlation():
    return render_template("correlation.html", co2=CO2)

# ---------------- Country models (same Model 2 method, any country) ----------------
def fit_country_model(name):
    """Least squares trend line on a country's yearly averages from 1950 onward.
    Pakistan returns the official Colab verified Model 2 so its numbers never change."""
    if name == "Pakistan":
        return {"slope": MODEL["slope"], "intercept": MODEL["intercept"],
                "forecasts": MODEL["forecasts"], "official": True}
    pts = [(y, t) for y, t in YEARLY.get(name, []) if y >= 1950]
    if len(pts) < 10:
        return None
    n = len(pts)
    sx = sum(y for y, _ in pts); sy = sum(t for _, t in pts)
    sxx = sum(y * y for y, _ in pts); sxy = sum(y * t for y, t in pts)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    intercept = (sy - slope * sx) / n
    fc = {str(y): round(slope * y + intercept, 2) for y in (2030, 2040, 2050)}
    return {"slope": slope, "intercept": intercept, "forecasts": fc, "official": False,
            "years_used": "%d to %d" % (pts[0][0], pts[-1][0])}

@app.route("/api/country-model")
@app.route("/api/country-model/<name>")
@login_required
def api_country_model(name=None):
    name = name or request.args.get("name", "")
    name = country_name(name)
    m = fit_country_model(name)
    if not m:
        return jsonify({"error": "Not enough yearly data from 1950 onward for " + name + "."}), 404
    return jsonify({"country": name, "forecasts": m["forecasts"], "official": m["official"],
                    "years_used": m.get("years_used", "1950 to 2013"),
                    "note": "Official Model 2 (verified in Colab)." if m["official"] else
                            "Same Model 2 method (linear trend from 1950), calculated live from project data."})

def yearly_baseline(name):
    """A country's own normal year: the average of its yearly temperatures from
    1951 to 1980, computed live from the project data. None if too little data."""
    pts = dict(YEARLY.get(name, []))
    base_vals = [t for y, t in pts.items() if 1951 <= y <= 1980]
    if len(base_vals) < 10:
        return None
    return round(sum(base_vals) / len(base_vals), 2)

def yearly_anomalies(name, threshold):
    """Years from 2001 onward whose yearly average is at least `threshold` C above
    the country's own 1951 to 1980 yearly average. Uses Berkeley Earth to 2013 and the
    ERA5 extension after that, so the latest complete year is included."""
    pts = dict(full_series(name))
    base = yearly_baseline(name)
    if base is None:
        return None
    rows = []
    for y in sorted(pts):
        if y >= 2001:
            diff = round(pts[y] - base, 2)
            if diff >= threshold:
                rows.append([str(y), pts[y], round(base, 2), diff])
    return {"country": name, "baseline": round(base, 2), "rows": rows,
            "years_checked": sum(1 for y in pts if y >= 2001)}

@app.route("/api/yearly-alerts")
@app.route("/api/yearly-alerts/<name>")
@login_required
def api_yearly_alerts(name=None):
    name = name or request.args.get("name", "")
    name = country_name(name)
    res = yearly_anomalies(name, current_threshold())
    if res is None:
        return jsonify({"error": "Not enough 1951 to 1980 data for " + name + " to build a baseline."}), 404
    res["threshold"] = current_threshold()
    return jsonify(res)

# ---------------- Live tool: prediction ----------------
@app.route("/api/predict")
@login_required
def api_predict():
    try:
        year = int(request.args.get("year", ""))
    except ValueError:
        return jsonify({"error": "Please enter a valid year."}), 400
    if year < 2014 or year > 2100:
        return jsonify({"error": "Enter a future year between 2014 and 2100."}), 400
    country = request.args.get("country", "Pakistan")
    m = fit_country_model(country)
    if not m:
        return jsonify({"error": "Not enough yearly data from 1950 onward for " + country + "."}), 404
    pred = m["slope"] * year + m["intercept"]
    note = ("Model 2: Linear Regression trained on Pakistan data, 1950 to 2000." if country == "Pakistan"
            else "Linear trend fitted live on " + country + " yearly data from 1950 (same method as Model 2).")
    return jsonify({"year": year, "country": country, "prediction": round(pred, 2), "note": note})

# ---------------- Live tool: anomaly checker ----------------
@app.route("/api/anomaly-check")
@login_required
def api_anomaly_check():
    country = request.args.get("country", "Pakistan")
    try:
        temp = float(request.args.get("temp", ""))
    except ValueError:
        return jsonify({"error": "Enter a temperature to check."}), 400
    if temp < -60 or temp > 50:
        return jsonify({"error": "An average temperature of %g C is not physically possible. "
                                 "Averages recorded on Earth fall roughly between -60 C and +45 C. "
                                 "Please enter a realistic value." % temp}), 400
    if country and country != "Pakistan":
        # Other countries: the project data holds yearly records for them, so the
        # check compares one full year with that country's own normal year.
        base = yearly_baseline(country)
        if base is None:
            return jsonify({"error": "Not enough 1951 to 1980 data for " + country +
                                     " to build its normal year."}), 404
        try:
            year = int(request.args.get("year", ""))
        except ValueError:
            return jsonify({"error": "Enter a year to check."}), 400
        diff = round(temp - base, 2)
        alert = diff >= current_threshold()
        level = "Severe" if diff >= 3 else "High" if diff >= 2 else "Moderate" if alert else "Normal"
        return jsonify({"mode": "year", "country": country, "label": "Year %d" % year,
                        "temperature": temp, "baseline": base, "difference": diff,
                        "alert": alert, "level": level, "threshold": current_threshold()})
    try:
        month = int(request.args.get("month", ""))
    except ValueError:
        return jsonify({"error": "Select a month and enter a temperature."}), 400
    if month < 1 or month > 12:
        return jsonify({"error": "Invalid month."}), 400
    baseline = BASELINE[str(month)]
    diff = round(temp - baseline, 2)
    alert = diff >= current_threshold()
    level = "Severe" if diff >= 3 else "High" if diff >= 2 else "Moderate" if alert else "Normal"
    return jsonify({"mode": "month", "country": "Pakistan", "label": MONTH_NAMES[month - 1],
                    "month": MONTH_NAMES[month - 1], "temperature": temp, "baseline": baseline,
                    "difference": diff, "alert": alert, "level": level,
                    "threshold": current_threshold()})

# ---------------- Live tool: data upload and processing ----------------
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "earthscape_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route("/upload")
@login_required
def upload():
    return render_template("upload.html")

@app.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Please choose a CSV file."}), 400
    raw = f.read()
    if len(raw) > 8 * 1024 * 1024:
        return jsonify({"error": "File is too large (maximum 8 MB)."}), 400
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8", "replace"))))
    except Exception:
        return jsonify({"error": "Could not read this CSV file."}), 400
    if not rows:
        return jsonify({"error": "The file has no data rows."}), 400
    cols = rows[0].keys()
    temp_col = next((c for c in cols if "temperature" in c.lower() and "uncertainty" not in c.lower()), None)
    date_col = next((c for c in cols if c.lower() in ("dt", "date", "month", "year")), None)
    country_col = next((c for c in cols if c.lower() == "country"), None)
    if not temp_col or not date_col:
        return jsonify({"error": "The CSV needs a date column (dt) and a temperature column, like the project dataset."}), 400
    missing = sum(1 for r in rows if not r[temp_col])
    countries = sorted({r[country_col] for r in rows if country_col and r[country_col]}) if country_col else []
    token = uuid.uuid4().hex
    with open(os.path.join(UPLOAD_DIR, token + ".json"), "w") as fh:
        json.dump({"rows": rows, "temp_col": temp_col, "date_col": date_col, "country_col": country_col}, fh)
    return jsonify({"token": token, "total_rows": len(rows), "missing_temperatures": missing,
                    "usable_rows": len(rows) - missing, "countries": countries,
                    "columns": list(cols)})

@app.route("/api/upload-series")
@login_required
def api_upload_series():
    token = request.args.get("token", "")
    country = request.args.get("country", "")
    path = os.path.join(UPLOAD_DIR, token + ".json")
    if not os.path.exists(path):
        return jsonify({"error": "Upload session expired. Please upload again."}), 404
    with open(path) as fh:
        saved = json.load(fh)
    rows, tc, dc, cc = saved["rows"], saved["temp_col"], saved["date_col"], saved["country_col"]
    per_year = {}
    for r in rows:
        if cc and country and r.get(cc) != country:
            continue
        try:
            year = int(str(r[dc])[:4])
            val = float(r[tc])
        except (TypeError, ValueError):
            continue
        per_year.setdefault(year, []).append(val)
    series = [[y, round(statistics.mean(v), 2)] for y, v in sorted(per_year.items())]
    return jsonify({"country": country or "All data", "points": series, "years": len(series)})

# ---------------- Live weather (Open-Meteo API, no key needed) ----------------
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog with frost", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "EarthScapeClimateAgency/1.0"})
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.load(r)

@app.route("/weather")
@login_required
def weather_page():
    return render_template("weather.html")

@app.route("/api/weather")
@login_required
def api_weather():
    city = request.args.get("city", "").strip()
    if not city:
        return jsonify({"error": "Please type a city name."}), 400
    try:
        geo = fetch_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&format=json&name="
                         + urllib.parse.quote(city))
        results = geo.get("results") or []
        if not results:
            return jsonify({"error": "City not found. Please check the spelling."}), 404
        place = results[0]
        w = fetch_json("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                       "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,surface_pressure"
                       "&daily=temperature_2m_max,temperature_2m_min&forecast_days=1&timezone=auto"
                       % (place["latitude"], place["longitude"]))
    except Exception:
        return jsonify({"error": "The live weather service did not respond. Please try again in a moment."}), 502
    cur, day = w.get("current", {}), w.get("daily", {})
    code = cur.get("weather_code")
    return jsonify({
        "city": place.get("name"), "country": place.get("country", ""),
        "time": cur.get("time", ""), "timezone": w.get("timezone", ""),
        "temperature": cur.get("temperature_2m"), "feels_like": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"), "wind": cur.get("wind_speed_10m"),
        "pressure": cur.get("surface_pressure"),
        "condition": WEATHER_CODES.get(code, "Unknown"),
        "today_max": (day.get("temperature_2m_max") or [None])[0],
        "today_min": (day.get("temperature_2m_min") or [None])[0],
        "source": "Open-Meteo, a free weather service",
    })

# ---------------- Weather by date and date range (Open-Meteo archive) ----------------
DAILY_VARS = "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,wind_speed_10m_max"

def geocode(city):
    geo = fetch_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&format=json&name="
                     + urllib.parse.quote(city))
    results = geo.get("results") or []
    return results[0] if results else None

def daily_series(place, start, end):
    """Day by day weather for a place between two dates (YYYY-MM-DD strings).
    Past data comes from the Open-Meteo, a free weather service. Very recent days that the
    archive has not filled yet are taken from the forecast API instead."""
    import datetime as dt
    lat, lon = place["latitude"], place["longitude"]
    days = {}

    def absorb(payload):
        d = (payload or {}).get("daily") or {}
        times = d.get("time") or []
        for i, day in enumerate(times):
            row = days.setdefault(day, {})
            for key, field in (("tmax", "temperature_2m_max"), ("tmin", "temperature_2m_min"),
                               ("tmean", "temperature_2m_mean"), ("rain", "precipitation_sum"),
                               ("wind", "wind_speed_10m_max")):
                vals = d.get(field) or []
                if i < len(vals) and vals[i] is not None and row.get(key) is None:
                    row[key] = vals[i]

    archive_error = None
    try:
        absorb(fetch_json("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
                          "&start_date=%s&end_date=%s&daily=%s&timezone=auto"
                          % (lat, lon, start, end, DAILY_VARS)))
    except Exception as e:
        archive_error = e
    today = dt.date.today()
    if dt.date.fromisoformat(end) >= today - dt.timedelta(days=10):
        try:
            absorb(fetch_json("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                              "&start_date=%s&end_date=%s&daily=%s&timezone=auto"
                              % (lat, lon, start, end, DAILY_VARS)))
        except Exception:
            pass
    out = []
    cur = dt.date.fromisoformat(start)
    last = dt.date.fromisoformat(end)
    while cur <= last:
        key = cur.isoformat()
        row = days.get(key) or {}
        if row.get("tmean") is None and row.get("tmax") is not None and row.get("tmin") is not None:
            row["tmean"] = round((row["tmax"] + row["tmin"]) / 2, 2)
        out.append({"date": key, "tmean": row.get("tmean"), "tmax": row.get("tmax"),
                    "tmin": row.get("tmin"), "rain": row.get("rain"), "wind": row.get("wind")})
        cur += dt.timedelta(days=1)
    if archive_error is not None and not any(r["tmean"] is not None for r in out):
        raise archive_error   # say "service busy", not "no data for this date"
    return out

def parse_date(value):
    import datetime as dt
    try:
        return dt.date.fromisoformat(value or "")
    except ValueError:
        return None

@app.route("/api/weather-day")
@login_required
def api_weather_day():
    import datetime as dt
    city = request.args.get("city", "").strip()
    day = parse_date(request.args.get("date", ""))
    if not city:
        return jsonify({"error": "Please type a city name."}), 400
    if day is None:
        return jsonify({"error": "Please select a date."}), 400
    if day > dt.date.today() + dt.timedelta(days=16):
        return jsonify({"error": "That date is too far in the future. Weather data is available up to about 16 days ahead."}), 400
    try:
        place = geocode(city)
        if not place:
            return jsonify({"error": "City not found. Please check the spelling."}), 404
        rows = daily_series(place, day.isoformat(), day.isoformat())
    except Exception:
        return jsonify({"error": "The free weather archive (Open-Meteo) is busy or rate-limited right now. Please try again in a few minutes."}), 502
    row = rows[0] if rows else {}
    if row.get("tmean") is None and row.get("tmax") is None:
        return jsonify({"error": "Data for this date is not available yet. Very recent days can take a few days to appear in the archive."}), 404
    return jsonify({"city": place.get("name"), "country": place.get("country", ""),
                    "date": day.isoformat(), "average_temperature": row.get("tmean"),
                    "max_temperature": row.get("tmax"), "min_temperature": row.get("tmin"),
                    "rainfall_mm": row.get("rain"), "max_wind_kmh": row.get("wind"),
                    "source": "Open-Meteo, a free weather service"})

@app.route("/api/weather-range")
@login_required
def api_weather_range():
    import datetime as dt
    city = request.args.get("city", "").strip()
    start = parse_date(request.args.get("from", ""))
    end = parse_date(request.args.get("to", ""))
    if not city:
        return jsonify({"error": "Please type a city name."}), 400
    if start is None or end is None:
        return jsonify({"error": "Please select both dates."}), 400
    if end < start:
        return jsonify({"error": "The second date must be after the first date."}), 400
    if (end - start).days > 366:
        return jsonify({"error": "Please select a period of one year or less."}), 400
    if end > dt.date.today() + dt.timedelta(days=16):
        return jsonify({"error": "The end date is too far in the future. Weather data is available up to about 16 days ahead."}), 400
    try:
        place = geocode(city)
        if not place:
            return jsonify({"error": "City not found. Please check the spelling."}), 404
        rows = daily_series(place, start.isoformat(), end.isoformat())
    except Exception:
        return jsonify({"error": "The free weather archive (Open-Meteo) is busy or rate-limited right now. Please try again in a few minutes."}), 502
    have = [r for r in rows if r.get("tmean") is not None]
    if not have:
        return jsonify({"error": "No data is available for this period yet."}), 404
    avg = round(sum(r["tmean"] for r in have) / len(have), 2)
    avg_max = round(sum(r["tmax"] for r in have if r["tmax"] is not None) / max(1, sum(1 for r in have if r["tmax"] is not None)), 2)
    avg_min = round(sum(r["tmin"] for r in have if r["tmin"] is not None) / max(1, sum(1 for r in have if r["tmin"] is not None)), 2)
    total_rain = round(sum(r["rain"] for r in rows if r.get("rain") is not None), 1)
    return jsonify({"city": place.get("name"), "country": place.get("country", ""),
                    "from": start.isoformat(), "to": end.isoformat(), "days": len(have),
                    "average_temperature": avg, "average_max": avg_max, "average_min": avg_min,
                    "total_rainfall_mm": total_rain, "daily": rows,
                    "source": "Open-Meteo, a free weather service"})

# ---------------- Weather: 24 hours of a date, and 12 months of a year ----------------
@app.route("/api/weather-hourly")
@login_required
def api_weather_hourly():
    import datetime as dt
    city = request.args.get("city", "").strip()
    day = parse_date(request.args.get("date", ""))
    if not city:
        return jsonify({"error": "Please type a city name."}), 400
    if day is None:
        return jsonify({"error": "Please select a date."}), 400
    if day > dt.date.today() + dt.timedelta(days=16):
        return jsonify({"error": "That date is too far in the future."}), 400
    try:
        place = geocode(city)
        if not place:
            return jsonify({"error": "City not found. Please check the spelling."}), 404
        lat, lon = place["latitude"], place["longitude"]
        hours = {}
        def absorb_h(payload):
            h = (payload or {}).get("hourly") or {}
            times = h.get("time") or []
            for i, tstamp in enumerate(times):
                row = hours.setdefault(tstamp, {})
                for key, field in (("temp", "temperature_2m"), ("humidity", "relative_humidity_2m")):
                    vals = h.get(field) or []
                    if i < len(vals) and vals[i] is not None and row.get(key) is None:
                        row[key] = vals[i]
        dstr = day.isoformat()
        try:
            absorb_h(fetch_json("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
                                "&start_date=%s&end_date=%s&hourly=temperature_2m,relative_humidity_2m&timezone=auto"
                                % (lat, lon, dstr, dstr)))
        except Exception as e:
            if day < dt.date.today() - dt.timedelta(days=10):
                raise e
        if day >= dt.date.today() - dt.timedelta(days=10):
            try:
                absorb_h(fetch_json("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
                                    "&start_date=%s&end_date=%s&hourly=temperature_2m,relative_humidity_2m&timezone=auto"
                                    % (lat, lon, dstr, dstr)))
            except Exception:
                pass
    except Exception:
        return jsonify({"error": "The free weather archive (Open-Meteo) is busy or rate-limited right now. Please try again in a few minutes."}), 502
    rows = [{"time": t, "hour": t[11:16], "temperature": v.get("temp"), "humidity": v.get("humidity")}
            for t, v in sorted(hours.items()) if v.get("temp") is not None]
    if not rows:
        return jsonify({"error": "Hourly data for this date is not available yet."}), 404
    return jsonify({"city": place.get("name"), "country": place.get("country", ""),
                    "date": dstr, "hours": rows, "source": "Open-Meteo, a free weather service"})

@app.route("/api/weather-months")
@login_required
def api_weather_months():
    import datetime as dt
    city = request.args.get("city", "").strip()
    try:
        year = int(request.args.get("year", ""))
    except ValueError:
        return jsonify({"error": "Please enter a year, for example 2024."}), 400
    if year < 1950 or year > dt.date.today().year:
        return jsonify({"error": "Please enter a year between 1950 and %d." % dt.date.today().year}), 400
    try:
        place = geocode(city)
        if not place:
            return jsonify({"error": "City not found. Please check the spelling."}), 404
        rows = daily_series(place, "%d-01-01" % year, "%d-12-31" % year)
    except Exception:
        return jsonify({"error": "The free weather archive (Open-Meteo) is busy or rate-limited right now. Please try again in a few minutes."}), 502
    months = []
    for mth in range(1, 13):
        part = [r for r in rows if int(r["date"][5:7]) == mth and r.get("tmean") is not None]
        if part:
            months.append({"month": MONTH_NAMES[mth - 1], "days": len(part),
                           "average_temperature": round(sum(r["tmean"] for r in part) / len(part), 2),
                           "total_rainfall_mm": round(sum(r["rain"] for r in part if r.get("rain") is not None), 1)})
        else:
            months.append({"month": MONTH_NAMES[mth - 1], "days": 0,
                           "average_temperature": None, "total_rainfall_mm": None})
    if not any(m["days"] for m in months):
        return jsonify({"error": "No data is available for this year yet."}), 404
    return jsonify({"city": place.get("name"), "country": place.get("country", ""),
                    "year": year, "months": months, "source": "Open-Meteo, a free weather service"})

# ---------------- Globe, projections and live data (Open-Meteo, cached) ----------------
LIVE_CITIES = [
    ("Karachi", "Pakistan", 24.86, 67.01), ("Lahore", "Pakistan", 31.55, 74.34), ("Islamabad", "Pakistan", 33.69, 73.06),
    ("Peshawar", "Pakistan", 34.01, 71.58), ("Quetta", "Pakistan", 30.18, 66.99), ("Multan", "Pakistan", 30.2, 71.47),
    ("Jacobabad", "Pakistan", 28.28, 68.44), ("Gilgit", "Pakistan", 35.92, 74.31),
    ("Dubai", "UAE", 25.2, 55.27), ("Riyadh", "Saudi Arabia", 24.71, 46.68), ("Doha", "Qatar", 25.29, 51.53),
    ("New Delhi", "India", 28.61, 77.21), ("Mumbai", "India", 19.08, 72.88), ("Dhaka", "Bangladesh", 23.81, 90.41),
    ("Kabul", "Afghanistan", 34.53, 69.17), ("Tehran", "Iran", 35.69, 51.39), ("Cairo", "Egypt", 30.04, 31.24),
    ("Istanbul", "Turkey", 41.01, 28.98), ("Moscow", "Russia", 55.76, 37.62), ("London", "UK", 51.51, -0.13),
    ("Paris", "France", 48.86, 2.35), ("Berlin", "Germany", 52.52, 13.41), ("Oslo", "Norway", 59.91, 10.75),
    ("Reykjavik", "Iceland", 64.15, -21.94), ("New York", "USA", 40.71, -74.01), ("Los Angeles", "USA", 34.05, -118.24),
    ("Mexico City", "Mexico", 19.43, -99.13), ("Toronto", "Canada", 43.65, -79.38), ("Sao Paulo", "Brazil", -23.55, -46.63),
    ("Buenos Aires", "Argentina", -34.6, -58.38), ("Lima", "Peru", -12.05, -77.04), ("Lagos", "Nigeria", 6.52, 3.38),
    ("Nairobi", "Kenya", -1.29, 36.82), ("Johannesburg", "South Africa", -26.2, 28.05), ("Beijing", "China", 39.9, 116.4),
    ("Shanghai", "China", 31.23, 121.47), ("Tokyo", "Japan", 35.68, 139.69), ("Seoul", "South Korea", 37.57, 126.98),
    ("Bangkok", "Thailand", 13.76, 100.5), ("Singapore", "Singapore", 1.35, 103.82), ("Jakarta", "Indonesia", -6.2, 106.85),
    ("Manila", "Philippines", 14.6, 120.98), ("Sydney", "Australia", -33.87, 151.21), ("Auckland", "New Zealand", -36.85, 174.76),
]

def _latlon():
    try:
        lat = float(request.args.get("lat", "")); lon = float(request.args.get("lon", ""))
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon

def _service_error(e):
    msg = str(e)
    if "limit" in msg.lower() or "429" in msg:
        return jsonify({"error": "The free Open-Meteo service is rate-limiting us for a minute. Please try again shortly."}), 503
    return jsonify({"error": "The climate data service did not respond. Please try again in a moment."}), 502

@app.route("/globe")
@login_required
def globe_page():
    return render_template("globe.html")

@app.route("/projections")
@login_required
def projections_page():
    return render_template("projections.html")

@app.route("/api/place/past")
@login_required
def api_place_past():
    ll = _latlon()
    if not ll:
        return jsonify({"error": "Valid lat and lon are required."}), 400
    try:
        resp = jsonify(climate_lib.past_summary(*ll))
        resp.headers["Cache-Control"] = "private, max-age=43200"
        return resp
    except Exception as e:
        return _service_error(e)

@app.route("/api/place/present")
@login_required
def api_place_present():
    ll = _latlon()
    if not ll:
        return jsonify({"error": "Valid lat and lon are required."}), 400
    try:
        return jsonify(climate_lib.present(*ll))
    except Exception as e:
        return _service_error(e)

@app.route("/api/place/projection")
@login_required
def api_place_projection():
    ll = _latlon()
    if not ll:
        return jsonify({"error": "Valid lat and lon are required."}), 400
    try:
        years = int(request.args.get("years", 10))
    except ValueError:
        years = 10
    try:
        resp = jsonify(climate_lib.projection(ll[0], ll[1], years, with_cmip=False))
        resp.headers["Cache-Control"] = "private, max-age=43200"
        return resp
    except Exception as e:
        return _service_error(e)

NE_TO_BERKELEY = {"Dem. Rep. Congo": "Congo (Democratic Republic Of The)", "Falkland Is.": "Falkland Islands (Islas Malvinas)",
                  "Guinea-Bissau": "Guinea Bissau", "Myanmar": "Burma", "Palestine": "Palestina", "Timor-Leste": "Timor Leste",
                  "S. Sudan": "Sudan", "Somaliland": "Somalia", "N. Cyprus": "Cyprus", "Kosovo": "Serbia", "Antarctica": "Antarctica"}

def berkeley_name(ne_props):
    low = {k.lower(): k for k in YEARLY}
    for cand in (ne_props.get("name", ""), ne_props.get("long", "")):
        if cand.lower() in low:
            return low[cand.lower()]
    return NE_TO_BERKELEY.get(ne_props.get("name"))

_WARMING_MAP = {}

@app.route("/api/warming-map")
@login_required
def api_warming_map():
    """Warming per globe country: the latest ten complete years (Berkeley Earth extended with
    matched ERA5, so 2016-2025 today) minus 1951-1980, plus the trend per decade since 1950."""
    if not _WARMING_MAP:
        for key, props in COUNTRY_GEO.items():
            bname = berkeley_name(props)
            pts = full_series(bname or "")
            if not pts:
                continue
            end = pts[-1][0]
            b = [t for y, t in pts if 1951 <= y <= 1980]
            last = [t for y, t in pts if y > end - 10]
            if len(b) >= 20 and len(last) >= 5:
                fit = climate_lib.ols([y for y, _ in pts if y >= 1950], [t for y, t in pts if y >= 1950])
                _WARMING_MAP[props["name"]] = {"warming": round(statistics.mean(last) - statistics.mean(b), 2),
                                               "period": "%d-%d" % (end - 9, end),
                                               "per_decade": round(fit["b"] * 10, 3) if fit else None,
                                               "dataset_name": bname, "mean": round(statistics.mean(t for _, t in pts if _ >= 1950), 2)}
    return jsonify(_WARMING_MAP)

_GLOBE_CACHE = {}

def _cached_value(key, ttl, fn):
    hit = _GLOBE_CACHE.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        val = fn()
        _GLOBE_CACHE[key] = (time.time(), val)
        return val
    except Exception:
        if hit:
            return hit[1]
        raise

@app.route("/api/globe/events")
@login_required
def api_globe_events():
    """Active tropical storms and erupting volcanoes from NASA EONET (no key needed)."""
    def get():
        out = []
        for cat, kind in (("severeStorms", "storm"), ("volcanoes", "volcano")):
            d = climate_lib.cached_json("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=20&category=" + cat, 3600, timeout=15)
            for e in d.get("events", []):
                geo = [g for g in e.get("geometry", []) if g.get("type") == "Point"]
                if not geo:
                    continue
                g = geo[-1]
                out.append({"kind": kind, "title": e.get("title"), "date": g.get("date"),
                            "lon": g["coordinates"][0], "lat": g["coordinates"][1],
                            "wind": g.get("magnitudeValue"), "unit": g.get("magnitudeUnit"),
                            "track": [[p["coordinates"][1], p["coordinates"][0]] for p in geo[-12:]] if kind == "storm" else []})
        return {"events": out, "source": "NASA EONET", "fetched": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    try:
        return jsonify(_cached_value("events", 3600, get))
    except Exception as e:
        return _service_error(e)

GIBS_WMS = ("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1"
            "&STYLES=&SRS=EPSG:4326&BBOX=-180,-90,180,90&WIDTH=2048&HEIGHT=1024&TRANSPARENT=TRUE")
GIBS_LAYERS = {  # name -> (NASA layer, format, days back for TIME or None for NASA's latest)
    "rain": ("IMERG_Precipitation_Rate", "image/png", None),
    "clouds": ("MODIS_Terra_CorrectedReflectance_TrueColor", "image/jpeg", 1),
    "fires": ("VIIRS_NOAA20_Thermal_Anomalies_375m_All", "image/png", 1),
}

@app.route("/api/globe/layer/<name>")
@login_required
def api_globe_layer(name):
    """A whole-world NASA GIBS image for one weather layer, fetched server-side (so the browser
    never hits cross-origin limits) and cached for three hours."""
    if name not in GIBS_LAYERS:
        return jsonify({"error": "unknown layer"}), 404
    layer, fmt, back = GIBS_LAYERS[name]
    day = time.strftime("%Y-%m-%d", time.gmtime(time.time() - back * 86400)) if back else None
    url = (GIBS_WMS.replace("WIDTH=2048&HEIGHT=1024", "WIDTH=4096&HEIGHT=2048") if name == "fires" else GIBS_WMS) + "&LAYERS=" + layer + "&FORMAT=" + fmt + ("&TIME=" + day if day else "")
    def get():
        req = urllib.request.Request(url, headers={"User-Agent": "EarthScapeClimateAgency/2.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            if not r.headers.get("Content-Type", "").startswith("image"):
                raise ValueError("NASA GIBS returned no image")
        return body
    try:
        body = _cached_value("layer:" + name + ":" + str(day), 3 * 3600, get)
    except Exception:
        return jsonify({"error": "NASA's imagery service did not respond. Try again shortly."}), 502
    from flask import Response
    resp = Response(body, mimetype=fmt)
    resp.headers["Cache-Control"] = "private, max-age=10800"
    resp.headers["X-Layer-Date"] = day or "latest"
    return resp

@app.route("/api/globe/wind")
@login_required
def api_globe_wind():
    """Wind right now on a 15 degree grid (Open-Meteo, one batched request, cached an hour)."""
    def get():
        lats, lons = [], []
        for la in range(-60, 76, 15):
            for lo in range(-180, 180, 15):
                lats.append(la); lons.append(lo)
        url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
               "&current=wind_speed_10m,wind_direction_10m&wind_speed_unit=kmh") % (
               ",".join(map(str, lats)), ",".join(map(str, lons)))
        d = climate_lib.cached_json(url, 3600, timeout=25)
        pts = []
        for la, lo, r in zip(lats, lons, d if isinstance(d, list) else [d]):
            c = r.get("current", {})
            if c.get("wind_speed_10m") is not None:
                pts.append([la, lo, c["wind_speed_10m"], c["wind_direction_10m"]])
        return {"step": 15, "points": pts, "time": (d[0] if isinstance(d, list) else d).get("current", {}).get("time"),
                "source": "Open-Meteo (ECMWF/GFS blend)"}
    try:
        return jsonify(_cached_value("wind", 3600, get))
    except Exception as e:
        return _service_error(e)

@app.route("/api/place/cmip6")
@login_required
def api_place_cmip6():
    ll = _latlon()
    if not ll:
        return jsonify({"error": "Valid lat and lon are required."}), 400
    try:
        resp = jsonify(climate_lib.cmip6_for(ll[0], ll[1], int(request.args.get("years", 10) or 10)))
        resp.headers["Cache-Control"] = "private, max-age=604800"   # model output to 2050 does not change
        return resp
    except Exception as e:
        resp, code = _service_error(e)
        resp.headers["Retry-After"] = "60"
        return resp, code

@app.route("/api/geocode")
@login_required
def api_geocode():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Type a place."}), 400
    try:
        p = climate_lib.geocode(q)
    except Exception as e:
        return _service_error(e)
    if not p:
        return jsonify({"error": "Place not found."}), 404
    return jsonify({"name": p.get("name"), "country": p.get("country", ""), "lat": p["latitude"], "lon": p["longitude"]})

@app.route("/api/live-cities")
@login_required
def api_live_cities():
    try:
        rows = climate_lib.live_cities(LIVE_CITIES)
    except Exception as e:
        return _service_error(e)
    have = [r for r in rows if r["temp"] is not None]
    return jsonify({"cities": rows, "updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                    "hottest": max(have, key=lambda r: r["temp"]) if have else None,
                    "coldest": min(have, key=lambda r: r["temp"]) if have else None,
                    "windiest": max(have, key=lambda r: r["wind"] or 0) if have else None,
                    "reporting": len(have), "total": len(rows)})

@app.route("/api/alerts/live")
@login_required
def api_alerts_live():
    try:
        data = live_alerts.get()
    except Exception as e:
        return _service_error(e)
    th, src = threshold_info()
    out = {"summary": live_alerts.summarize(data, th), "places": data["places"], "last_month": data["last_month"],
           "built": data["built"], "normal": data["normal"], "source": data["source"], "fallback": data.get("fallback", False),
           "threshold": th, "threshold_source": src}
    resp = jsonify(out)
    resp.headers["Cache-Control"] = "private, max-age=600"
    return resp

@app.route("/api/alerts/summary")
@login_required
def api_alerts_summary():
    th = current_threshold()
    try:
        s = live_alerts.summarize(live_alerts.get(), th)
        return jsonify({"badge": s["badge"], "recent": len(s["recent"]), "upcoming": len(s["upcoming"]),
                        "threshold": th, "window": s["window"], "historical": len(historical_alerts(th))})
    except Exception:
        return jsonify({"badge": None, "threshold": th, "historical": len(historical_alerts(th))})

@app.route("/api/public/pulse")
def api_public_pulse():
    """Tiny public endpoint for the sign-in page: Karachi right now."""
    try:
        p = climate_lib.present(24.86, 67.01)
        return jsonify({"city": "Karachi", "temp": p["current"]["temp"], "sky": p["current"]["sky"]})
    except Exception:
        return jsonify({"city": "Karachi", "temp": None})

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    body = request.get_json(silent=True) or {}
    q = str(body.get("message", "")).strip()
    if not q:
        return jsonify({"error": "Ask me something about the climate."}), 400
    try:
        ANALYST.threshold = current_threshold()
        ANALYST.historical = historical_alerts(ANALYST.threshold)
        live = live_alerts.cached()
        ANALYST.live = live_alerts.summarize(live, ANALYST.threshold) if live else None
        out = ANALYST.answer(q[:1500], body.get("history") or [], body.get("context") or {})
    except Exception:
        out = {"reply": "I hit a snag pulling the data for that one. Try asking about a specific country or city, for example \"How has Karachi warmed since 1980?\"",
               "chart": None, "provider": "Built-in analyst"}
    return jsonify(out)

# ---------------- Feedback and support ----------------
FEEDBACK_FILE = os.path.join(BASE, "data", "feedback.json")

def read_feedback():
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE) as f:
            return json.load(f)
    return []

@app.route("/feedback", methods=["GET", "POST"])
@login_required
def feedback():
    if request.method == "POST":
        entry = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "type": request.form.get("type", "Feedback"),
            "message": request.form.get("message", "").strip(),
            "by": session.get("user"),
        }
        if not entry["name"] or not entry["message"]:
            flash("Please enter your name and a message before submitting.", "error")
            return redirect(url_for("feedback"))
        items = read_feedback()
        items.append(entry)
        try:
            with open(FEEDBACK_FILE, "w") as f:
                json.dump(items, f, indent=2)
        except OSError:
            pass  # read-only hosting (serverless): submission still accepted
        flash("Thank you. Your message has been submitted to the support team.")
        return redirect(url_for("feedback"))
    return render_template("feedback.html")

# ---------------- Help and user guide ----------------
@app.route("/help")
@login_required
def help_page():
    return render_template("help.html", threshold=current_threshold())

# ---------------- Admin ----------------
@app.route("/admin")
@login_required
@admin_required
def admin():
    users = [{"username": u, "role": d["role"], "name": d["name"],
              "email": d.get("email", "")} for u, d in USERS.items()]
    errs = [(a - p) ** 2 for _, a, p in MODEL["test_years"]]
    stats = {
        "total_records": "10,064,718",
        "cleaned_rows": "544,811",
        "countries": len(YEARLY),
        "months_checked": len(MONTHS_CHECKED),
        "model_rmse": round((sum(errs) / len(errs)) ** 0.5, 2),
        "feedback_count": len(read_feedback()),
    }
    return render_template("admin.html", users=users, feedback=read_feedback(),
                           threshold=current_threshold(), stats=stats, months=MONTHS_CHECKED,
                           recovery=[{"username": u,
                                      "minutes_left": max(0, int((r["expires"] - time.time()) // 60))}
                                     for u, r in RECOVERY_REQUESTS.items()
                                     if r["expires"] > time.time()])

@app.route("/admin/reset-password", methods=["POST"])
@login_required
@admin_required
def admin_reset_password():
    u = request.form.get("username", "").strip()
    new_pw = request.form.get("new_password", "")
    if u not in USERS:
        flash("Unknown username.", "error")
        return redirect(url_for("admin"))
    if len(new_pw) < 6:
        flash("The new password must be at least 6 characters long.", "error")
        return redirect(url_for("admin"))
    USERS[u]["password"] = generate_password_hash(new_pw)
    save_user_password(u)
    RECOVERY_REQUESTS.pop(u, None)
    flash("Password for %s has been reset. They can sign in with the new password now." % u)
    return redirect(url_for("admin"))

@app.route("/admin/threshold", methods=["POST"])
@login_required
@admin_required
def set_threshold():
    try:
        val = float(request.form.get("threshold", ""))
    except ValueError:
        flash("Enter a valid threshold value.", "error")
        return redirect(url_for("admin"))
    if val < 0.5 or val > 5.0:
        flash("Threshold must be between 0.5 and 5.0 C.", "error")
        return redirect(url_for("admin"))
    _threshold_global[0] = val
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"threshold": val}, f)
    except OSError:
        pass  # read-only hosting (Vercel): the signed cookie below keeps it
    flash("Alert threshold updated to %g C. Alerts, the badge and the dashboard now use it." % val)
    resp = redirect(url_for("admin"))
    resp.set_cookie(THRESHOLD_COOKIE, _threshold_signer().dumps(val), max_age=365 * 86400,
                    httponly=True, samesite="Lax", secure=request.is_secure)
    return resp

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=("PORT" not in os.environ))
