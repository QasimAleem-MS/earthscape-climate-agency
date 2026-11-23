# ============================================================
# EarthScape AI Climate Analyst
# Grounds every answer in the app's own data (Berkeley Earth yearly records,
# the Pakistan model, anomaly alerts, CO2 correlation) and in live Open-Meteo
# data for the place being asked about. Uses an LLM when GROQ_API_KEY or
# GEMINI_API_KEY is set; otherwise a rule-based analyst answers from the same
# facts so the demo never breaks.
# ============================================================
import json
import os
import re
import urllib.request

import climate_lib as cl

ALIASES = {
    "usa": "United States", "us": "United States", "america": "United States", "united states of america": "United States",
    "uk": "United Kingdom", "britain": "United Kingdom", "england": "United Kingdom", "uae": "United Arab Emirates",
    "ksa": "Saudi Arabia", "russia": "Russia", "korea": "South Korea", "drc": "Congo (Democratic Republic Of The)",
}
CITY_HINTS = {
    "karachi": ("Karachi", "Pakistan", 24.86, 67.01), "lahore": ("Lahore", "Pakistan", 31.55, 74.34),
    "islamabad": ("Islamabad", "Pakistan", 33.69, 73.06), "peshawar": ("Peshawar", "Pakistan", 34.01, 71.58),
    "quetta": ("Quetta", "Pakistan", 30.18, 66.99), "multan": ("Multan", "Pakistan", 30.2, 71.47),
    "faisalabad": ("Faisalabad", "Pakistan", 31.42, 73.08), "jacobabad": ("Jacobabad", "Pakistan", 28.28, 68.44),
    "dubai": ("Dubai", "United Arab Emirates", 25.2, 55.27), "london": ("London", "United Kingdom", 51.51, -0.13),
    "new york": ("New York", "United States", 40.71, -74.01), "delhi": ("New Delhi", "India", 28.61, 77.21),
    "tokyo": ("Tokyo", "Japan", 35.68, 139.69), "paris": ("Paris", "France", 48.86, 2.35),
    "riyadh": ("Riyadh", "Saudi Arabia", 24.71, 46.68), "doha": ("Doha", "Qatar", 25.29, 51.53),
    "berlin": ("Berlin", "Germany", 52.52, 13.41), "beijing": ("Beijing", "China", 39.9, 116.4),
    "sydney": ("Sydney", "Australia", -33.87, 151.21), "cairo": ("Cairo", "Egypt", 30.04, 31.24),
    "toronto": ("Toronto", "Canada", 43.65, -79.38), "moscow": ("Moscow", "Russia", 55.76, 37.62),
    "istanbul": ("Istanbul", "Turkey", 41.01, 28.98), "kabul": ("Kabul", "Afghanistan", 34.53, 69.17),
    "tehran": ("Tehran", "Iran", 35.69, 51.39), "dhaka": ("Dhaka", "Bangladesh", 23.81, 90.41),
    "mumbai": ("Mumbai", "India", 19.08, 72.88), "jakarta": ("Jakarta", "Indonesia", -6.2, 106.85),
    "lagos": ("Lagos", "Nigeria", 6.52, 3.38), "nairobi": ("Nairobi", "Kenya", -1.29, 36.82),
}

SYSTEM_PROMPT = """You are "Aria", the senior climate analyst of the EarthScape Climate Agency (an Aptech Big Data eProject).
Speak like a warm, sharp human analyst briefing a colleague: conversational, confident, plain English, no jargon without a quick explanation.
Rules:
- Ground every number in the DATA CONTEXT you are given. Quote the figures with units (C, mm, C per decade) and say where they come from (Berkeley Earth project data, ERA5 via Open-Meteo, Open-Meteo forecast, our projection model, CMIP6 models).
- Never invent numbers. If the context does not hold the answer, say what you do have and what the user can open in the app (Globe, Projections, Data Explorer, Alerts).
- Be honest about uncertainty: daily weather cannot be predicted years ahead; our 2 to 10 year outlook is a climate projection of monthly and yearly means with ranges.
- Keep answers short: 2 to 5 sentences, or a few tight bullet points for comparisons. One friendly line at most, no filler.
- The app can draw a small chart under your answer; if CHART is listed in the context, you may refer to it ("see the chart below")."""


