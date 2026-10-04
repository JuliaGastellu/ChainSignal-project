"""Adaptador del microservicio WDK para el experimento testnet de ChainSignal."""

from loguru import logger

from infra.modo import exigir_escritura_experimental
from wallet_controller.wallet_agent import WalletAgent
from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado
from domain.modelos_transaccion import ResultadoTransaccion, EstadoContrato


class ServicioWDK:
    """Encapsulo la comunicación con el microservicio WDK.

    Traduzco entre los modelos de dominio y la interfaz de WalletAgent, y
    registro cada operación con sus parámetros y resultados.

    Cada método que firma exige CHAINSIGNAL_MODE=TESTNET_EXPERIMENT. Ya no
    fabrico éxitos simulados: si el WDK no responde o no devuelve hash, el
    resultado es un fallo y nunca un "éxito en modo simulación".
    """

    def __init__(self):
        self._agente = WalletAgent()

    @property
    def activo(self) -> bool:
        """Indica si el microservicio WDK está disponible."""
        return self._agente.wdk_active

    def desplegar_contrato(
        self,
        contrato: ContratoCompilado,
        args_constructor: list | None = None,
    ) -> ContratoDeplegado | None:
        """Despliego un contrato compilado en la red configurada.

        Args:
            contrato: Contrato con ABI y bytecode listo para desplegar.
            args_constructor: Argumentos del constructor.

        Returns:
            ContratoDeplegado con dirección y hash, o None si el WDK no lo desplegó.
        """
        exigir_escritura_experimental("desplegar_contrato")
        logger.info(
            "Requesting deployment of '{}' with args={}",
            contrato.name,
            args_constructor,
        )

        datos = self._agente.deploy_contract(
            contrato.abi,
            contrato.bytecode,
            args=args_constructor or [],
        )

        if not datos:
            logger.error(
                "Deployment of '{}' produced no response from WDK.", contrato.name
            )
            return None

        resultado = ContratoDeplegado(
            name=contrato.name,
            address=datos["address"],
            transaction_hash=datos["hash"],
            abi=contrato.abi,
        )
        logger.info(
            "Contract '{}' deployment submitted at {}. Hash: {}",
            resultado.name,
            resultado.address,
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
        """Ejecuto una función de escritura en un contrato desplegado.

        Args:
            contrato: Contrato desplegado con dirección y ABI.
            funcion: Nombre del método a invocar.
            args: Argumentos de la función.
            valor_wei: ETH a enviar con la transacción (en wei).

        Returns:
            ResultadoTransaccion con hash y estado.
        """
        exigir_escritura_experimental("llamar_contrato")
        logger.info(
            "Executing {}() in {} with args={}",
            funcion,
            contrato.address,
            args,
        )

        tx_hash = self._agente.call_contract(
            contrato.address,
            contrato.abi,
            funcion,
            args=args or [],
            value=valor_wei,
        )

        success = tx_hash is not None
        resultado = ResultadoTransaccion(
            transaction_hash=tx_hash or "",
            contract_address=contrato.address,
            function=funcion,
            success=success,
            detail="Transaction submitted; not confirmed." if success else "WDK did not return hash.",
        )
        logger.info(
            "{}() in {}: success={}, hash={}",
            funcion,
            contrato.address,
            success,
            tx_hash,
        )
        return resultado

    def leer_estado(
        self,
        contrato: ContratoDeplegado,
        campo: str,
        args: list | None = None,
    ) -> EstadoContrato:
        """Leo el valor de una variable o función view de un contrato.

        Args:
            contrato: Contrato desplegado con dirección y ABI.
            campo: Nombre de la variable o método view.
            args: Argumentos opcionales para funciones view.

        Returns:
            EstadoContrato con el valor leído.
        """
        logger.info("Reading '{}' from {}", campo, contrato.address)

        valor = self._agente.get_contract_state(
            contrato.address,
            contrato.abi,
            campo,
            args=args or [],
        )

        success = valor is not None
        resultado = EstadoContrato(
            contract_address=contrato.address,
            field=campo,
            value=valor,
            success=success,
            detail="Read completed." if success else "WDK did not return value.",
        )
        logger.info(
            "'{}' in {}: value={}",
            campo,
            contrato.address,
            valor,
        )
        return resultado

    def obtener_direccion_wallet(self) -> str | None:
        """Obtengo la dirección de la wallet que administra el WDK.

        Returns:
            La dirección, o None si el WDK no está activo.
        """
        if not self.activo:
            return None

        # create_agent_wallet devuelve la wallet actual si ya existe; exige el
        # modo experimental porque puede derivar o crear identidad.
        datos_wallet = self._agente.create_agent_wallet()
        direccion = datos_wallet.get("address")
        logger.info("Agent wallet address: {}", direccion)
        return direccion

    def consultar_balance(self, direccion: str | None = None) -> float | None:
        """Consulto el saldo en ETH de una dirección.
        Sin dirección, consulto la wallet propia del agente.

        Ya no devuelvo un saldo inventado fuera de producción: sin WDK activo
        respondo None.

        Args:
            direccion: Dirección a consultar. Opcional.

        Returns:
            El saldo en ETH, o None si no puedo consultarlo.
        """
        if not self.activo:
            return None

        balance = self._agente.get_balance(direccion)
        logger.info("Balance of {}: {} ETH", direccion or "agent", balance)
        return float(balance)

    def transferir_activo(
        self, direccion_destino: str, cantidad_wei: int, use_aa: bool = False
    ) -> ResultadoTransaccion:
        """Transfiero ETH desde la wallet del agente a un destino.

        Args:
            direccion_destino: Dirección receptora.
            cantidad_wei: Cantidad de ETH a enviar, en wei.

        Returns:
            ResultadoTransaccion con el hash de la operación.
        """
        exigir_escritura_experimental("transferir")
        logger.info(
            "Requesting transfer of {} wei to {}",
            cantidad_wei,
            direccion_destino,
        )

        tx_hash = self._agente.ejecutar_transaccion(direccion_destino, cantidad_wei)

        success = tx_hash is not None
        resultado = ResultadoTransaccion(
            transaction_hash=tx_hash or "",
            contract_address="",  # Transferencia nativa, no a contrato
            function="transferencia_nativa",
            success=success,
            detail="Transfer submitted; not confirmed." if success else "WDK did not transfer.",
        )
        logger.info(
            "Transfer to {}: success={}, hash={}",
            direccion_destino,
            success,
            tx_hash,
        )
        return resultado

    def obtener_cotizacion_swap(
        self, token_in: str, token_out: str, cantidad: int
    ) -> dict | None:
        """Obtengo una cotización de intercambio de tokens.

        Args:
            token_in: Dirección del token de entrada (o 0x... para el nativo si aplica).
            token_out: Dirección del token de salida.
            cantidad: Cantidad en unidades base de token_in.

        Returns:
            Dict con fee, tokenInAmount y tokenOutAmount, o None.
        """
        logger.info("Requesting quote: {} -> {} (amount: {})", token_in, token_out, cantidad)
        return self._agente.get_swap_quote(token_in, token_out, cantidad)

    def ejecutar_swap(
        self, token_in: str, token_out: str, cantidad: int, use_aa: bool = False
    ) -> ResultadoTransaccion:
        """Ejecuto un intercambio de tokens on-chain.

        Args:
            token_in: Token a vender.
            token_out: Token a comprar.
            cantidad: Cantidad a vender.
            use_aa: Si uso Account Abstraction.

        Returns:
            ResultadoTransaccion con hash y estado.
        """
        exigir_escritura_experimental("ejecutar_swap")
        logger.info("Requesting swap execution: {} -> {} (AA={})", token_in, token_out, use_aa)

        datos = self._agente.execute_swap(token_in, token_out, cantidad, use_aa)
        success = datos is not None

        resultado = ResultadoTransaccion(
            transaction_hash=datos["hash"] if success else "",
            contract_address="",
            function="swap_tokens",
            success=success,
            detail="Swap submitted; not confirmed." if success else "Failed to execute swap in WDK.",
        )
        return resultado
