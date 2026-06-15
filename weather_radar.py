#!/usr/bin/env python3
"""
Weather Radar GPS - Terminal Weather & Rain Radar
Supports GPS (Termux Android) or IP geolocation fallback.
Data source: Open-Meteo (no API key required)
"""

import os
import sys
import time
import json
import platform
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from typing import Optional, Tuple


# ─── CONFIG ─---------------------------------------------------------------
try:
    with open(os.path.expanduser("~/.weather_radar_config.json")) as f:
        CONFIG = json.load(f)
except Exception:
    CONFIG = {
        "units": "metric",        # metric | imperial
        "tz": "auto",             # auto | timezone string
        "refresh_min": 10,
        "gps_timeout": 8,
        "last_lat": None,
        "last_lon": None,
        "last_city": None,
    }

UNITS       = CONFIG.get("units", "metric")
GPS_TIMEOUT = CONFIG.get("gps_timeout", 8)
REFRESH_MIN = CONFIG.get("refresh_min", 10)
# ---------------------------------------------------------------------------


# ─── CONSTANTS ─────────────────────────────────────────────────────────────
WMO_CODES = {
    0:  ("☀️",  "Cerah"),
    1:  ("🌤",  "Cerah sebagian"),
    2:  ("⛅",  "Berawan sebagian"),
    3:  ("☁️",  "Berawan"),
    45: ("🌫️",  "Berkabut"),
    48: ("🌫️",  "Berkabut beku"),
    51: ("🌦",  "Gerimis ringan"),
    53: ("🌦",  "Gerimis"),
    55: ("🌧",  "Gerimis lebat"),
    56: ("🌧",  "Gerimis beku ringan"),
    57: ("🌧",  "Gerimis beku"),
    61: ("🌦",  "Hujan ringan"),
    63: ("🌧",  "Hujan"),
    65: ("🌧",  "Hujan lebat"),
    66: ("🌧",  "Hujan beku"),
    67: ("🌧",  "Hujan beku lebat"),
    71: ("🌦",  "Salju ringan"),
    73: ("❄️",  "Salju"),
    75: ("❄️",  "Salju lebat"),
    77: ("❄️",  "Butir salju"),
    80: ("🌦",  "Hujan semburan ringan"),
    81: ("🌧",  "Hujan semburan"),
    82: ("🌧",  "Hujan semburan lebat"),
    85: ("🌦",  "Hujan salju ringan"),
    86: ("❄️",  "Hujan salju lebat"),
    95: ("⛈",  "Badai petir"),
    96: ("⛈",  "Badai petir + hujan es ringan"),
    99: ("⛈",  "Badai petir + hujan es"),
}

TEMP_UNIT  = "°C" if UNITS == "metric" else "°F"
WIND_UNIT  = "km/h" if UNITS == "metric" else "mph"
PRECIP_UNIT = "mm" if UNITS == "metric" else "in"

BG_DARK    = "\033[48;5;236m"   # dark grey
BG_BLUE    = "\033[48;5;17m"    # dark blue   (rain)
BG_CYAN    = "\033[48;5;24m"    # blue-cyan   (rain+)
BG_LIGHT   = "\033[48;5;153m"   # cyan        (light rain)
FG_WHITE   = "\033[38;5;15m"
FG_YELLOW  = "\033[38;5;220m"
FG_GREEN   = "\033[38;5;120m"
FG_RED     = "\033[38;5;202m"
RESET      = "\033[0m"
BOLD       = "\033[1m"
DIM        = "\033[2m"

RAIN_COLORS = [
    (0.00, " "),
    (0.10, "\033[48;5;153m \033[0m"),  # light cyan
    (0.50, "\033[48;5;24m \033[0m"),   # blue
    (2.00, "\033[48;5;17m \033[0m"),   # dark blue
    (10.0, "\033[41m\033[38;5;255m █\033[0m"),  # red warning
]

QUOTES = [
    "Pack your umbrella before the sky does.",
    "Not all storms come to disrupt your life,\n  some come to clear your path. 💫",
    "Plan a cloudy day; enjoy the sunny ones. 🌞",
    "The best thing to predict is yourself.",
    "Stay dry, stay curious. ☔",
]
# ---------------------------------------------------------------------------


def fetch_json(url: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
    """Fetch JSON from URL safely."""
    try:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "WeatherRadarGPS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  {DIM}[err fetch: {e}]{RESET}")
        return None


