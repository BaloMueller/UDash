from gkeepapi.node import NodeLabels
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from datetime import datetime, timezone
import logging
import pytz
import gpsoauth
import gkeepapi

logger = logging.getLogger(__name__)
class Keep(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "Google",
            "expected_key": "G_EMAIL, G_ANDROID_ID, G_MASTER_TOKEN",
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        note_id = settings.get('id')
        if not note_id:
            raise RuntimeError("Note id is required.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        email = device_config.load_env_key("G_EMAIL")
        password = device_config.load_env_key("G_PASSWORD")
        android_id = device_config.load_env_key("G_ANDROID_ID")

        ### Get your master token via one of the two methods below

        ### Get token from cookie oauth
        ### https://github.com/simon-weber/gpsoauth?tab=readme-ov-file#alternative-flow
        # token_t = '...'
        # master_response = gpsoauth.exchange_token(email, token_t, android_id)
        # master_token = master_response['Token']  # if there's no token check the response for more details
        #
        # auth_response = gpsoauth.perform_oauth(
        #     email, master_token, android_id,
        #     service='sj', app='com.google.android.music',
        #     client_sig='38918a453d07199354f8b19af05ec6562ced5788')
        # token = auth_response['Auth']
        # logger.info(f"Token data: {master_token}")

        ### Get token with urllib (not working with latest version of urllib as per https://github.com/urllib3/urllib3/issues/2101)
        ### https://github.com/simon-weber/gpsoauth?tab=readme-ov-file#gpsoauth
        # master_response = gpsoauth.perform_master_login(email, password, android_id)
        # logger.info(f"Token data: {master_response}")
        # master_token = master_response['Token']
        # auth_response = gpsoauth.perform_oauth(
        #     email, master_token, android_id,
        #     service='sj', app='com.google.android.music',
        #     client_sig='38918a453d07199354f8b19af05ec6562ced5788')
        # token = auth_response['Auth']
        # logger.info(f"Token data: {token}")

        master_token = device_config.load_env_key("G_MASTER_TOKEN")
        keep = gkeepapi.Keep()
        success = keep.authenticate(email, master_token)
        keep.sync()

        gnote = keep.get(note_id)
        if not gnote:
            raise RuntimeError("Note not found.")

        gnote_date_str = gnote.timestamps.edited.astimezone().strftime("%Y-%m-%d %H:%M")

        template_params = {
            "title": gnote.title,
            "note_item": gnote.text,
            "date": "Edited: " + gnote_date_str,
            "plugin_settings": settings
        }

        image = self.render_image(dimensions, "keep.html", "keep.css", template_params)
        return image
