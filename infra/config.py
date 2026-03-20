import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # API Keys
    ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")
    
    # OpenClaw / AI Config
    OPENCLAW_ENABLED: bool = os.getenv("OPENCLAW_ENABLED", "true").lower() == "true"
    
    # App Config
    APP_ENV: str = os.getenv("APP_ENV", "local")
    ENABLE_CACHE: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    
    # Server Config
    PORT: int = int(os.getenv("PORT", "8001"))
    WEB_PORT: int = int(os.getenv("WEB_PORT", "8081"))
    API_URL: str = os.getenv("API_URL", f"http://127.0.0.1:{PORT}")
    
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    def validate(self):
        if not self.ETHERSCAN_API_KEY:
            print("WARNING: ETHERSCAN_API_KEY not configured. Demo might fail without mock data.")
        return True

settings = Settings()
settings.validate()