def get_gps_location() -> Optional[Tuple[float, float]]:
    """
    Try GPS via Termux:API on Android.
    With fallback to IP-based geolocation.
    """
    if CONFIG.get("last_lat") and CONFIG.get("last_lon"):
        return CONFIG["last_lat"], CONFIG["last_lon"]

    # Termux GPS
    try:
        import subprocess
        result = subprocess.run(
            ["termux-location", "-p", "gps"],
            capture_output=True, text=True, timeout=GPS_TIMEOUT
        )
        if result.returncode == 0:
            loc = json.loads(result.stdout)
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if lat and lon:
                return lat, lon
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass

    # IP geolocation fallback
    print(f"  {DIM}[GPS tidak tersedia, pakai lokasi IP...]{RESET}")
    try:
        data = fetch_json("https://ipapi.co/json/", timeout=10)
        if data and data.get("latitude") and data.get("longitude"):
            return float(data["latitude"]), float(data["longitude"])
    except Exception:
        pass

    return None


def get_city_name(lat: float, lon: float) -> str:
    """Reverse geocode lat/lon to city name."""
    data = fetch_json(
        "https://nominatim.openstreetmap.org/reverse",
        {"lat": lat, "lon": lon, "format": "json", "zoom": 10, "accept_language": "id"},
        timeout=10,
    )
    if data:
        addr = data.get("address", {})
        for key in ["city", "town", "village", "county", "state"]:
            if addr.get(key):
                return addr[key]
        return addr.get("country", f"{lat:.3f},{lon:.3f}")
    return f"{lat:.3f},{lon:.3f}"


def get_weather(lat: float, lon: float) -> Optional[dict]:
    """Fetch weather data from Open-Meteo."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,precipitation,cloud_cover,pressure_msl,apparent_temperature",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_sum,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 3,
    }
    return fetch_json("https://api.open-meteo.com/v1/forecast", params, timeout=15)


def get_radar_frame(lat: float, lon: float) -> Optional[dict]:
    """
    Fetch precipitation/radar forecast from Open-Meteo's precipitation model
    (ECMWF / ICON-D2) — purely model-based, no actual radar but gives good
    short-term rain probability maps.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation",
        "timezone": "auto",
        "forecast_hours": 24,
    }
    return fetch_json("https://api.open-meteo.com/v1/forecast", params, timeout=15)


# ─── RENDER ────────────────────────────────────────────────────────────────

def k_to_c(k: Optional[float]) -> Optional[float]:
    if k is None: return None
    return round(k - 273.15, 1)


def wind_deg_to_dir(deg: Optional[float]) -> str:
    if deg is None: return "?"
    dirs = ["U","UU","T","TT","S","SS","B","BB"]
    return dirs[int((deg + 22.5) / 45.0) % 8]


def rain_cell(precip: Optional[float]) -> str:
    """Return coloured cell for rain grid."""
    if precip is None or precip < 0.05:
        return " ·"
    for threshold, cell in RAIN_COLORS[1:]:
        if precip < threshold:
            return cell
    return RAIN_COLORS[-1][1]


def trunc(s: str, n: int) -> str:
    return (s[: n - 1] + "…") if len(s) > n else s


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def draw_card(text: str, title: str = "", color: str = FG_WHITE) -> str:
    border = "─" * 44
    lines  = text.split("\n")
    result = f"{BOLD}{color}┌{border}┐{RESET}\n"
    if title:
        result += f"{BOLD}{color}│{RESET} {BOLD}{FG_YELLOW}{title}{RESET}"
        result += " " * (44 - len(title)) + f"{BOLD}{color}│{RESET}\n"
        result += f"{BOLD}{color}├{border}┤{RESET}\n"
    for line in lines:
        pad = 44 - len(line.encode("utf-8").decode())  # crude but ok
        result += f"{BOLD}{color}│{RESET} {color}{line}{RESET} {' ' * max(0, 44 - len(line))}{BOLD}{color}│{RESET}\n"
    result += f"{BOLD}{color}└{border}┘{RESET}"
    return result


