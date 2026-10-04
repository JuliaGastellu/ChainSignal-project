import os
import sys
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Cargo .env solo cuando lo necesito para desarrollo local. Las pruebas
# definen CHAINSIGNAL_DISABLE_DOTENV=1 para no leer nunca mi .env real.
if os.getenv("CHAINSIGNAL_DISABLE_DOTENV", "").lower() not in ("1", "true", "yes"):
    load_dotenv()

class Settings(BaseSettings):
    # Red y proveedores de lectura del producto (infra/red.py). El producto lee
    # Ethereum mainnet; no acepto testnets en READ_ONLY.
    CHAIN_ID: int = int(os.getenv("CHAIN_ID", "1"))
    ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")
    ETHEREUM_RPC_URL: str = os.getenv("ETHEREUM_RPC_URL", "")
    # Ingesta (E03): frescura, confirmaciones, profundidad de reorg y paginación.
    INGESTION_CACHE_TTL_SECONDS: int = int(os.getenv("INGESTION_CACHE_TTL_SECONDS", "60"))
    INGESTION_CONFIRMATIONS: int = int(os.getenv("INGESTION_CONFIRMATIONS", "12"))
    INGESTION_REORG_DEPTH: int = int(os.getenv("INGESTION_REORG_DEPTH", "64"))
    INGESTION_PAGE_SIZE: int = int(os.getenv("INGESTION_PAGE_SIZE", "1000"))
    INGESTION_MAX_PAGES: int = int(os.getenv("INGESTION_MAX_PAGES", "20"))
    INGESTION_MAX_RETRIES: int = int(os.getenv("INGESTION_MAX_RETRIES", "3"))
    PROVIDER_TIMEOUT_SECONDS: float = float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "15"))
    # Worker y notificaciones (E05).
    WORKER_LEASE_SECONDS: float = float(os.getenv("WORKER_LEASE_SECONDS", "60"))
    WORKER_POLL_SECONDS: float = float(os.getenv("WORKER_POLL_SECONDS", "5"))
    WORKER_MAX_ATTEMPTS: int = int(os.getenv("WORKER_MAX_ATTEMPTS", "5"))
    # Apagado por defecto: en este entorno no envío mensajes reales a terceros.
    NOTIFICATIONS_WEBHOOKS_ENABLED: bool = os.getenv("NOTIFICATIONS_WEBHOOKS_ENABLED", "false").lower() == "true"
    MAX_EVENT_STREAMS_PER_ORG: int = int(os.getenv("MAX_EVENT_STREAMS_PER_ORG", "10"))
    # Experiencia comercial (E06).
    SIGNUP_ENABLED: bool = os.getenv("SIGNUP_ENABLED", "false").lower() == "true"
    DEMO_ENABLED: bool = os.getenv("DEMO_ENABLED", "true").lower() == "true"
    DEMO_TTL_HOURS: float = float(os.getenv("DEMO_TTL_HOURS", "24"))
    # Solo fuera de producción: reproduzco una lectura grabada (tests/datos/...)
    # en lugar de consultar un RPC, para E2E con datos controlados.
    AAVE_REPLAY_FIXTURE: str = os.getenv("AAVE_REPLAY_FIXTURE", "")
    # Piloto comercial (E09). Cobro asistido: sin secreto, el webhook de
    # facturación no existe. El formulario de contacto guarda pedidos con
    # consentimiento; no envía respuestas automáticas.
    BILLING_WEBHOOK_SECRET: str = os.getenv("BILLING_WEBHOOK_SECRET", "")
    BILLING_PROVIDER: str = os.getenv("BILLING_PROVIDER", "processor")
    CONTACT_ENABLED: bool = os.getenv("CONTACT_ENABLED", "true").lower() == "true"
    # Explicación opcional con modelo (E07). Apagada por defecto: sin modelo el
    # producto usa la plantilla determinista. Solo la API lee la clave; nunca
    # el worker ni el experimento de firma.
    EXPLANATION_MODEL_ENABLED: bool = os.getenv("EXPLANATION_MODEL_ENABLED", "false").lower() == "true"
    EXPLANATION_API_BASE: str = os.getenv("EXPLANATION_API_BASE", "")
    EXPLANATION_API_KEY: str = os.getenv("EXPLANATION_API_KEY", "")
    EXPLANATION_MODEL: str = os.getenv("EXPLANATION_MODEL", "")
    EXPLANATION_TIMEOUT_SECONDS: float = float(os.getenv("EXPLANATION_TIMEOUT_SECONDS", "15"))
    EXPLANATION_MAX_OUTPUT_TOKENS: int = int(os.getenv("EXPLANATION_MAX_OUTPUT_TOKENS", "600"))
    # Precios en USD por millón de tokens; sin precio no puedo acotar el costo y no habilito el modelo.
    EXPLANATION_PRICE_INPUT_USD_PER_MTOK: str = os.getenv("EXPLANATION_PRICE_INPUT_USD_PER_MTOK", "")
    EXPLANATION_PRICE_OUTPUT_USD_PER_MTOK: str = os.getenv("EXPLANATION_PRICE_OUTPUT_USD_PER_MTOK", "")
    EXPLANATION_DAILY_BUDGET_USD: str = os.getenv("EXPLANATION_DAILY_BUDGET_USD", "1")

    # Web3 y pagos de los experimentos en Sepolia; el producto no los usa.
    SEPOLIA_RPC_URL: str = os.getenv("SEPOLIA_RPC_URL", "")
    USDC_ADDRESS_SEPOLIA: str = os.getenv("USDC_ADDRESS_SEPOLIA", "0x1C7D4b196cB0232491C26109653A6c6224a3383D")
    X402_PAYMENT_RECIPIENT: str = os.getenv("X402_PAYMENT_RECIPIENT", "0x516D97bC82a962627Fd52115F32ce80F2f5da52a")
    X402_REPORT_PRICE_USDC: int = int(os.getenv("X402_REPORT_PRICE_USDC", "1"))
    X402_CHAIN_NAME: str = os.getenv("X402_CHAIN_NAME", "sepolia")

    # Swap y protección (experimento testnet heredado)
    SWAP_AMOUNT_WEI: int = int(os.getenv("SWAP_AMOUNT_WEI", "500000000000000"))
    # No defino un valor por defecto a propósito. Antes apuntaba a la dirección
    # de quema y cualquier despliegue sin esta variable habría destruido fondos
    # en cada transferencia "protectora". validate() frena el arranque.
    SAFE_WALLET_ADDRESS: str = os.getenv("SAFE_WALLET_ADDRESS", "")
    DEMO_FORCE_TRANSFER_WEI: int = int(os.getenv("DEMO_FORCE_TRANSFER_WEI", "1000000000000000"))
    DEMO_SIMULATED_MOVED_ETH: float = float(os.getenv("DEMO_SIMULATED_MOVED_ETH", "0.001"))

    # Capa de seguridad de ejecución (ESL)
    MAX_EXPOSURE_ETH: float = float(os.getenv("MAX_EXPOSURE_ETH", "0.5"))
    COOLDOWN_SECONDS: int = int(os.getenv("COOLDOWN_SECONDS", "300"))

    # Aplicación
    APP_ENV: str = os.getenv("APP_ENV", "local")
    # READ_ONLY (por defecto) o TESTNET_EXPERIMENT. Ver infra/modo.py: la API
    # nunca escribe on-chain; el modo experimental solo habilita experiments/.
    CHAINSIGNAL_MODE: str = os.getenv("CHAINSIGNAL_MODE", "READ_ONLY").strip().upper()
    ENABLE_CACHE: bool = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    AGENT_DEMO_MODE: bool = os.getenv("AGENT_DEMO_MODE", "false").lower() == "true"

    # Sesiones de navegador (E02). Reemplazan la clave global CHAINSIGNAL_API_KEY.
    SESSION_TTL_HOURS: float = float(os.getenv("SESSION_TTL_HOURS", "12"))
    # Secure por defecto. Solo lo apago para desarrollo local sobre http que no
    # sea localhost; los navegadores aceptan cookies Secure en http://localhost.
    SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false"
    INVITATION_TTL_HOURS: float = float(os.getenv("INVITATION_TTL_HOURS", "72"))
    # Orígenes del navegador autorizados para CORS con credenciales y para el
    # chequeo de Origin en mutaciones. Lista separada por comas.
    CORS_ALLOWED_ORIGINS: str = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:8081,http://127.0.0.1:8081,http://localhost:5173,http://127.0.0.1:5173",
    )
    EVENT_STREAM_POLL_SECONDS: float = float(os.getenv("EVENT_STREAM_POLL_SECONDS", "2"))

    # Secreto compartido que exige el microservicio WDK en cada ruta salvo /health.
    WDK_SERVICE_TOKEN: str = os.getenv("WDK_SERVICE_TOKEN", "")

    # Planes, historial de ejecución y presupuestos viven en SQLAlchemy
    # (infra/db.py). Compose apunta esta URL al servicio Postgres `db`. Si
    # queda vacía, el desarrollo local cae en un archivo SQLite temporal; esa
    # base no sirve para certificar concurrencia ni para producción.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    # Operación (E08). Con varias réplicas no migro al arrancar: corro
    # `alembic upgrade head` una vez, como paso aparte, y cada proceso solo
    # verifica que el esquema esté en head. En producción es obligatorio.
    DB_AUTO_MIGRATE: bool = os.getenv("DB_AUTO_MIGRATE", "true").lower() == "true"
    DB_CONNECT_TIMEOUT_SECONDS: int = int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5"))
    DB_STATEMENT_TIMEOUT_MS: int = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "15000"))
    # Token para /metrics. Vacío: la ruta responde 404.
    METRICS_TOKEN: str = os.getenv("METRICS_TOKEN", "")

    # Servidor
    PORT: int = int(os.getenv("PORT", "8001"))
    WEB_PORT: int = int(os.getenv("WEB_PORT", "8081"))
    API_URL: str = os.getenv("API_URL", f"http://127.0.0.1:{PORT}")
    # Los enlaces al explorador salen de infra/red.py según la red; ya no los
    # configuro aparte para no mezclar Sepolia con mainnet.
    SEPOLIA_CHAIN_ID: int = int(os.getenv("SEPOLIA_CHAIN_ID", "11155111"))

    def _validar_produccion(self) -> None:
        """Lo mínimo para operar el piloto sin sorpresas (E08)."""
        if not self.DATABASE_URL.startswith("postgresql"):
            raise RuntimeError("En producción DATABASE_URL es obligatoria y debe apuntar a PostgreSQL.")
        if self.DB_AUTO_MIGRATE:
            raise RuntimeError("En producción DB_AUTO_MIGRATE=false: las migraciones corren como paso aparte, no al arrancar réplicas.")
        if not self.cors_origins or any(not o.startswith("https://") for o in self.cors_origins):
            raise RuntimeError("En producción CORS_ALLOWED_ORIGINS debe listar solo orígenes https.")
        if self.is_read_only:
            # Nombro las variables presentes, nunca sus valores.
            presentes = [n for n, v in (("AGENT_SEED_PHRASE", os.getenv("AGENT_SEED_PHRASE", "")),
                                        ("WDK_SERVICE_TOKEN", self.WDK_SERVICE_TOKEN),
                                        ("SAFE_WALLET_ADDRESS", self.SAFE_WALLET_ADDRESS)) if (v or "").strip()]
            if presentes:
                raise RuntimeError("El runtime de lectura no recibe secretos de firma; quitá: " + ", ".join(presentes))

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_read_only(self) -> bool:
        return self.CHAINSIGNAL_MODE == "READ_ONLY"

    def validate(self):
        if not self.ETHERSCAN_API_KEY:
            # Va a stderr para no ensuciar la salida de las CLI (por ejemplo, JSON).
            print("AVISO: ETHERSCAN_API_KEY no está configurada; sin datos de prueba la demo puede fallar.", file=sys.stderr)

        modos_validos = {"READ_ONLY", "TESTNET_EXPERIMENT"}
        if self.CHAINSIGNAL_MODE not in modos_validos:
            raise RuntimeError(
                f"CHAINSIGNAL_MODE={self.CHAINSIGNAL_MODE!r} no es válido. Uso READ_ONLY o TESTNET_EXPERIMENT."
            )

        from infra.red import REDES

        if self.CHAIN_ID not in REDES:
            raise RuntimeError(f"CHAIN_ID={self.CHAIN_ID} no es una red soportada.")
        if self.is_read_only and REDES[self.CHAIN_ID].es_testnet:
            raise RuntimeError(
                "El runtime de lectura del producto usa Ethereum mainnet (CHAIN_ID=1); las testnets quedan para experiments/."
            )
        if self.INGESTION_PAGE_SIZE < 1 or self.INGESTION_PAGE_SIZE > 10000 or self.INGESTION_MAX_PAGES < 1:
            raise RuntimeError("INGESTION_PAGE_SIZE debe estar entre 1 y 10000 e INGESTION_MAX_PAGES ser positivo.")

        if "*" in self.cors_origins:
            raise RuntimeError("CORS_ALLOWED_ORIGINS no puede ser '*': uso cookies de sesión con credenciales.")
        if self.SESSION_TTL_HOURS <= 0 or self.INVITATION_TTL_HOURS <= 0:
            raise RuntimeError("SESSION_TTL_HOURS e INVITATION_TTL_HOURS deben ser positivos.")
        if self.is_production and self.AAVE_REPLAY_FIXTURE:
            raise RuntimeError("AAVE_REPLAY_FIXTURE no se permite con APP_ENV=production.")
        if self.EXPLANATION_MODEL_ENABLED:
            from decimal import Decimal, InvalidOperation

            if not (self.EXPLANATION_API_BASE and self.EXPLANATION_MODEL):
                raise RuntimeError("EXPLANATION_MODEL_ENABLED exige EXPLANATION_API_BASE y EXPLANATION_MODEL.")
            try:
                precios = [Decimal(self.EXPLANATION_PRICE_INPUT_USD_PER_MTOK), Decimal(self.EXPLANATION_PRICE_OUTPUT_USD_PER_MTOK),
                           Decimal(self.EXPLANATION_DAILY_BUDGET_USD)]
            except InvalidOperation:
                raise RuntimeError("Con el modelo habilitado, los precios por token y el presupuesto diario deben ser números.")
            if any(p < 0 for p in precios) or precios[0] + precios[1] == 0:
                raise RuntimeError("Necesito precios por token positivos para acotar el costo de las explicaciones.")
            if self.is_production and not self.EXPLANATION_API_BASE.startswith("https://"):
                raise RuntimeError("En producción EXPLANATION_API_BASE debe usar https.")
            if not 1 <= self.EXPLANATION_TIMEOUT_SECONDS <= 60 or not 50 <= self.EXPLANATION_MAX_OUTPUT_TOKENS <= 2000:
                raise RuntimeError("EXPLANATION_TIMEOUT_SECONDS debe estar entre 1 y 60 y EXPLANATION_MAX_OUTPUT_TOKENS entre 50 y 2000.")
        if self.is_production:
            self._validar_produccion()
        if self.is_production and not self.SESSION_COOKIE_SECURE:
            raise RuntimeError("En producción la cookie de sesión debe ser Secure (SESSION_COOKIE_SECURE=true).")

        null_address = "0x0000000000000000000000000000000000000000"
        burn_address = "0x000000000000000000000000000000000000dead"
        safe_wallet = (self.SAFE_WALLET_ADDRESS or "").strip().lower()

        # Un destino nulo o de quema nunca es aceptable, aunque esté en READ_ONLY.
        if safe_wallet in {null_address, burn_address}:
            raise RuntimeError(
                f"SAFE_WALLET_ADDRESS resuelve a {safe_wallet}, la dirección nula o de quema. "
                "ChainSignal no arranca: cualquier fondo movido como acción 'protectora' "
                "se perdería de forma permanente."
            )

        # En solo lectura no necesito seed, WDK ni destino de rescate.
        if self.is_read_only:
            return True

        # Desde aquí valido el experimento testnet, que sí firma.
        if self.APP_ENV == "production":
            raise RuntimeError(
                "CHAINSIGNAL_MODE=TESTNET_EXPERIMENT no se permite con APP_ENV=production."
            )

        # Me niego a arrancar si el destino de transferencias protectoras falta:
        # no existe un valor por defecto seguro.
        if not safe_wallet:
            raise RuntimeError(
                "SAFE_WALLET_ADDRESS no está configurada. El experimento testnet no arranca: "
                "el destino de transferencias protectoras debe configurarse de forma "
                "explícita y no tiene un valor por defecto seguro."
            )

        # wallet_controller/wallet_agent.py se autentica con este token y
        # wdk_service/server.js rechaza a quien no lo presenta.
        if not (self.WDK_SERVICE_TOKEN or "").strip():
            raise RuntimeError(
                "WDK_SERVICE_TOKEN no está configurado. El experimento testnet no arranca: el "
                "microservicio WDK no debe aceptar solicitudes sin autenticar."
            )
        return True

settings = Settings()
settings.validate()
