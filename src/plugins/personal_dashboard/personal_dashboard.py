import logging
from datetime import datetime
import pytz
from plugins.base_plugin.base_plugin import BasePlugin
from plugins.personal_dashboard.widgets import (
    TemperatureWidget,
    WeatherWidget,
    BirthdaysWidget,
)

logger = logging.getLogger(__name__)

class PersonalDashboard(BasePlugin):
    """Always-on dashboard plugin showing device temperature, tomorrow's weather
    forecast, and upcoming birthdays from a Google Calendar ICS feed."""

    def generate_image(self, settings, device_config):
        tz_name = device_config.get_config("timezone", default="UTC")
        tz = pytz.timezone(tz_name)

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        temperature = TemperatureWidget.get_data()

        try:
            weather = WeatherWidget.get_data(settings)
        except Exception as e:
            logger.error(f"Failed to fetch tomorrow's weather: {e}")
            weather = None

        try:
            birthdays = BirthdaysWidget.get_data(settings, tz)
        except Exception as e:
            logger.error(f"Failed to fetch birthdays from ICS: {e}")
            birthdays = []

        now = datetime.now(tz)
        template_params = {
            "plugin_settings": settings,
            "temperature": temperature,
            "weather": weather,
            "birthdays": birthdays,
            "current_date": f"{now.strftime('%A')}, {now.day} {now.strftime('%B %Y')}",
            "lookahead_days": int(settings.get("birthdayLookaheadDays", 60)),
        }

        image = self.render_image(dimensions, "dashboard.html", "dashboard.css", template_params)
        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image
