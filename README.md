# EarthScape Climate Agency - Developer Documentation

eProject: Big Data - EarthScape Climate Agency (Aptech ADSE, Term 6)
Submitted by: Taha Kazmi (student1514118), Centre ACE-PK-KARACHI-2-NORTH NAZIMABAD

## What the system does
A Flask web application that stores, explores and analyses climate data, with a
Pakistan focus: login with roles (Administrator, Analyst), a dashboard of charts,
a data explorer for 242 countries, machine learning results (trend prediction,
anomaly detection, correlation analysis), an alerts page driven by a
configurable threshold, live tools (prediction, anomaly checker, CSV upload),
feedback and support, and a help/FAQ guide.

### New in the UI revamp (v2)
- **Orbital glass design system** (`static/es/theme.css`): animated parallax
  starfield, a slowly rotating 3D Earth with an orbiting satellite (three.js via
  globe.gl), glassmorphism cards, reveal-on-scroll, responsive layout. It respects
  `prefers-reduced-motion`, lazy-loads three.js only when an Earth is on screen and
  pauses all animation when the tab is hidden.
- **Showpiece sign-in / sign-up**: the full space scene behind a glass card with
  floating-label inputs, show/hide password, Caps Lock hint, a role picker
  (Analyst / Administrator), live stats (countries, data years, records, Karachi
  right now) and proper loading, error and success states. Forms work with or
  without JavaScript.
- **Live Globe** (`/globe`): 177 Natural Earth countries on a 3D satellite globe.
  Drag, zoom, hover to highlight (coloured by Berkeley Earth warming), search box,
  Globe / Flat map toggle, live temperature labels for 44 cities. Clicking a country
  opens a panel for its capital (or centre) with three tabs:
  - **Past**: monthly temperature and rain since 1970 (1Y / 5Y / 30Y / All),
    warming stripes, seasonal cycle, yearly rain, anomaly heatmap, extremes.
  - **Present**: current conditions, a 16-day forecast and the next 48 hours.
  - **Future**: the 2-10 year climate projection below.
- **Projections** (`/projections`): 2 to 10 year projections of monthly and yearly
  mean temperature and rainfall for any place, with 80% / 95% bands, a CMIP6
  cross-check, a backtest and a CSV download.
- **Aria, the AI climate analyst**: a floating chat on every signed-in page. It is
  grounded in the app's data and live Open-Meteo data for the place asked about,
  can draw a small chart inline, types out replies and keeps a short history.
- **Charts over text**: the dashboard now has warming stripes, a live world board,
  trend + forecast, monthly climatology, a month-by-year heatmap, extremes,
  forecast-vs-actual error, country comparisons, fastest-warming countries,
  year-over-year change and KPI cards with sparklines. Predictions, Explorer,
  Correlation and Admin pages gained charts too. All charts are animated, themed
  and have tooltips (Chart.js 4).

## How the long-range projection works
`climate_lib.py`, pure Python (no numpy) so the serverless bundle stays tiny:
1. Monthly history for the point from the Open-Meteo Historical Weather API (ERA5,
   1970 to last month). If Open-Meteo is rate-limiting, it falls back to NASA POWER
   monthly data (MERRA-2, 1981 onward) and says so on screen.
2. Seasonality: the normal of each calendar month (1991-2020).
3. Trend: least squares line on the monthly anomalies from 1980 onward.
4. Uncertainty: month-to-month noise + slow natural variability (spread of 5-year
   means) + trend uncertainty corrected for autocorrelation, so bands widen with
   the horizon.
5. Backtest: the same method trained only to 2015 predicts 2016 onward; MAE, RMSE,
   bias and band coverage are shown, next to a climatology-only baseline.
6. Cross-check: three CMIP6 HighResMIP models from the Open-Meteo Climate API
   (to 2050), with any remaining offset to the observations removed.

Daily weather cannot be predicted years ahead; the app forecasts daily weather up
to 16 days and the **climate** (monthly and yearly averages, with ranges) up to 10
years.

## Architecture
- `app.py`: Flask application (routes, authentication, role checks, live APIs).
- `climate_lib.py`: Open-Meteo / NASA POWER clients with memory + `/tmp` caching,
  history summaries, forecast, projection engine, backtest, CMIP6 cross-check.
- `analyst.py`: the AI analyst (LLM call + grounding + rule-based fallback).
- `prep_data.py`: builds the JSON data files in `data/` (MapReduce pattern).
- `templates/`: Jinja2 pages. `static/es/`: design system, charts kit, globe,
  place panels, chat. `static/vendor/globe.gl.min.js` (bundles three.js),
  `static/img/` Earth textures, `static/es/countries.geojson` (Natural Earth
  110m, 177 countries with capital points).

