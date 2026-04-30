from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import urllib.request
import json
import os
import platform
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hackerwerkstatt-secret")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "passwort123")

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

# ── Datenbank Setup ───────────────────────────────────
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

# ── Wetter API ────────────────────────────────────────
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

# ── Hauptseite ────────────────────────────────────────
@app.route("/")
def index():
    current, forecast, error = get_weather()
    return render_template("index.html", location=config["location"],
                           current=current, forecast=forecast, error=error)

# ── Sensor API ────────────────────────────────────────
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

# ── Login ─────────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USER and
                request.form.get("password") == ADMIN_PASS):
            session["admin"] = True
            return redirect(url_for("admin"))
        error = "Falscher Benutzername oder Passwort"
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))

# ── Admin Dashboard ───────────────────────────────────
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    message = None
    if request.method == "POST":
        try:
            config["lat"] = float(request.form["lat"])
            config["lon"] = float(request.form["lon"])
            config["location"] = request.form["location"]
            message = "✅ Einstellungen gespeichert!"
        except Exception as e:
            message = f"❌ Fehler: {e}"

    try:
        test_url = f"https://api.open-meteo.com/v1/forecast?latitude={config['lat']}&longitude={config['lon']}&current=temperature_2m"
        with urllib.request.urlopen(test_url, timeout=5) as r:
            api_status = "✅ Online" if r.status == 200 else "⚠️ Fehler"
    except:
        api_status = "❌ Nicht erreichbar"

    try:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM sensor_data").fetchone()[0]
        latest = conn.execute(
            "SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        db_info = {"eintraege": count, "letzter": latest[1] if latest else "—"}
    except:
        db_info = {"eintraege": "—", "letzter": "—"}

    server_info = {
        "python": platform.python_version(),
        "system": platform.system() + " " + platform.release(),
        "hostname": platform.node(),
        "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
    }

    return render_template("admin.html",
        config=config, api_status=api_status,
        server_info=server_info, message=message, db_info=db_info)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port)