def render_weather(lat: float, lon: float, data: dict) -> str:
    cur  = data.get("current", {})
    dly  = data.get("daily",   {})
    hrly = data.get("hourly",  {})

    time_now  = datetime.now().strftime("%H:%M")
    date_now  = datetime.now().strftime("%a, %d %b %Y")

    # Current
    code  = cur.get("weather_code", 999)
    icon, desc = WMO_CODES.get(code, ("❓", f"Unknown ({code})"))
    t_cur = cur.get("temperature_2m")
    t_ap  = cur.get("apparent_temperature")
    hum   = cur.get("relative_humidity_2m")
    wind  = cur.get("wind_speed_10m")
    wdir  = cur.get("wind_direction_10m")
    cld   = cur.get("cloud_cover")
    precip= cur.get("precipitation")
    pres  = cur.get("pressure_msl")

    city_name = get_city_name(lat, lon)

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────
    lines.append(f"  {BOLD}{FG_CYAN}🌍 {city_name.upper()}{RESET}")
    lines.append(f"  {DIM}{lat:.4f}°, {lon:.4f}°  |  {date_now}  |  {time_now}{RESET}")
    lines.append("")

    # ── Current conditions card ───────────────────────────────────────────
    card: list[str] = []
    temp_str = f"{t_cur:.1f}{TEMP_UNIT}" if t_cur is not None else "N/A"
    ap_str   = f"{t_ap:.1f}{TEMP_UNIT}" if t_ap is not None  else "N/A"
    wnd_str  = f"{wind:.1f} {WIND_UNIT} {wind_deg_to_dir(wdir)}" if wind is not None else "N/A"
    cld_str  = f"{cld}%" if cld is not None else "N/A"
    hum_str  = f"{hum}%" if hum is not None else "N/A"
    prc_str  = f"{precip:.1f} {PRECIP_UNIT}" if precip is not None else "0"
    
    card.append(f"  {icon}  {desc}")
    card.append(f"  Suhu     : {BOLD}{FG_YELLOW}{temp_str}{RESET}  (terasa {ap_str})")
    card.append(f"  Angin    : {wnd_str}")
    card.append(f"  Kelembaban: {hum_str}  |  {DIM}awan {cld_str}{RESET}")
    if precip and precip > 0.1:
        card.append(f"  Curah hujan: {FG_CYAN}{prc_str}{RESET}")
    if pres:
        card.append(f"  Tekanan  : {pres:.0f} hPa")
    card.append("")

    lines.append(draw_card("\n".join(card), "─── SEKARANG ───", FG_GREEN))
    lines.append("")

    # ── Mini rain radar (12H) ─────────────────────────────────────────────
    hrly_time  = hrly.get("time", [])
    hrly_prcp  = hrly.get("precipitation", []) or hrly.get("precipitation_probability", [])
    now_idx    = 0
    for i, t in enumerate(hrly_time):
        try:
            if datetime.fromisoformat(t).hour == datetime.now().hour:
                now_idx = i
                break
        except:
            pass

    # Grid radar 4 rows x 6 cols = 24 hours
    def rain_bar(precip: Optional[float], height: int = 4) -> list[str]:
        blocks = ["█", "▄", "░", "·"]
        if precip is None or precip < 0.05:
            h = 0
        elif precip < 0.5:
            h = 1
        elif precip < 2.0:
            h = 2
        elif precip < 10.0:
            h = 3
        else:
            h = 4
        bar = []
        for i in range(height):
            if h > (height - 1 - i):
                bar.append(blocks[min(i, len(blocks)-1)])
            else:
                bar.append(" ")
        return bar

    radar_rows = [[] for _ in range(4)]
    radar_labels = []
    end_idx = min(now_idx + 24, len(hrly_prcp)) if hrly_prcp else now_idx
    for i in range(now_idx, end_idx):
        p = hrly_prcp[i] if i < len(hrly_prcp) else None
        bar = rain_bar(p, height=4)
        for row_idx, cell in enumerate(bar):
            radar_rows[row_idx].append(cell)
        hr = None
        try:
            hr = datetime.fromisoformat(hrly_time[i]).hour
        except:
            pass
        if hr is not None:
            label = f"{hr:02d}"
        else:
            label = "  "
        radar_labels.append(label)

    # Build grid
    rain_lines: list[str] = []
    rain_lines.append(f"  {BOLD}{FG_CYAN}🌧  RADAR HUJAN 24 jam ke depan{RESET}")
    rain_lines.append(f"  {DIM}{'─' * 50}{RESET}")
    label_row = "   " + " ".join(lbl[:2].rjust(2, " ") for lbl in radar_labels[:24:2])
    rain_lines.append(f"  {DIM}{label_row}{RESET}")

    # 4-bar display
    for row in radar_rows:
        rain_lines.append("  " + "  ".join(row))

    rain_lines.append("")
    lines.append(draw_card("\n".join(rain_lines), "─── RADAR HUJAN ───", FG_CYAN))
    lines.append("")

    # ── 3-day forecast ────────────────────────────────────────────────────
    daily_lines: list[str] = []
    d_time   = dly.get("time", [])
    d_code   = dly.get("weather_code", [])
    d_max    = dly.get("temperature_2m_max", [])
    d_min    = dly.get("temperature_2m_min", [])
    d_prcp   = dly.get("precipitation_sum", [])
    d_prcp_p = dly.get("precipitation_probability_max", [])
    d_sunrise= dly.get("sunrise", [])
    d_sunset = dly.get("sunset", [])

    for i in range(min(3, len(d_time))):
        dt = datetime.fromisoformat(d_time[i])
        day_name = dt.strftime("%a %d/%m")
        icon_d, desc_d = WMO_CODES.get(d_code[i], ("❓", str(d_code[i])))
        t_max = f"{d_max[i]:.0f}{TEMP_UNIT}" if d_max[i] is not None else "?"
        t_min = f"{d_min[i]:.0f}{TEMP_UNIT}" if d_min[i] is not None else "? : "
        prc   = f"{d_prcp[i]:.1f}{PRECIP_UNIT}" if d_prcp[i] is not None else "?"
        prcp_p= f"{d_prcp_p[i]}%" if d_prcp_p[i] is not None else "?"
        
        sunrise = datetime.fromisoformat(d_sunrise[i]).strftime("%H:%M") if d_sunrise[i] else "?"
        sunset  = datetime.fromisoformat(d_sunset[i]).strftime("%H:%M")  if d_sunset[i]  else "?"

        daily_lines.append(f"  {icon_d} {day_name}")
        daily_lines.append(f"     {t_min}→{t_max}")
        daily_lines.append(f"     ☀️{sunrise} 🌅{sunset}")
        daily_lines.append(f"     Hujan: {FG_CYAN}{prc}{RESET} ({prcp_p})")
        daily_lines.append("")

    lines.append(draw_card("\n".join(daily_lines), "─── 3 HARI KE DEPAN ───", FG_YELLOW))
    lines.append("")

    # ── Quote ─────────────────────────────────────────────────────────────
    import random
    quote = random.choice(QUOTES)
    lines.append(f"  {DIM}💭 \"{quote}\"{RESET}")
    lines.append("  " + DIM + time.strftime("%H:%M:%S") + RESET)

    return "\n".join(lines)


