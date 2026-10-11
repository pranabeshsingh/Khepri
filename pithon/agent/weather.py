"""Structured live weather service with zero-API-key requirements."""

import json
import logging
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional

logger = logging.getLogger("pithon.weather")

def get_weather_report(location: str) -> Dict[str, Any]:
    """Fetch live weather metrics from wttr.in JSON API."""
    loc_clean = location.strip() or "Kolkata"
    encoded_loc = urllib.parse.quote(loc_clean)
    url = f"https://wttr.in/{encoded_loc}?format=j1"

    headers = {"User-Agent": "curl/7.88.1"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            current = data.get("current_condition", [{}])[0]
            temp_c = current.get("temp_C", "?")
            feels_c = current.get("FeelsLikeC", temp_c)
            desc = current.get("weatherDesc", [{}])[0].get("value", "Clear").strip()
            humidity = current.get("humidity", "?")
            wind_kmh = current.get("windspeedKmph", "?")
            uv = current.get("uvIndex", "?")

            # Check today's max/min
            today = data.get("weather", [{}])[0]
            max_c = today.get("maxtempC", "?")
            min_c = today.get("mintempC", "?")

            area_info = data.get("nearest_area", [{}])[0]
            area_name = area_info.get("areaName", [{}])[0].get("value", loc_clean)
            country = area_info.get("country", [{}])[0].get("value", "")

            summary = (
                f"🌤️ *Weather for {area_name}* ({country})\n\n"
                f"• *Condition:* {desc}\n"
                f"• *Temperature:* `{temp_c}°C` (Feels like `{feels_c}°C`)\n"
                f"• *High / Low:* `{max_c}°C` / `{min_c}°C`\n"
                f"• *Humidity:* `{humidity}%` | *Wind:* `{wind_kmh} km/h`\n"
                f"• *UV Index:* `{uv}`"
            )

            return {
                "success": True,
                "location": area_name,
                "temp_c": temp_c,
                "condition": desc,
                "humidity": humidity,
                "summary": summary
            }
    except Exception as e:
        logger.warning(f"Error fetching weather for {location}: {e}")
        # Fallback to plain text line
        try:
            line_url = f"https://wttr.in/{encoded_loc}?format=%l:+%c+%t,+%w,+%h+humidity"
            req2 = urllib.request.Request(line_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=6.0) as resp2:
                text_res = resp2.read().decode("utf-8").strip()
                return {
                    "success": True,
                    "location": loc_clean,
                    "summary": f"🌤️ *Weather for {loc_clean}:*\n`{text_res}`"
                }
        except Exception:
            return {
                "success": False,
                "location": loc_clean,
                "summary": f"⚠️ Could not fetch live weather for '{loc_clean}'. Please try again."
            }
