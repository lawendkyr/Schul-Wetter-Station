from flask import Flask, render_template, jsonify, request
import urllib.request
import json
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)

DB_PATH = "/app/data/sensor.db"

config = {
    "lat": 53.5407,
    "lon": 10.0017,
    "location": "HafenCity, Hamburg",
}

WMO_CODES = {
    0: ("Klar", "☀️"), 1: ("Überwiegend klar", "🌤️"),
    2: ("Teilweise bewölkt", "⛅"), 3: ("Bedeckt", "☁️"),
    45: ("Nebel", "🌫️"), 48: ("Raureif-Nebel", "🌫️"),
    51: ("Leichter Nieselregen", "🌦️"), 53: ("Mäßiger Nieselregen", "🌦️"),
    55: ("Starker Nieselregen", "🌧️"), 61: ("Leichter Regen", "🌧️"),
    63: ("Mäßiger Regen", "🌧️"), 65: ("Starker Regen", "🌧️"),
    71: ("Leichter Schnee", "🌨️"), 73: ("Mäßiger Schnee", "🌨️"),
    75: ("Starker Schnee", "❄️"), 77: ("Schneekörner", "🌨️"),
    80: ("Leichte Schauer", "🌦️"), 81: ("Mäßige Schauer", "🌧️"),
    82: ("Starke Schauer", "⛈️"), 85: ("Leichte Schneeschauer", "🌨️"),
    86: ("Starke Schneeschauer", "❄️"), 95: ("Gewitter", "⛈️"),
    96: ("Gewitter mit Hagel", "⛈️"), 99: ("Starkes Gewitter mit Hagel", "⛈️"),
}

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            temperature REAL,
            humidity REAL,
            air_quality_raw INTEGER,
            air_quality TEXT,
            uv_index REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={config['lat']}&longitude={config['lon']}"
        f"&current=temperature_2m,apparent_temperature,weathercode,"
        f"windspeed_10m,winddirection_10m,relativehumidity_2m,precipitation"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max"
        f"&timezone=Europe%2FBerlin&forecast_days=7"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
        cur = data["current"]
        daily = data["daily"]
        code = cur.get("weathercode", 0)
        desc, emoji = WMO_CODES.get(code, ("Unbekannt", "🌡️"))
        directions = ["N","NO","O","SO","S","SW","W","NW"]
        wind_label = directions[int((cur.get("winddirection_10m", 0) + 22.5) / 45) % 8]
        current = {
            "temp": round(cur["temperature_2m"]),
            "feels_like": round(cur["apparent_temperature"]),
            "desc": desc, "emoji": emoji,
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
                "label": label, "emoji": e, "desc": d,
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
    sensor = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            sensor = dict(row)
    except:
        pass
    return render_template("index.html", location=config["location"],
                           current=current, forecast=forecast,
                           error=error, sensor=sensor)

@app.route("/api", methods=["POST"])
def api_receive():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    required = ["temperature", "humidity", "air_quality_raw", "air_quality", "uv_index"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Feld fehlt: {field}"}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO sensor_data
                (timestamp, temperature, humidity, air_quality_raw, air_quality, uv_index)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            float(data["temperature"]),
            float(data["humidity"]),
            int(data["air_quality_raw"]),
            str(data["air_quality"]),
            float(data["uv_index"]),
        ))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "message": "Daten gespeichert"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api", methods=["GET"])
def api_latest():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM sensor_data ORDER BY id DESC LIMIT 100"
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port)