# ─── MAIN LOOP ─────────────────────────────────────────────────────────────

def print_banner() -> None:
    banner = f"""
{BOLD}{FG_CYAN}
   ╔══════════════════════════════════════════════╗
   ║     🌧  WEATHER RADAR + GPS TERMINAL   🌍    ║
   ║            Data: Open-Meteo API              ║
   ╚══════════════════════════════════════════════╝{RESET}
"""
    print(banner)


def main() -> None:
    print_banner()

    last_lat = CONFIG.get("last_lat")
    last_lon = CONFIG.get("last_lon")

    if last_lat is None or last_lon is None:
        print(f"  {FG_YELLOW}📍 Mendeteksi lokasi...{RESET}")
        loc = get_gps_location()
        if loc is None:
            print(f"  {FG_RED}❌ GPS tidak tersedia. Jalankan ulang di Termux (termux-api).{RESET}")
            print(f"  {DIM}  Atau set manual di ~/.weather_radar_config.json{RESET}")
            sys.exit(1)
        lat, lon = loc
        print(f"  {FG_GREEN}✓ Lokasi terdeteksi: {lat:.4f}°, {lon:.4f}°{RESET}\n")
        CONFIG["last_lat"] = lat
        CONFIG["last_lon"] = lon
        with open(os.path.expanduser("~/.weather_radar_config.json"), "w") as f:
            json.dump(CONFIG, f, indent=2)
    else:
        lat, lon = last_lat, last_lon

    print(f"  {DIM}Mengambil data cuaca (press Ctrl+C untuk keluar)...{RESET}\n")

    try:
        while True:
            clear_screen()
            print_banner()
            data = get_weather(lat, lon)
            if data:
                output = render_weather(lat, lon, data)
                print(output)
            else:
                print(f"  {FG_RED}❌ Gagal fetch data. Retrying in {REFRESH_MIN}m...{RESET}")

            print(f"  {DIM}[Auto-refresh {REFRESH_MIN} menit | Ctrl+C keluar]{RESET}")
            time.sleep(REFRESH_MIN * 60)

    except KeyboardInterrupt:
        clear_screen()
        print(f"\n  {FG_CYAN}👋 Sampai jumpa! Jangan lupa bawa payung. ☔{RESET}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