### New API routes (all require sign-in except the pulse)
| Route | What it returns |
| --- | --- |
| `/api/place/past?lat=&lon=` | monthly history summary (Past tab) |
| `/api/place/present?lat=&lon=` | current conditions + 16 days (Present tab) |
| `/api/place/projection?lat=&lon=&years=2..10` | projection + backtest |
| `/api/place/cmip6?lat=&lon=&years=` | CMIP6 ensemble cross-check |
| `/api/live-cities` | 44 cities right now (one batched call) |
| `/api/warming-map` | warming per globe country from Berkeley Earth |
| `/api/geocode?q=` | place search |
| `/api/chat` (POST) | AI analyst reply (+ optional chart) |
| `/api/public/pulse` | Karachi right now, for the sign-in page |

## Environment variables (all optional)
| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | Enables the LLM analyst through Groq's OpenAI-compatible API (free tier). |
| `GROQ_MODEL` | Defaults to `llama-3.3-70b-versatile`. |
| `GEMINI_API_KEY` | Alternative LLM (used when no Groq key is set). |
| `GEMINI_MODEL` | Defaults to `gemini-2.0-flash`. |
| `SECRET_KEY` | Flask session secret (falls back to the built-in demo value). |
| `ALERT_THRESHOLD` | Deployment default alert threshold in C (0.5 to 5.0, default 1.5). |

With no LLM key the analyst falls back to a rule-based analyst that answers common
questions from the same real data, so the demo never breaks. No keys are stored in
the repository; set them in Vercel > Project > Settings > Environment Variables.

## Data sources
Berkeley Earth Surface Temperature (Kaggle), NOAA CO2, Copernicus ERA5 (via Our
World in Data and Open-Meteo), Open-Meteo Forecast and Climate (CMIP6 HighResMIP)
APIs, NASA POWER (fallback), Natural Earth country shapes. The free Open-Meteo
tier is rate-limited per IP (per minute, hour and day); responses are cached
server-side and in the browser to stay well inside it.

## Machine learning workflow (run by the student in Google Colab)
1. Cleaning: EarthScape_Data_Cleaning_Full_Code.py (577,462 rows to 544,811).
2. Trend prediction: EarthScape_Train_Test_Full_Code.py (Linear Regression,
   Model 2 trained on 1950 to 2000 data, test RMSE 0.52 C).
3. Anomaly detection: EarthScape_Anomaly_Detection_Full_Code.py (1951 to 1980
   baseline, threshold 1.5 C, 41 alerts, top anomaly March 2010 at +4.31 C).
4. Correlation: EarthScape_Correlation_Full_Code.py (CO2 vs temperature,
   r = 0.9655).

## Running locally
`pip install -r requirements.txt`, then `python app.py`, open http://127.0.0.1:5000
Logins: set ADMIN_USERNAME, ADMIN_PASSWORD, ANALYST_USERNAME and ANALYST_PASSWORD as environment variables (Vercel > Settings > Environment Variables). Without them the app falls back to local development defaults.
Optional: `export GROQ_API_KEY=...` before starting to enable the LLM analyst.

## Deployment
Hosted on Vercel from the GitHub repository (Flask preset, app.py at root).
Every push to the main branch redeploys automatically. No new Python packages
are required (the projection engine is pure Python).

## Alerts: how the numbers work
- **Live alerts** (`live_alerts.py`, cached 6 hours): ERA5 daily means from the
  Open-Meteo archive for Karachi, Lahore, Islamabad, Peshawar, Quetta and Multan
  (one batched request), plus their average as a Pakistan proxy. Each month from
  2014 to the last full month is compared with the 1991-2020 normal of the same
  calendar month; the next 16 forecast days are compared with the daily normal
  (1991-2020, smoothed over 15 days, forecast offset removed using the last 14
  days). If the Open-Meteo quota is exhausted it falls back to NASA POWER daily
  data and says so.
- **Sidebar badge** = live alerts at the current threshold: city-months in the
  last 12 months plus places with forecast days at or above it. Hover it for the
  breakdown.
- **Historical** tab: the original Berkeley Earth list (Pakistan, 2001-2013,
  1951-1980 normal), filtered by the same threshold.
- **Threshold**: saved by an administrator in a signed cookie (survives logout
  and serverless cold starts, but only in that browser), otherwise the
  `ALERT_THRESHOLD` environment variable, otherwise 1.5 C. Vercel's filesystem is
  read-only, so a single threshold shared by every user needs a database or KV
  store (for example Vercel KV / Upstash Redis); none is added here.
