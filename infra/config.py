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
    USDC_ADDRESS_SEPOLIA: str = os.getenv("USDC_ADDRESS_SEPOLIA", "0x1C7D4b196cB0232491C26109653A6c6224a3383D")
    X402_PAYMENT_RECIPIENT: str = os.getenv("X402_PAYMENT_RECIPIENT", "0x516D97bC82a962627Fd52115F32ce80F2f5da52a")
    X402_REPORT_PRICE_USDC: int = int(os.getenv("X402_REPORT_PRICE_USDC", "1"))
    X402_CHAIN_NAME: str = os.getenv("X402_CHAIN_NAME", "sepolia")
    
    # Swap & Protection Config
    SWAP_AMOUNT_WEI: int = int(os.getenv("SWAP_AMOUNT_WEI", "500000000000000"))
    SAFE_WALLET_ADDRESS: str = os.getenv("SAFE_WALLET_ADDRESS", "0x000000000000000000000000000000000000dEaD")
    DEMO_FORCE_TRANSFER_WEI: int = int(os.getenv("DEMO_FORCE_TRANSFER_WEI", "1000000000000000"))
    DEMO_SIMULATED_MOVED_ETH: float = float(os.getenv("DEMO_SIMULATED_MOVED_ETH", "0.001"))
    
    # Execution Safety Layer (ESL)
    MAX_EXPOSURE_ETH: float = float(os.getenv("MAX_EXPOSURE_ETH", "0.5"))
    COOLDOWN_SECONDS: int = int(os.getenv("COOLDOWN_SECONDS", "300"))
    
    # App Config
    APP_ENV: str = os.getenv("APP_ENV", "local")
    ENABLE_CACHE: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    AGENT_DEMO_MODE: bool = os.getenv("AGENT_DEMO_MODE", "false").lower() == "true"
    
    # Server Config
    PORT: int = int(os.getenv("PORT", "8001"))
    WEB_PORT: int = int(os.getenv("WEB_PORT", "8081"))
    API_URL: str = os.getenv("API_URL", f"http://127.0.0.1:{PORT}")
    ETHERSCAN_TX_BASE_URL: str = os.getenv("ETHERSCAN_TX_BASE_URL", "https://sepolia.etherscan.io/tx")
    ETHERSCAN_ADDRESS_BASE_URL: str = os.getenv("ETHERSCAN_ADDRESS_BASE_URL", "https://sepolia.etherscan.io/address")
    SEPOLIA_CHAIN_ID: int = int(os.getenv("SEPOLIA_CHAIN_ID", "11155111"))
    
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    def validate(self):
        if not self.ETHERSCAN_API_KEY:
            print("WARNING: ETHERSCAN_API_KEY not configured. Demo might fail without mock data.")
        return True

settings = Settings()
settings.validate()
