import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # API Keys
    ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")
    
    # OpenClaw / AI Config
    OPENCLAW_ENABLED: bool = os.getenv("OPENCLAW_ENABLED", "true").lower() == "true"
    
    # Web3 / Payment Config
    SEPOLIA_RPC_URL: str = os.getenv("SEPOLIA_RPC_URL", "")
    USDC_ADDRESS_SEPOLIA: str = os.getenv("USDC_ADDRESS_SEPOLIA", "0x1c7d4B196Cb0232491C26109653a6c6224a3383d")
    X402_PAYMENT_RECIPIENT: str = os.getenv("X402_PAYMENT_RECIPIENT", "0x516D97bC82a962627Fd52115F32ce80F2f5da52a")
    X402_REPORT_PRICE_USDC: int = int(os.getenv("X402_REPORT_PRICE_USDC", "1"))
    
    # Swap & Protection Config
    SWAP_AMOUNT_WEI: int = 500000000000000  # 0.0005 ETH in wei
    SAFE_WALLET_ADDRESS: str = "0x000000000000000000000000000000000000dEaD"  # Rescue wallet
    
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
