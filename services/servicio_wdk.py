"""Adaptador del microservicio WDK para el agente ChainSignal."""

import os
from loguru import logger

from wallet_controller.wallet_agent import WalletAgent
from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado
from domain.modelos_transaccion import ResultadoTransaccion, EstadoContrato


class ServicioWDK:
    """Encapsula la comunicación con el microservicio WDK.

    Traduce entre los modelos del dominio y la interfaz de WalletAgent,
    registrando cada operación con sus parámetros y resultado.
    """

    def __init__(self):
        self._agente = WalletAgent()
        self.modo_simulacion = os.getenv("APP_ENV", "local") != "production"

    @property
    def activo(self) -> bool:
        """Indica si el microservicio WDK está disponible."""
        return self._agente.wdk_active

    def desplegar_contrato(
        self,
        contrato: ContratoCompilado,
        args_constructor: list | None = None,
    ) -> ContratoDeplegado | None:
        """Despliega un contrato compilado en la red configurada.

        Args:
            contrato: Contrato con ABI y bytecode listos para despliegue.
            args_constructor: Argumentos para el constructor del contrato.

        Returns:
            ContratoDeplegado con dirección y hash, o None si el WDK no está activo.
        """
        logger.info(
            "Solicitando despliegue de '{}' con args={}",
            contrato.nombre,
            args_constructor,
        )

        if self.modo_simulacion:
            logger.info("MODO SIMULACION: Simulando despliegue de '{}'", contrato.nombre)
            return ContratoDeplegado(
                nombre=contrato.nombre,
                direccion="0xSimulatedAddress" + contrato.nombre.lower()[:20].ljust(20, '0'),
                transaction_hash="0xSimulatedHash" + contrato.nombre.lower().ljust(49, '0'),
                abi=contrato.abi,
            )

        datos = self._agente.deploy_contract(
            contrato.abi,
            contrato.bytecode,
            args=args_constructor or [],
        )

        if not datos:
            logger.error(
                "El despliegue de '{}' no produjo respuesta del WDK.", contrato.nombre
            )
            return None

        resultado = ContratoDeplegado(
            nombre=contrato.nombre,
            direccion=datos["address"],
            transaction_hash=datos["hash"],
            abi=contrato.abi,
        )
        logger.info(
            "Contrato '{}' desplegado en {}. Hash: {}",
            resultado.nombre,
            resultado.direccion,
            resultado.transaction_hash,
        )
        return resultado

    def ejecutar_funcion(
        self,
        contrato: ContratoDeplegado,
        funcion: str,
        args: list | None = None,
        valor_wei: int = 0,
    ) -> ResultadoTransaccion:
        """Ejecuta una función de escritura en un contrato desplegado.

        Args:
            contrato: Contrato desplegado con dirección y ABI.
            funcion: Nombre del método a invocar.
            args: Argumentos de la función.
            valor_wei: ETH a enviar con la transacción (en wei).

        Returns:
            ResultadoTransaccion con hash y estado.
        """
        logger.info(
            "Ejecutando {}() en {} con args={}",
            funcion,
            contrato.direccion,
            args,
        )

        if self.modo_simulacion:
            logger.info("MODO SIMULACION: Simulando ejecución de {}()", funcion)
            return ResultadoTransaccion(
                transaction_hash="0xSimulatedExecHash" + funcion.lower()[:45].ljust(45, '0'),
                contrato_direccion=contrato.direccion,
                funcion=funcion,
                exitoso=True,
                detalle="Transacción ejecutada en MODO SIMULACIÓN.",
            )

        tx_hash = self._agente.call_contract(
            contrato.direccion,
            contrato.abi,
            funcion,
            args=args or [],
            value=valor_wei,
        )

        exitoso = tx_hash is not None
        resultado = ResultadoTransaccion(
            transaction_hash=tx_hash or "",
            contrato_direccion=contrato.direccion,
            funcion=funcion,
            exitoso=exitoso,
            detalle="Transacción enviada." if exitoso else "El WDK no devolvió hash.",
        )
        logger.info(
            "{}() en {}: exitoso={}, hash={}",
            funcion,
            contrato.direccion,
            exitoso,
            tx_hash,
        )
        return resultado

    def leer_estado(
        self,
        contrato: ContratoDeplegado,
        campo: str,
        args: list | None = None,
    ) -> EstadoContrato:
        """Lee el valor de una variable o función view de un contrato.

        Args:
            contrato: Contrato desplegado con dirección y ABI.
            campo: Nombre de la variable o método view.
            args: Argumentos opcionales para funciones view.

        Returns:
            EstadoContrato con el valor leído.
        """
        logger.info("Leyendo '{}' de {}", campo, contrato.direccion)

        valor = self._agente.get_contract_state(
            contrato.direccion,
            contrato.abi,
            campo,
            args=args or [],
        )

        exitoso = valor is not None
        resultado = EstadoContrato(
            contrato_direccion=contrato.direccion,
            campo=campo,
            valor=valor,
            exitoso=exitoso,
            detalle="Lectura completada." if exitoso else "El WDK no devolvió valor.",
        )
        logger.info(
            "'{}' en {}: valor={}",
            campo,
            contrato.direccion,
            valor,
        )
        return resultado

    def obtener_direccion_wallet(self) -> str | None:
        """Obtiene la dirección de la wallet gestionada por el WDK.

        Returns:
            La dirección de la wallet o None si no hay WDK activo.
        """
        if not self.activo:
            return None

        # create_agent_wallet devuelve la wallet actual si ya existe
        datos_wallet = self._agente.create_agent_wallet()
        direccion = datos_wallet.get("address")
        logger.info("Dirección de wallet del agente: {}", direccion)
        return direccion

    def consultar_balance(self, direccion: str | None = None) -> float | None:
        """Consulta el balance en ETH de una dirección.
        Si no se provee dirección, consulta la wallet del propio agente.

        Args:
            direccion: Dirección a consultar. Opcional.

        Returns:
            El balance en ETH o None si hay error.
        """
        if self.modo_simulacion:
            return 10.5  # Balance simulado siempre positivo para permitir tests

        if not self.activo:
            return None

        balance = self._agente.get_balance(direccion)
        logger.info("Balance de {}: {} ETH", direccion or "agente", balance)
        return float(balance)

    def transferir_activo(
        self, direccion_destino: str, cantidad_wei: int, use_aa: bool = False
    ) -> ResultadoTransaccion:
        """Transfiere ETH desde la wallet del agente hacia un destino.

        Args:
            direccion_destino: Dirección receptora.
            cantidad_wei: Cantidad de ETH en wei a enviar.

        Returns:
            ResultadoTransaccion con el hash de la operación.
        """
        logger.info(
            "Solicitando transferencia de {} wei a {}",
            cantidad_wei,
            direccion_destino,
        )

        if self.modo_simulacion:
            logger.info("MODO SIMULACION: Simulando transferencia a {}", direccion_destino)
            return ResultadoTransaccion(
                transaction_hash="0xSimulatedTransferHash00000000000000000000000000000000000000000",
                contrato_direccion="",
                funcion="transferencia_nativa",
                exitoso=True,
                detalle="Transferencia enviada en MODO SIMULACIÓN.",
            )

        tx_hash = self._agente.ejecutar_transaccion(direccion_destino, cantidad_wei)

        exitoso = tx_hash is not None
        resultado = ResultadoTransaccion(
            transaction_hash=tx_hash or "",
            contrato_direccion="",  # Es una tranferencia nativa, no a contrato
            funcion="transferencia_nativa",
            exitoso=exitoso,
            detalle="Transferencia enviada." if exitoso else "El WDK no transfirió.",
        )
        logger.info(
            "Transferencia a {}: exitoso={}, hash={}",
            direccion_destino,
            exitoso,
            tx_hash,
        )
        return resultado

    def obtener_cotizacion_swap(
        self, token_in: str, token_out: str, cantidad: int
    ) -> dict | None:
        """Obtiene una cotización para intercambiar tokens.

        Args:
            token_in: Dirección del token de entrada (o 0x... para nativo si aplica).
            token_out: Dirección del token de salida.
            cantidad: Cantidad en unidades base del token_in.

        Returns:
            Dict con fee, tokenInAmount y tokenOutAmount, o None.
        """
        logger.info("Solicitando cotización: {} -> {} (monto: {})", token_in, token_out, cantidad)
        return self._agente.get_swap_quote(token_in, token_out, cantidad)

    def ejecutar_swap(
        self, token_in: str, token_out: str, cantidad: int, use_aa: bool = False
    ) -> ResultadoTransaccion:
        """Ejecuta un intercambio de tokens on-chain.

        Args:
            token_in: Token a vender.
            token_out: Token a comprar.
            cantidad: Cantidad a vender.
            use_aa: Si se debe usar Account Abstraction.

        Returns:
            ResultadoTransaccion con el hash y estado.
        """
        logger.info("Solicitando ejecución de swap: {} -> {} (AA={})", token_in, token_out, use_aa)

        if self.modo_simulacion:
            logger.info("MODO SIMULACION: Simulando swap {} -> {}", token_in, token_out)
            return ResultadoTransaccion(
                transaction_hash="0xSimulatedSwapHash" + token_out.lower()[:44].ljust(44, '0'),
                contrato_direccion="",
                funcion="swap_tokens",
                exitoso=True,
                detalle="Swap ejecutado en MODO SIMULACIÓN.",
            )

        datos = self._agente.execute_swap(token_in, token_out, cantidad, use_aa)
        exitoso = datos is not None

        resultado = ResultadoTransaccion(
            transaction_hash=datos["hash"] if exitoso else "",
            contrato_direccion="",
            funcion="swap_tokens",
            exitoso=exitoso,
            detalle="Swap confirmado." if exitoso else "Fallo al ejecutar swap en WDK.",
        )
        return resultado

    # ─────────────────────────────────────────────────────────────────────────
    # WDK Agent Skills — Habilidades invocables cuando la decisión es EXECUTE_ADVANCED
    # ─────────────────────────────────────────────────────────────────────────

    def skill_obtener_balance(self, direccion: str) -> dict:
        """Skill: Consulta el balance de una dirección via el endpoint /skills/balance.

        Difiere de consultar_balance() en que siempre pasamos una dirección explícita
        y devolvemos el dict completo del skill (balanceEth, balanceWei, red).

        Args:
            direccion: Dirección Ethereum a consultar.

        Returns:
            Dict con claves 'balanceEth', 'balanceWei', 'red', o dict vacío en error.
        """
        logger.info("Skill activo: obtener_balance para {}", direccion)

        if self.modo_simulacion:
            logger.info("MODO SIMULACION: Skill balance simulado para {}", direccion)
            return {
                "skill": "obtener_balance",
                "address": direccion,
                "balanceEth": "10.5",
                "balanceWei": "10500000000000000000",
                "red": "simulacion",
            }

        try:
            import httpx
            resp = httpx.get(
                f"{self._agente.wdk_url}/skills/balance",
                params={"address": direccion},
                timeout=10.0,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Skill balance retornó HTTP {}: {}", resp.status_code, resp.text)
            return {}
        except Exception as error:
            logger.error("Fallo en skill obtener_balance: {}", error)
            return {}

    def skill_obtener_cotizacion(
        self, token_in: str, token_out: str, cantidad: int
    ) -> dict:
        """Skill: Obtiene cotización de swap sin ejecutarla via /skills/swap/quote.

        Args:
            token_in: Token a vender (dirección o símbolo 'ETH').
            token_out: Token a comprar (dirección).
            cantidad: Cantidad en wei del token de entrada.

        Returns:
            Dict con 'fee', 'tokenInAmount', 'tokenOutAmount', o dict vacío en error.
        """
        logger.info("Skill activo: obtener_cotizacion {} -> {}", token_in, token_out)

        if self.modo_simulacion:
            logger.info("MODO SIMULACION: Skill cotización simulada")
            return {
                "skill": "obtener_cotizacion_swap",
                "tokenIn": token_in,
                "tokenOut": token_out,
                "fee": "50000000000000",
                "tokenInAmount": str(cantidad),
                "tokenOutAmount": str(int(cantidad * 0.98)),
            }

        try:
            import httpx
            resp = httpx.post(
                f"{self._agente.wdk_url}/skills/swap/quote",
                json={"tokenIn": token_in, "tokenOut": token_out, "amount": str(cantidad)},
                timeout=15.0,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Skill cotización retornó HTTP {}: {}", resp.status_code, resp.text)
            return {}
        except Exception as error:
            logger.error("Fallo en skill obtener_cotizacion: {}", error)
            return {}

    def skill_ejecutar_swap(
        self, token_in: str, token_out: str, cantidad: int, use_aa: bool = False
    ) -> ResultadoTransaccion:
        """Skill: Ejecuta un swap via el endpoint dedicado /skills/swap/execute.

        A diferencia de ejecutar_swap(), este skill siempre usa la seed phrase
        configurada en el entorno del gateway, sin pasarla desde Python.

        Args:
            token_in: Token a vender.
            token_out: Token a comprar.
            cantidad: Cantidad en wei.
            use_aa: Si se debe usar Account Abstraction.

        Returns:
            ResultadoTransaccion con hash y estado.
        """
        logger.info("Skill activo: ejecutar_swap {} -> {} (AA={})", token_in, token_out, use_aa)

        if self.modo_simulacion:
            logger.info("MODO SIMULACION: Skill swap ejecutado en simulación")
            return ResultadoTransaccion(
                transaction_hash="0xSkillSwapSimulado" + token_out.lower()[:45].ljust(45, "0"),
                contrato_direccion="",
                funcion="skill_swap",
                exitoso=True,
                detalle="Skill swap ejecutado en MODO SIMULACIÓN.",
            )

        try:
            import httpx
            resp = httpx.post(
                f"{self._agente.wdk_url}/skills/swap/execute",
                json={
                    "tokenIn": token_in,
                    "tokenOut": token_out,
                    "amount": str(cantidad),
                    "useAA": use_aa,
                },
                timeout=60.0,
            )
            if resp.status_code == 200:
                datos = resp.json()
                return ResultadoTransaccion(
                    transaction_hash=datos.get("hash", ""),
                    contrato_direccion="",
                    funcion="skill_swap",
                    exitoso=True,
                    detalle="Skill swap completado via endpoint dedicado.",
                )
            logger.error("Skill swap/execute retornó HTTP {}: {}", resp.status_code, resp.text)
            return ResultadoTransaccion(
                transaction_hash="",
                contrato_direccion="",
                funcion="skill_swap",
                exitoso=False,
                detalle=f"Error en gateway: {resp.text}",
            )
        except Exception as error:
            logger.error("Fallo en skill ejecutar_swap: {}", error)
            return ResultadoTransaccion(
                transaction_hash="",
                contrato_direccion="",
                funcion="skill_swap",
                exitoso=False,
                detalle=f"Excepción al invocar skill: {error}",
            )

