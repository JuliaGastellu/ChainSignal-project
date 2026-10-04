import os
import json
import httpx
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from dotenv import load_dotenv
from loguru import logger

from infra.modo import exigir_escritura_experimental

# Las pruebas definen CHAINSIGNAL_DISABLE_DOTENV=1 para no leer mi .env real.
if os.getenv("CHAINSIGNAL_DISABLE_DOTENV", "").lower() not in ("1", "true", "yes"):
    load_dotenv()

class WalletAgent:
    """Gestiona la identidad on-chain del agente con soporte para Tether WDK.

    Es parte del experimento testnet: cada método que crea identidad, firma o
    pide firmar al WDK exige CHAINSIGNAL_MODE=TESTNET_EXPERIMENT y falla con
    EscrituraDeshabilitada en cualquier otro modo. La API comercial no lo usa.
    """

    def __init__(self):
        self.rpc_url = os.getenv("SEPOLIA_RPC_URL")
        # Respeto WDK_URL cuando existe (en Compose es http://wdk:3001, otro host
        # distinto del localhost del contenedor). Sin ella uso localhost para
        # desarrollo fuera de Docker.
        self.wdk_url = os.getenv("WDK_URL") or f"http://localhost:{os.getenv('WDK_PORT', '3001')}"
        self.wdk_active = False

        # wdk_service/server.js exige este secreto compartido en todas las rutas
        # salvo /health.
        self._wdk_token = os.getenv("WDK_SERVICE_TOKEN", "")
        self._wdk_headers = {"X-WDK-Token": self._wdk_token} if self._wdk_token else {}

        # Verificación inicial del microservicio WDK
        try:
            response = httpx.get(f"{self.wdk_url}/health", timeout=2.0)
            if response.status_code == 200:
                self.wdk_active = True
                logger.success(f"Servicio Tether WDK detectado en {self.wdk_url}. Modo real activado.")
            else:
                logger.warning("Microservicio WDK no respondió correctamente. Usando modo simulación.")
        except Exception:
            logger.info("Microservicio WDK no detectado. Operando en modo simulación (fallback).")

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.account = None
        
    def create_agent_wallet(self):
        """Crea una nueva wallet para el agente o la carga de memoria si existe.

        Ya no envío la seed al servicio WDK en cada solicitud: wdk_service/server.js
        deriva su propia cuenta una vez desde su entorno y yo solo le pido la
        dirección resultante.
        """
        exigir_escritura_experimental("crear_wallet_agente")
        seed_phrase = os.getenv("AGENT_SEED_PHRASE")

        # Si WDK está activo, le pedimos la dirección de SU cuenta de agente
        # (derivada server-side desde su propio AGENT_SEED_PHRASE).
        if self.wdk_active:
            try:
                resp = httpx.post(f"{self.wdk_url}/wallet/create", json={}, headers=self._wdk_headers)
                data = resp.json()
                logger.info(f"Wallet WDK inicializada: {data['address']}")
                return data
            except Exception as e:
                logger.error(f"Error inicializando wallet en WDK: {e}")

        # Fallback a Web3.py estándar (solo para obtener una dirección/keypair
        # locales cuando WDK no está disponible; este camino nunca firma ni
        # envía transacciones - ver ejecutar_transaccion, que exige wdk_active).
        if seed_phrase:
            try:
                self.account = Account.from_mnemonic(seed_phrase)
                logger.info(f"Wallet del agente cargada desde seed phrase (Web3): {self.account.address}")
            except Exception as e:
                logger.warning(f"No se pudo derivar wallet desde AGENT_SEED_PHRASE: {e}. Creando wallet nueva.")
                self.account = Account.create()
                logger.success(f"Nueva wallet de agente creada (Web3): {self.account.address}")
        else:
            self.account = Account.create()
            logger.success(f"Nueva wallet de agente creada (Web3): {self.account.address}")

        # Nunca devuelvo material de clave desde aquí. Si este camino alternativo
        # necesitara firmar, usaría self.account internamente y no un valor que
        # alguien pudiera serializar.
        return {"address": self.account.address}

    def get_balance(self, address=None):
        """Obtiene el balance de la wallet en ETH."""
        target_address = address or (self.account.address if self.account else None)
        if not target_address:
            return 0
            
        # Si WDK está activo, consultamos por ahí
        if self.wdk_active:
            try:
                resp = httpx.get(f"{self.wdk_url}/wallet/balance", params={"address": target_address}, headers=self._wdk_headers)
                return float(resp.json().get("balanceEth", 0))
            except Exception as e:
                logger.warning(f"Error consultando balance en WDK: {e}. Usando Web3 fallback.")

        try:
            balance_wei = self.w3.eth.get_balance(target_address)
            return self.w3.from_wei(balance_wei, 'ether')
        except Exception as e:
            logger.error(f"Error obteniendo balance: {e}")
            return 0

    def ejecutar_transaccion(self, to, value_wei, use_aa=False):
        """Envía una transacción real usando WDK.

        No envío la seed por la red: el servicio WDK firma con su propia cuenta.
        """
        exigir_escritura_experimental("transferir")
        if not self.wdk_active:
            logger.warning("Intento de transacción real sin WDK activo. Abortando.")
            return None

        try:
            logger.info(f"Ejecutando envío WDK: {value_wei} Wei a {to} (AA={use_aa})")
            resp = httpx.post(f"{self.wdk_url}/wallet/send", json={
                "to": to,
                "valueWei": str(value_wei),
                "useAA": use_aa
            }, headers=self._wdk_headers, timeout=30.0)
            
            if resp.status_code == 200:
                data = resp.json()
                logger.success(f"Transacción WDK exitosa. Hash: {data['hash']}")
                return data['hash']
            else:
                logger.error(f"Fallo en microservicio WDK: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Error en comunicación con WDK: {e}")
            return None

    def deploy_contract(self, abi, bytecode, args=None):
        """Despliega un contrato inteligente usando el microservicio WDK.

        No envío la seed por la red: el servicio WDK firma con su propia cuenta.
        """
        exigir_escritura_experimental("desplegar_contrato")
        if not self.wdk_active:
            logger.warning("WDK no activo. Despliegue cancelado.")
            return None

        try:
            logger.info("Solicitando despliegue de contrato a WDK...")
            resp = httpx.post(f"{self.wdk_url}/contract/deploy", json={
                "abi": abi,
                "bytecode": bytecode,
                "args": args or []
            }, headers=self._wdk_headers, timeout=60.0)
            
            if resp.status_code == 200:
                data = resp.json()
                logger.success(f"Contrato desplegado con éxito en: {data['address']}")
                return data
            else:
                logger.error(f"Error en despliegue WDK: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Fallo en comunicación con WDK para deploy: {e}")
            return None

    def call_contract(self, address, abi, method, args=None, value=0, use_aa=False):
        """Ejecuta una función de escritura en un contrato inteligente.

        No envío la seed por la red: el servicio WDK firma con su propia cuenta.
        """
        exigir_escritura_experimental("llamar_contrato")
        if not self.wdk_active:
            logger.warning("WDK no activo. Llamada a contrato cancelada.")
            return None

        try:
            logger.info(f"Llamando a {method} en contrato {address} (AA={use_aa})...")
            resp = httpx.post(f"{self.wdk_url}/contract/call", json={
                "address": address,
                "abi": abi,
                "method": method,
                "args": args or [],
                "value": str(value),
                "useAA": use_aa
            }, headers=self._wdk_headers, timeout=60.0)
            
            if resp.status_code == 200:
                data = resp.json()
                logger.success(f"Llamada a contrato exitosa. Hash: {data['hash']}")
                return data['hash']
            else:
                logger.error(f"Error en llamada a contrato WDK: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Fallo en comunicación con WDK para call: {e}")
            return None

    def get_contract_state(self, address, abi, method, args=None):
        """Consulta el estado (lectura) de un contrato inteligente."""
        try:
            params = {
                "address": address,
                "abi": json.dumps(abi),
                "method": method,
                "args": json.dumps(args or [])
            }
            resp = httpx.get(f"{self.wdk_url}/contract/state", params=params, headers=self._wdk_headers, timeout=10.0)
            if resp.status_code == 200:
                return resp.json().get("result")
            else:
                logger.error(f"Error consultando estado de contrato: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Fallo en consulta de contrato: {e}")
            return None

    def get_swap_quote(self, token_in, token_out, amount):
        """Obtiene una cotización para un swap de tokens."""
        if not self.wdk_active:
            logger.warning("WDK no activo. No se puede obtener cotización.")
            return None
        
        try:
            resp = httpx.post(f"{self.wdk_url}/swap/quote", json={
                "tokenIn": token_in,
                "tokenOut": token_out,
                "amount": str(amount)
            }, headers=self._wdk_headers, timeout=15.0)
            
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"Error en cotización WDK: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Fallo en comunicación con WDK para quote: {e}")
            return None

    def execute_swap(self, token_in, token_out, amount, use_aa=False):
        """Ejecuta un swap de tokens usando WDK.

        No envío la seed por la red: el servicio WDK firma con su propia cuenta.
        """
        exigir_escritura_experimental("ejecutar_swap")
        if not self.wdk_active:
            logger.warning("WDK no activo. Swap cancelado.")
            return None

        try:
            logger.info(f"Ejecutando swap WDK: {amount} de {token_in} a {token_out} (AA={use_aa})")
            resp = httpx.post(f"{self.wdk_url}/swap/execute", json={
                "tokenIn": token_in,
                "tokenOut": token_out,
                "amount": str(amount),
                "useAA": use_aa
            }, headers=self._wdk_headers, timeout=60.0)
            
            if resp.status_code == 200:
                data = resp.json()
                logger.success(f"Swap WDK exitoso. Hash: {data['hash']}")
                return data
            else:
                logger.error(f"Error en swap WDK: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Fallo en comunicación con WDK para swap: {e}")
            return None
