import os
import json
import httpx
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

class WalletAgent:
    """Gestiona la identidad on-chain del agente AI con soporte para Tether WDK."""

    def __init__(self):
        self.rpc_url = os.getenv("SEPOLIA_RPC_URL")
        self.wdk_url = f"http://localhost:{os.getenv('WDK_PORT', '3001')}"
        self.wdk_active = False
        
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
        """Crea una nueva wallet para el agente o la carga de memoria si existe."""
        seed_phrase = os.getenv("AGENT_SEED_PHRASE")
        
        # Si WDK está activo y hay seed phrase, priorizamos WDK
        if self.wdk_active and seed_phrase:
            try:
                resp = httpx.post(f"{self.wdk_url}/wallet/create", json={"seedPhrase": seed_phrase})
                data = resp.json()
                logger.info(f"Wallet WDK inicializada: {data['address']}")
                return data
            except Exception as e:
                logger.error(f"Error inicializando wallet en WDK: {e}")

        # Fallback a Web3.py estándar
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
            
        return {
            "address": self.account.address,
            "private_key": self.account._private_key.hex() if hasattr(self.account, '_private_key') else None
        }

    def get_balance(self, address=None):
        """Obtiene el balance de la wallet en ETH."""
        target_address = address or (self.account.address if self.account else None)
        if not target_address:
            return 0
            
        # Si WDK está activo, consultamos por ahí
        if self.wdk_active:
            try:
                resp = httpx.get(f"{self.wdk_url}/wallet/balance", params={"address": target_address})
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
        """Envía una transacción real usando WDK."""
        seed_phrase = os.getenv("AGENT_SEED_PHRASE")
        
        if not self.wdk_active:
            logger.warning("Intento de transacción real sin WDK activo. Abortando.")
            return None
            
        if not seed_phrase:
            logger.error("AGENT_SEED_PHRASE no configurada. No se puede firmar la transacción.")
            return None

        try:
            logger.info(f"Ejecutando envío WDK: {value_wei} Wei a {to} (AA={use_aa})")
            resp = httpx.post(f"{self.wdk_url}/wallet/send", json={
                "seedPhrase": seed_phrase,
                "to": to,
                "valueWei": str(value_wei),
                "useAA": use_aa
            }, timeout=30.0)
            
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
        """Despliega un contrato inteligente usando el microservicio WDK."""
        seed_phrase = os.getenv("AGENT_SEED_PHRASE")
        if not self.wdk_active or not seed_phrase:
            logger.warning("WDK no activo o falta seed phrase. Despliegue cancelado.")
            return None

        try:
            logger.info("Solicitando despliegue de contrato a WDK...")
            resp = httpx.post(f"{self.wdk_url}/contract/deploy", json={
                "seedPhrase": seed_phrase,
                "abi": abi,
                "bytecode": bytecode,
                "args": args or []
            }, timeout=60.0)
            
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
        """Ejecuta una función de escritura en un contrato inteligente."""
        seed_phrase = os.getenv("AGENT_SEED_PHRASE")
        if not self.wdk_active or not seed_phrase:
            logger.warning("WDK no activo o falta seed phrase. Llamada a contrato cancelada.")
            return None

        try:
            logger.info(f"Llamando a {method} en contrato {address} (AA={use_aa})...")
            resp = httpx.post(f"{self.wdk_url}/contract/call", json={
                "seedPhrase": seed_phrase,
                "address": address,
                "abi": abi,
                "method": method,
                "args": args or [],
                "value": str(value),
                "useAA": use_aa
            }, timeout=60.0)
            
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
            resp = httpx.get(f"{self.wdk_url}/contract/state", params=params, timeout=10.0)
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
            }, timeout=15.0)
            
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"Error en cotización WDK: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Fallo en comunicación con WDK para quote: {e}")
            return None

    def execute_swap(self, token_in, token_out, amount, use_aa=False):
        """Ejecuta un swap de tokens usando WDK."""
        seed_phrase = os.getenv("AGENT_SEED_PHRASE")
        if not self.wdk_active or not seed_phrase:
            logger.warning("WDK no activo o falta seed phrase. Swap cancelado.")
            return None

        try:
            logger.info(f"Ejecutando swap WDK: {amount} de {token_in} a {token_out} (AA={use_aa})")
            resp = httpx.post(f"{self.wdk_url}/swap/execute", json={
                "seedPhrase": seed_phrase,
                "tokenIn": token_in,
                "tokenOut": token_out,
                "amount": str(amount),
                "useAA": use_aa
            }, timeout=60.0)
            
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
