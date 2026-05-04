from datetime import date

import requests
from utils.app_utils import resolve_path

# Open-Meteo daily forecast endpoint - 2 days so index 0 = today, index 1 = tomorrow.
_OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lng}"
    "&daily=weathercode,temperature_2m_max,temperature_2m_min"
    "&timezone=auto&forecast_days=2"
)
_OPEN_METEO_IMPERIAL_URL = _OPEN_METEO_URL + "&temperature_unit=fahrenheit"

# WMO Weather Interpretation Codes -> human-readable descriptions.
WMO_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight showers",
    81: "Moderate showers",
    82: "Violent showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ hail",
    99: "Thunderstorm w/ heavy hail",
}

TEMP_UNITS = {
    "metric": "°C",
    "imperial": "°F",
    "standard": "K",
}

WEATHER_ICONS_DIR = resolve_path("plugins/weather/icons")


class WeatherWidget:
    """Fetches and maps tomorrow weather data from Open-Meteo."""

    @staticmethod
    def _map_weather_code_to_icon(weather_code):
        """Map Open-Meteo WMO weather codes to the existing weather plugin icons."""
        icon = "01d"

        if weather_code in [0]:
            icon = "01d"
        elif weather_code in [1]:
            icon = "022d"
        elif weather_code in [2]:
            icon = "02d"
        elif weather_code in [3]:
            icon = "04d"
        elif weather_code in [51, 61, 80]:
            icon = "51d"
        elif weather_code in [53, 63, 81]:
            icon = "53d"
        elif weather_code in [55, 65, 82]:
            icon = "09d"
        elif weather_code in [45]:
            icon = "50d"
        elif weather_code in [48]:
            icon = "48d"
        elif weather_code in [56, 66]:
            icon = "56d"
        elif weather_code in [57, 67]:
            icon = "57d"
        elif weather_code in [71, 85]:
            icon = "71d"
        elif weather_code in [73]:
            icon = "73d"
        elif weather_code in [75, 86]:
            icon = "13d"
        elif weather_code in [77]:
            icon = "77d"
        elif weather_code in [95, 96, 99]:
            icon = "11d"

        return f"{WEATHER_ICONS_DIR}/{icon}.png"

    @staticmethod
    def get_data(settings):
        """Fetch tomorrow's daily forecast from Open-Meteo (no API key required)."""
        lat = settings.get("latitude", "").strip()
        lng = settings.get("longitude", "").strip()
        if not lat or not lng:
            return None

        units = settings.get("units", "metric")
        base_url = _OPEN_METEO_IMPERIAL_URL if units == "imperial" else _OPEN_METEO_URL

        url = base_url.format(lat=lat, lng=lng)
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        times = daily.get("time", [])
        if len(times) < 2:
            return None

        # Index 0 = today, index 1 = tomorrow.
        code = (daily.get("weathercode") or daily.get("weather_code") or [0, 0])[1]
        temp_max = (daily.get("temperature_2m_max") or [0, 0])[1]
        temp_min = (daily.get("temperature_2m_min") or [0, 0])[1]

        if units == "standard":
            temp_max = temp_max + 273.15
            temp_min = temp_min + 273.15

        tomorrow = date.fromisoformat(times[1])
        icon_path = WeatherWidget._map_weather_code_to_icon(int(code))
        return {
            "description": WMO_DESCRIPTIONS.get(int(code), "Unknown"),
            "high": round(temp_max),
            "low": round(temp_min),
            "unit": TEMP_UNITS.get(units, "°C"),
            "date": f"{tomorrow.day} {tomorrow.strftime('%B')}",
            "weekday": tomorrow.strftime("%A"),
            "icon": icon_path,
        }
