from flask import Flask, render_template
import urllib.request
import json
from datetime import datetime

app = Flask(__name__)

# Hamburg HafenCity – Am Hannoverschen Bahnhof 21
LAT = 53.5407
LON = 10.0017
LOCATION = "HafenCity, Hamburg"

WMO_CODES = {
    0: ("Klar", "☀️"),
    1: ("Überwiegend klar", "🌤️"),
    2: ("Teilweise bewölkt", "⛅"),
    3: ("Bedeckt", "☁️"),
    45: ("Nebel", "🌫️"),
    48: ("Raureif-Nebel", "🌫️"),
    51: ("Leichter Nieselregen", "🌦️"),
    53: ("Mäßiger Nieselregen", "🌦️"),
    55: ("Starker Nieselregen", "🌧️"),
    61: ("Leichter Regen", "🌧️"),
    63: ("Mäßiger Regen", "🌧️"),
    65: ("Starker Regen", "🌧️"),
    71: ("Leichter Schnee", "🌨️"),
    73: ("Mäßiger Schnee", "🌨️"),
    75: ("Starker Schnee", "❄️"),
    77: ("Schneekörner", "🌨️"),
    80: ("Leichte Schauer", "🌦️"),
    81: ("Mäßige Schauer", "🌧️"),
    82: ("Starke Schauer", "⛈️"),
    85: ("Leichte Schneeschauer", "🌨️"),
    86: ("Starke Schneeschauer", "❄️"),
    95: ("Gewitter", "⛈️"),
    96: ("Gewitter mit Hagel", "⛈️"),
    99: ("Starkes Gewitter mit Hagel", "⛈️"),
}

def get_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,apparent_temperature,weathercode,"
        f"windspeed_10m,winddirection_10m,relativehumidity_2m,precipitation"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max"
        f"&timezone=Europe%2FBerlin"
        f"&forecast_days=7"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())

        cur = data["current"]
        daily = data["daily"]

        code = cur.get("weathercode", 0)
        desc, emoji = WMO_CODES.get(code, ("Unbekannt", "🌡️"))

        wind_dir = cur.get("winddirection_10m", 0)
        directions = ["N","NO","O","SO","S","SW","W","NW"]
        wind_label = directions[int((wind_dir + 22.5) / 45) % 8]

        current = {
            "temp": round(cur["temperature_2m"]),
            "feels_like": round(cur["apparent_temperature"]),
            "desc": desc,
            "emoji": emoji,
            "wind": round(cur["windspeed_10m"]),
            "wind_dir": wind_label,
            "humidity": cur["relativehumidity_2m"],
            "precip": cur["precipitation"],
            "updated": datetime.now().strftime("%H:%M Uhr"),
        }

        forecast = []
        weekdays = ["Mo","Di","Mi","Do","Fr","Sa","So"]
        for i in range(7):
            dt = datetime.strptime(daily["time"][i], "%Y-%m-%d")
            wd = weekdays[dt.weekday()]
            label = "Heute" if i == 0 else ("Morgen" if i == 1 else f"{wd}, {dt.strftime('%d.%m.')}")
            c = daily["weathercode"][i]
            d, e = WMO_CODES.get(c, ("—", "🌡️"))
            forecast.append({
                "label": label,
                "emoji": e,
                "desc": d,
                "max": round(daily["temperature_2m_max"][i]),
                "min": round(daily["temperature_2m_min"][i]),
                "precip": round(daily["precipitation_sum"][i], 1),
                "wind": round(daily["windspeed_10m_max"][i]),
            })

        return current, forecast, None
    except Exception as e:
        return None, None, str(e)


@app.route("/")
def index():
    current, forecast, error = get_weather()
    return render_template(
        "index.html",
        location=LOCATION,
        current=current,
        forecast=forecast,
        error=error,
    )


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port)