def _fmt(v, unit="C", d=2):
    return "n/a" if v is None else ("%+.*f %s" % (d, v, unit) if unit.startswith("C/") or unit == "dC" else "%.*f %s" % (d, v, unit))


class Analyst:
    def __init__(self, yearly, model, alerts, co2, recent, countries_geo):
        self.yearly = yearly
        self.model = model
        self.alerts = alerts
        self.co2 = co2
        self.recent = recent
        self.geo = countries_geo  # name(lower) -> dict(name, place, lat, lon)
        self.names = sorted(yearly.keys(), key=len, reverse=True)

    # ---------- understanding the question ----------
    def find_place(self, text, ctx):
        t = " " + re.sub(r"[^a-z0-9 ]", " ", text.lower()) + " "
        for k, v in CITY_HINTS.items():
            if " %s " % k in t:
                return {"name": v[0], "country": v[1], "lat": v[2], "lon": v[3], "kind": "city"}
        for k, v in ALIASES.items():
            if " %s " % k in t:
                return self._country(v)
        for n in self.names:
            if " %s " % n.lower() in t:
                return self._country(n)
        for k, g in self.geo.items():
            if len(k) > 3 and " %s " % k in t:
                return self._country(g["name"])
        if ctx and ctx.get("lat") is not None and ctx.get("lon") is not None:
            return {"name": ctx.get("place") or ctx.get("country"), "country": ctx.get("country"),
                    "lat": float(ctx["lat"]), "lon": float(ctx["lon"]), "kind": "context"}
        return None

    def _country(self, name):
        g = self.geo.get(name.lower())
        if not g:
            for k, v in self.geo.items():
                if name.lower() in (v.get("long", "").lower(), k):
                    g = v
                    break
        place = {"name": name, "country": name, "kind": "country"}
        if g:
            place.update({"lat": g["lat"], "lon": g["lon"], "capital": g["place"]})
        return place

    @staticmethod
    def intent(text):
        t = text.lower()
        return {
            "future": bool(re.search(r"futur|predict|project|forecast for 20|20[3-9]\d|next (few|\d+|ten|five) years|will .* (be|get)|outlook|2030|2035", t)),
            "now": bool(re.search(r"now|today|current|right now|this week|tomorrow|forecast|weather", t)),
            "rain": bool(re.search(r"rain|precip|monsoon|wet|dry|drought|flood", t)),
            "trend": bool(re.search(r"trend|warm|hotter|heat|history|histor|since|over time|change|getting", t)),
            "compare": bool(re.search(r"compar|vs|versus|than", t)),
            "alerts": bool(re.search(r"alert|anomal|extreme|hottest|record", t)),
            "co2": "co2" in t or "carbon" in t,
            "model": bool(re.search(r"model|accura|rmse|error|backtest|how .* work", t)),
        }

    # ---------- building the data context ----------
    def gather(self, question, ctx):
        place = self.find_place(question, ctx)
        it = self.intent(question)
        years = [int(y) for y in re.findall(r"\b(1[89]\d\d|20\d\d)\b", question)]
        facts = {"project": self.project_facts()}
        chart = None
        if place:
            facts["place"] = {"name": place.get("name"), "country": place.get("country"),
                              "capital_or_point": place.get("capital"), "lat": place.get("lat"), "lon": place.get("lon")}
            cname = place.get("country")
            if cname in self.yearly:
                facts["berkeley_earth_yearly"] = self.country_facts(cname, years)
            if place.get("lat") is not None:
                try:
                    pres = cl.present(place["lat"], place["lon"])
                    facts["now"] = {"temp_C": pres["current"]["temp"], "feels_C": pres["current"]["feels"],
                                    "sky": pres["current"]["sky"], "humidity_pct": pres["current"]["humidity"],
                                    "wind_kmh": pres["current"]["wind"], "local_time": pres["current"]["time"],
                                    "next_7_days": [{"date": d["date"], "max": d["tmax"], "min": d["tmin"], "rain_mm": d["rain"], "sky": d["sky"]}
                                                    for d in pres["days"][:7]]}
                    if it["now"] and not it["future"] and not it["trend"]:
                        chart = {"type": "bar-range", "title": "Next 7 days - %s" % place["name"],
                                 "labels": [d["date"][5:] for d in pres["days"][:7]],
                                 "series": [{"label": "Max C", "data": [d["tmax"] for d in pres["days"][:7]]},
                                            {"label": "Min C", "data": [d["tmin"] for d in pres["days"][:7]]}]}
                except Exception:
                    facts["now"] = "live weather unavailable right now"
                if it["trend"] or it["rain"] or it["alerts"] or it["future"] or years or not it["now"]:
                    try:
                        past = cl.past_summary(place["lat"], place["lon"])
                        pf = {"era5_range": past["range"], "trend_C_per_decade_since_1980": past["trend_per_decade"], "source": past["source"],
                              "warming_last10y_vs_baseline_C": past["warming_vs_base"], "baseline_years": past["base_label"],
                              "extremes": past["extremes"],
                              "normal_monthly_temp_1991_2020": dict(zip(cl.MONTHS, past["climatology"]["t"])),
                              "normal_monthly_rain_mm_1991_2020": dict(zip(cl.MONTHS, past["climatology"]["p"])),
                              "annual_mean_temp_last_12_years": past["annual_t"][-12:],
                              "annual_rain_mm_last_12_years": past["annual_p"][-12:]}
                        if years:
                            pf["requested_years"] = {str(y): {"temp": dict(past["annual_t"]).get(y), "rain": dict(past["annual_p"]).get(y)} for y in years}
                        facts["era5_history"] = pf
                        if chart is None and it["rain"]:
                            chart = {"type": "bar", "title": "Normal monthly rain (1991-2020) - %s" % place["name"],
                                     "labels": cl.MONTHS, "series": [{"label": "Rain mm", "data": past["climatology"]["p"]}]}
                        elif chart is None and not it["future"]:
                            a = past["annual_t"]
                            if years and len(years) >= 2:
                                a = [p for p in a if min(years) <= p[0] <= max(years)] or a
                            chart = {"type": "line", "title": "Yearly mean temperature - %s" % place["name"],
                                     "labels": [p[0] for p in a], "series": [{"label": "C", "data": [p[1] for p in a]}]}
                    except Exception:
                        facts["era5_history"] = "history service busy"
                if it["future"]:
                    try:
                        pr = cl.projection(place["lat"], place["lon"], 10, with_cmip=True)
                        facts["projection"] = {"method": pr["method"], "trend_C_per_decade": pr["model"]["trend_per_decade"],
                                               "annual_projection": [{"year": a["year"], "mean": a["t"], "range80": [a["lo80"], a["hi80"]], "rain_mm": a["p"]} for a in pr["annual"]],
                                               "backtest_2016_on": pr["backtest"]["metrics"],
                                               "cmip6_ensemble": [e for e in pr["cmip6"].get("ensemble", []) if e["year"] >= pr["annual"][0]["year"]][:10]}
                        chart = {"type": "line", "title": "Projected yearly mean - %s" % place["name"],
                                 "labels": [p[0] for p in pr["history_annual_t"][-15:]] + [a["year"] for a in pr["annual"]],
                                 "series": [{"label": "Observed C", "data": [p[1] for p in pr["history_annual_t"][-15:]] + [None] * len(pr["annual"])},
                                            {"label": "Projected C", "data": [None] * (len(pr["history_annual_t"][-15:]) - 1) + [pr["history_annual_t"][-1][1]] + [a["t"] for a in pr["annual"]], "dash": True}]}
                    except Exception:
                        facts["projection"] = "projection service busy"
        elif it["co2"]:
            chart = {"type": "line", "title": "CO2 (ppm) vs world land temperature",
                     "labels": [r[0] for r in self.co2], "series": [{"label": "CO2 ppm", "data": [r[1] for r in self.co2]}]}
        elif it["alerts"] or True:
            if chart is None and (it["alerts"] or it["trend"]):
                rp = self.recent["pakistan_yearly"]
                chart = {"type": "bar", "title": "Pakistan yearly mean temperature (ERA5)",
                         "labels": list(rp.keys()), "series": [{"label": "C", "data": list(rp.values())}]}
        if chart:
            facts["CHART"] = chart["title"]
        return place, it, facts, chart

    def project_facts(self):
        th = getattr(self, "threshold", 1.5)
        hist = getattr(self, "historical", None)
        if hist is None:
            hist = [r for r in self.alerts if r[3] >= th]
        top = max(hist, key=lambda r: r[3]) if hist else None
        live = getattr(self, "live", None)
        facts = {
            "dataset": "Berkeley Earth Surface Temperature: 10,064,718 records, 544,811 after cleaning, %d countries; Berkeley yearly data to 2012, extended to 2025 and 2026-so-far with Copernicus ERA5" % len(self.yearly),
            "pakistan_model": "Model 2 linear regression trained 1950-2000, test RMSE 0.52 C on 2001-2013; forecasts %s" % self.model["forecasts"],
            "pakistan_alerts": "%d months 2001-2013 were >= %s C (the current alert threshold) above their 1951-1980 normal; biggest %s at +%s C" % (len(hist), th, top[0][:7] if top else "-", top[3] if top else "-"),
            "co2_correlation": "CO2 vs world land temperature 1959-2025: r = 0.9655",
            "pakistan_recent_era5": self.recent["pakistan_yearly"],
        }
        if live:
            facts["live_alerts"] = {"threshold_C": th, "count": live["badge"], "window": live["window"],
                                    "recent_count": len(live["recent"]), "upcoming_count": len(live["upcoming"]),
                                    "recent_months": live["recent"][:8], "upcoming_spells": live["upcoming"][:6],
                                    "normal": "1991-2020, 6 major Pakistani cities and their average"}
        return facts

    def country_facts(self, name, years):
        fn = getattr(self, "series_fn", None)
        pts = [p for p in (fn(name) if fn else self.yearly.get(name, [])) if p[0] >= 1900]
        if not pts:
            return None
        base = [t for y, t in pts if 1951 <= y <= 1980]
        b = sum(base) / len(base) if base else None
        last = pts[-1][0]
        fit = cl.ols([p[0] for p in pts if p[0] >= 1950], [p[1] for p in pts if p[0] >= 1950])
        hot = max(pts, key=lambda p: p[1])
        dec = [t for y, t in pts if y > last - 10]
        out = {"records": "%d to %d, Berkeley Earth + ERA5" % (pts[0][0], last),
               "normal_1951_1980": cl.rnd(b),
               "last_decade": "%d-%d" % (last - 9, last), "last_decade_mean": cl.rnd(sum(dec) / len(dec)),
               "warming_last_decade_vs_1951_1980_C": cl.rnd(sum(dec) / len(dec) - b) if b is not None else None,
               "trend_C_per_decade_from_1950": cl.rnd(fit["b"] * 10, 3) if fit else None,
               "warmest_year": hot, "latest_year": pts[-1]}
        ytd = getattr(self, "ytd_fn", None)
        try:
            y = ytd(name) if ytd else None
            if y:
                out["current_year_so_far"] = y
        except Exception:
            pass
        if years:
            d = dict(pts)
            out["requested_years"] = {str(y): d.get(y) for y in years}
        return out

    # ---------- answering ----------
    def answer(self, question, history, ctx):
        place, it, facts, chart = self.gather(question, ctx or {})
        provider = None
        reply = None
        try:
            if os.environ.get("GROQ_API_KEY"):
                reply = self.call_groq(question, history, facts)
                provider = "Groq " + os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
            elif os.environ.get("GEMINI_API_KEY"):
                reply = self.call_gemini(question, history, facts)
                provider = "Gemini " + os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        except Exception:
            reply = None
        if not reply:
            reply = self.rule_based(question, place, it, facts)
            provider = "Built-in analyst (no LLM key set)" if not (os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")) else "Built-in analyst (LLM unavailable)"
        return {"reply": reply, "chart": chart, "provider": provider,
                "place": place.get("name") if place else None}

    def _messages(self, question, history, facts):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT + "\n\nDATA CONTEXT (JSON):\n" + json.dumps(facts, default=str)[:14000]}]
        for h in (history or [])[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                msgs.append({"role": h["role"], "content": str(h["content"])[:1500]})
        msgs.append({"role": "user", "content": question[:1500]})
        return msgs

    def call_groq(self, question, history, facts):
        body = json.dumps({"model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                           "messages": self._messages(question, history, facts), "temperature": 0.4, "max_tokens": 600}).encode()
        req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "EarthScape/2.0",
                                              "Authorization": "Bearer " + os.environ["GROQ_API_KEY"]})
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()

    def call_gemini(self, question, history, facts):
        msgs = self._messages(question, history, facts)
        contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in msgs[1:]]
        body = json.dumps({"systemInstruction": {"parts": [{"text": msgs[0]["content"]}]}, "contents": contents,
                           "generationConfig": {"temperature": 0.4, "maxOutputTokens": 600}}).encode()
        model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
                                     data=body, method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()

    def rule_based(self, q, place, it, f):
        """A careful offline analyst: picks the facts that match the question."""
        lines = []
        name = place.get("name") if place else None
        if not place:
            p = f["project"]
            if it["co2"]:
                return ("CO2 and heat move together very closely in our data: from 1959 to 2025 the correlation between CO2 in the air and world land temperature is r = 0.9655 "
                        "(1.0 would be a perfect match). The chart below shows CO2 climbing every single year.")
            if it["model"]:
                return ("Our Pakistan trend model (Model 2) is a linear regression trained on 1950 to 2000 and tested on 2001 to 2013, with a test error (RMSE) of 0.52 C. "
                        "For any country on the Globe, the Projections page fits a newer model on ERA5 monthly data since 1980 and backtests it: it trains to 2015 and predicts 2016 onward so you can see the real error.")
            if it["alerts"]:
                la = p.get("live_alerts")
                live_txt = ""
                if la:
                    live_txt = (" Live right now: %d alerts at +%s C (%d city-months in the last 12 months and %d places with forecast heat alerts in the next 16 days, versus the 1991-2020 normal)."
                                % (la["count"], la["threshold_C"], la["recent_count"], la["upcoming_count"]))
                return ("Historical: %s.%s An alert means a month (or forecast day) is at least the threshold hotter than normal for that month in that place. Open the Alerts page for the full list." % (p["pakistan_alerts"], live_txt))
            rp = p["pakistan_recent_era5"]
            return ("Happy to dig in. Pakistan is our focus country: ERA5 puts 2025 at %.2f C, among its hottest years, and the long-run Berkeley Earth model points to about %s C by 2050. "
                    "Ask me about any country or city, for example \"How has Karachi warmed since 1980?\", \"Will Germany be hotter by 2035?\" or \"What's the weather in Dubai this week?\"" %
                    (rp.get("2025", 0), self.model["forecasts"].get("2050")))
        now = f.get("now") if isinstance(f.get("now"), dict) else None
        hist = f.get("era5_history") if isinstance(f.get("era5_history"), dict) else None
        proj = f.get("projection") if isinstance(f.get("projection"), dict) else None
        be = f.get("berkeley_earth_yearly")
        if it["future"] and proj:
            a = proj["annual_projection"]
            last = a[-1]; first = a[0]
            bt = proj["backtest_2016_on"]
            cm = proj.get("cmip6_ensemble") or []
            cm_last = next((c for c in cm if c["year"] == last["year"]), cm[-1] if cm else None)
            lines.append("For %s, our projection puts the yearly mean at about %.1f C in %d, rising to %.1f C by %d (80%% range %.1f to %.1f C). That's a warming trend of %+.2f C per decade."
                         % (name, first["mean"], first["year"], last["mean"], last["year"], last["range80"][0], last["range80"][1], proj["trend_C_per_decade"]))
            if cm_last:
                lines.append("The CMIP6 climate models land at %.1f C for %d, so the two methods %s." % (cm_last["t"], cm_last["year"], "agree closely" if abs(cm_last["t"] - last["mean"]) < 0.5 else "differ by %.1f C" % abs(cm_last["t"] - last["mean"])))
            lines.append("When we trained only to 2015 and predicted 2016 onward, monthly error was %.2f C (MAE). This is a climate outlook for averages, not day-by-day weather." % bt["mae"])
            return " ".join(lines)
        if it["now"] and now and not it["trend"]:
            d = now["next_7_days"]
            hot = max(d, key=lambda x: x["max"] if x["max"] is not None else -99)
            wet = sum(x["rain_mm"] or 0 for x in d)
            lines.append("Right now in %s it's %.1f C (feels like %.1f C), %s, humidity %s%% and wind %s km/h." % (name, now["temp_C"], now["feels_C"], now["sky"].lower(), now["humidity_pct"], now["wind_kmh"]))
            lines.append("Over the next 7 days the warmest day is %s at %.1f C, and about %.1f mm of rain is expected in total." % (hot["date"], hot["max"], wet))
            return " ".join(lines)
        if it["rain"] and hist:
            norm = hist["normal_monthly_rain_mm_1991_2020"]
            wettest_m = max(norm, key=lambda k: norm[k] or 0)
            ann = hist["annual_rain_mm_last_12_years"]
            lines.append("%s gets most of its rain in %s (about %.0f mm in a normal month, 1991-2020)." % (name, wettest_m, norm[wettest_m] or 0))
            if ann:
                lines.append("Last full year (%d) brought %.0f mm; the wettest year since %s was %s with %s mm." % (ann[-1][0], ann[-1][1], hist["era5_range"][0][:4], hist["extremes"]["wettest_year"][0], hist["extremes"]["wettest_year"][1]))
            return " ".join(lines) + " The chart shows the normal rain for every month."
        if hist:
            ex = hist["extremes"]
            tr = hist["trend_C_per_decade_since_1980"] or 0
            wb = hist["warming_last10y_vs_baseline_C"] or 0
            lines.append("%s's trend since 1980 is %+.2f C per decade, and the last ten years ran %.2f C %s than its %s average (source: %s)."
                         % (name, tr, abs(wb), "warmer" if wb >= 0 else "cooler", hist["baseline_years"], hist.get("source", "ERA5")))
            lines.append("The hottest year on record there was %s at %.2f C, and the hottest month was %s (%.1f C)." % (ex["hottest_year"][0], ex["hottest_year"][1], ex["hottest_month"][0], ex["hottest_month"][1]))
            if hist.get("requested_years"):
                ry = ", ".join("%s: %s C" % (y, v["temp"]) for y, v in hist["requested_years"].items() if v["temp"] is not None)
                if ry:
                    lines.append("Yearly means you asked about: %s." % ry)
        if be:
            lines.append("In our project data (%s) its trend from 1950 is %+.3f C per decade, and %s averaged %+.2f C against its 1951-1980 normal." % (be["records"], be["trend_C_per_decade_from_1950"] or 0, be["last_decade"], be["warming_last_decade_vs_1951_1980_C"] or 0))
        if now:
            lines.append("Right now it's %.1f C and %s." % (now["temp_C"], now["sky"].lower()))
        return " ".join(lines) or ("I found %s but the data services are busy right now. Try again in a moment, or open it on the Globe." % name)
