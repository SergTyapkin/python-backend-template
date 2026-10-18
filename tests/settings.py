from pydantic_settings import SettingsConfigDict

from myapp.core.config import Settings


class IsolatedSettings(Settings):
    """Tests ignore developer .env while still allowing explicit environment variables."""

    model_config = SettingsConfigDict(env_file=None)
