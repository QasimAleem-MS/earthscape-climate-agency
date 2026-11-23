"""Build data/era5_by_country.json from Our World in Data's ERA5 country averages.

Source: Copernicus ERA5 reanalysis, monthly 2 m air temperature averaged over each
country's area, published by Our World in Data (updated monthly):
https://ourworldindata.org/grapher/average-monthly-surface-temperature
Run:  python prep_era5.py  (downloads the CSV, about 7 MB)
"""
import csv, io, json, urllib.request
from collections import defaultdict

URL = ("https://ourworldindata.org/grapher/average-monthly-surface-temperature.csv"
       "?v=1&csvType=full&useColumnShortNames=true")
# OWID name -> name used in the Berkeley Earth file, so both series share one key
ALIAS = {"Antigua and Barbuda": "Antigua And Barbuda", "Bosnia and Herzegovina": "Bosnia And Herzegovina",
         "Myanmar": "Burma", "Democratic Republic of Congo": "Congo (Democratic Republic Of The)",
         "Czechia": "Czech Republic", "Cote d'Ivoire": "Côte D'Ivoire", "Falkland Islands": "Falkland Islands (Islas Malvinas)",
         "Guinea-Bissau": "Guinea Bissau", "Heard Island and McDonald Islands": "Heard Island And Mcdonald Islands",
         "Isle of Man": "Isle Of Man", "North Macedonia": "Macedonia", "Palestine": "Palestina",
         "Saint Vincent and the Grenadines": "Saint Vincent And The Grenadines", "Sao Tome and Principe": "Sao Tome And Principe",
         "South Georgia and the South Sandwich Islands": "South Georgia And The South Sandwich Isla",
         "Eswatini": "Swaziland", "East Timor": "Timor Leste", "Trinidad and Tobago": "Trinidad And Tobago",
         "United States Virgin Islands": "Virgin Islands",
         "Africa (NIAID)": "Africa", "Asia (NIAID)": "Asia", "Europe (NIAID)": "Europe",
         "North America (NIAID)": "North America", "South America (NIAID)": "South America", "Oceania (NIAID)": "Oceania"}
SKIP_WORDS = ("Ocean", "Sea", "Seas", "Mediterranean", "Antarctica (NIAID)", "Australia (NIAID)", "Arctic")

def main(path=None):
    raw = open(path).read() if path else urllib.request.urlopen(URL, timeout=120).read().decode()
    monthly = defaultdict(dict)
    for r in csv.DictReader(io.StringIO(raw)):
        e = r["entity"]
        if "(NIAID" in e and ALIAS.get(e) is None:
            continue
        name = ALIAS.get(e, e)
        y, m = r["month"].split("-")
        try:
            monthly[name][(int(y), int(m))] = float(r["temperature_2m"])
        except ValueError:
            pass
    out = {}
    for name, mm in monthly.items():
        years = sorted({y for y, _ in mm})
        full = [[y, round(sum(mm[(y, m)] for m in range(1, 13)) / 12, 2)]
                for y in years if all((y, m) in mm for m in range(1, 13))]
        last_y = years[-1]
        months = sorted(m for (y, m) in mm if y == last_y)
        ytd = None
        if len(months) < 12:
            norm = [mm[(y, m)] for y in range(1991, 2021) for m in months if (y, m) in mm]
            ytd = {"year": last_y, "months": len(months), "last_month": months[-1],
                   "mean": round(sum(mm[(last_y, m)] for m in months) / len(months), 2),
                   "normal_same_months": round(sum(norm) / len(norm), 2) if norm else None}
        recent = sorted(k for k in mm if k[0] >= last_y - 2)
        out[name] = {"years": full, "ytd": ytd,
                     "monthly": [["%d-%02d" % k, round(mm[k], 2)] for k in recent]}
    json.dump(out, open("data/era5_by_country.json", "w"), separators=(",", ":"))
    print(len(out), "regions;", "Pakistan latest:", out["Pakistan"]["years"][-1], out["Pakistan"]["ytd"])

if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
