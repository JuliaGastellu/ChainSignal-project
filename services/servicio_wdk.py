"""Adaptador del microservicio WDK para el agente ChainSignal."""

import os
from loguru import logger

from wallet_controller.wallet_agent import WalletAgent
from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado
from domain.modelos_transaccion import ResultadoTransaccion, EstadoContrato


class ServicioWDK:
    """Encapsulates communication with the WDK microservice.

    Translates between domain models and the WalletAgent interface,
    logging each operation with its parameters and results.
    """

    def __init__(self):
        self._agente = WalletAgent()
        self.modo_simulacion = os.getenv("APP_ENV", "local") != "production"
        if self.modo_simulacion:
            logger.warning("[WARNING] WDK running in SIMULATION MODE (APP_ENV={})", os.getenv("APP_ENV", "local"))

    @property
    def activo(self) -> bool:
        """Indicates if the WDK microservice is available."""
        return self._agente.wdk_active

    def desplegar_contrato(
        self,
        contrato: ContratoCompilado,
        args_constructor: list | None = None,
    ) -> ContratoDeplegado | None:
        """Deploys a compiled contract on the configured network.

        Args:
            contrato: Contract with ABI and bytecode ready for deployment.
            args_constructor: Arguments for the contract constructor.

        Returns:
            ContratoDeplegado with address and hash, or None if WDK is inactive.
        """
        logger.info(
            "Requesting deployment of '{}' with args={}",
            contrato.name,
            args_constructor,
        )

        if self.modo_simulacion:
            logger.info("SIMULATION MODE: Simulating deployment of '{}'", contrato.name)
            return ContratoDeplegado(
                name=contrato.name,
                address="0xSimulatedAddress" + contrato.name.lower()[:20].ljust(20, '0'),
                transaction_hash="0xSimulatedHash" + contrato.name.lower().ljust(49, '0'),
                abi=contrato.abi,
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
            "Contract '{}' deployed at {}. Hash: {}",
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
        """Executes a write function on a deployed contract.

        Args:
            contrato: Deployed contract with address and ABI.
            funcion: Name of the method to invoke.
            args: Function arguments.
            valor_wei: ETH to send with the transaction (in wei).

        Returns:
            ResultadoTransaccion with hash and status.
        """
        logger.info(
            "Executing {}() in {} with args={}",
            funcion,
            contrato.address,
            args,
        )

        if self.modo_simulacion:
            logger.info("SIMULATION MODE: Simulating execution of {}()", funcion)
            return ResultadoTransaccion(
                transaction_hash="0xSimulatedExecHash" + funcion.lower()[:45].ljust(45, '0'),
                contract_address=contrato.address,
                function=funcion,
                success=True,
                detail="Transaction executed in SIMULATION MODE.",
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
            detail="Transaction sent." if success else "WDK did not return hash.",
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
        """Reads the value of a view variable or function from a contract.

        Args:
            contrato: Deployed contract with address and ABI.
            campo: Name of the variable or view method.
            args: Optional arguments for view functions.

        Returns:
            EstadoContrato with the read value.
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
        """Obtains the address of the wallet managed by the WDK.

        Returns:
            The wallet address or None if no active WDK.
        """
        if not self.activo:
            return None

        # create_agent_wallet returns the current wallet if it already exists
        datos_wallet = self._agente.create_agent_wallet()
        direccion = datos_wallet.get("address")
        logger.info("Agent wallet address: {}", direccion)
        return direccion

    def consultar_balance(self, direccion: str | None = None) -> float | None:
        """Consults the ETH balance of an address.
        If no address is provided, consults the agent's own wallet.

        Args:
            direccion: Address to consult. Optional.

        Returns:
            The ETH balance or None if error.
        """
        if self.modo_simulacion:
            return 10.5  # Simulated balance always positive for tests

        if not self.activo:
            return None

        balance = self._agente.get_balance(direccion)
        logger.info("Balance of {}: {} ETH", direccion or "agent", balance)
        return float(balance)

    def transferir_activo(
        self, direccion_destino: str, cantidad_wei: int, use_aa: bool = False
    ) -> ResultadoTransaccion:
        """Transfers ETH from the agent wallet to a destination.

        Args:
            direccion_destino: Recipient address.
            cantidad_wei: Amount of ETH in wei to send.

        Returns:
            ResultadoTransaccion with the operation hash.
        """
        logger.info(
            "Requesting transfer of {} wei to {}",
            cantidad_wei,
            direccion_destino,
        )

        if self.modo_simulacion:
            logger.info("SIMULATION MODE: Simulating transfer to {}", direccion_destino)
            return ResultadoTransaccion(
                transaction_hash="0xSimulatedTransferHash00000000000000000000000000000000000000000",
                contract_address="",
                function="transferencia_nativa",
                success=True,
                detail="Transfer sent in SIMULATION MODE.",
            )

        tx_hash = self._agente.ejecutar_transaccion(direccion_destino, cantidad_wei)

        success = tx_hash is not None
        resultado = ResultadoTransaccion(
            transaction_hash=tx_hash or "",
            contract_address="",  # Native transfer, not to contract
            function="transferencia_nativa",
            success=success,
            detail="Transfer sent." if success else "WDK did not transfer.",
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
        """Obtains a quote for token exchange.

        Args:
            token_in: Input token address (or 0x... for native if applicable).
            token_out: Output token address.
            cantidad: Amount in base units of token_in.

        Returns:
            Dict with fee, tokenInAmount and tokenOutAmount, or None.
        """
        logger.info("Requesting quote: {} -> {} (amount: {})", token_in, token_out, cantidad)
        return self._agente.get_swap_quote(token_in, token_out, cantidad)

    def ejecutar_swap(
        self, token_in: str, token_out: str, cantidad: int, use_aa: bool = False
    ) -> ResultadoTransaccion:
        """Executes an on-chain token exchange.

        Args:
            token_in: Token to sell.
            token_out: Token to buy.
            cantidad: Amount to sell.
            use_aa: Whether to use Account Abstraction.

        Returns:
            ResultadoTransaccion with hash and status.
        """
        logger.info("Requesting swap execution: {} -> {} (AA={})", token_in, token_out, use_aa)

        if self.modo_simulacion:
            logger.info("SIMULATION MODE: Simulating swap {} -> {}", token_in, token_out)
            return ResultadoTransaccion(
                transaction_hash="0xSimulatedSwapHash" + token_out.lower()[:44].ljust(44, '0'),
                contract_address="",
                function="swap_tokens",
                success=True,
                detail="Swap executed in SIMULATION MODE.",
            )

        datos = self._agente.execute_swap(token_in, token_out, cantidad, use_aa)
        success = datos is not None

        resultado = ResultadoTransaccion(
            transaction_hash=datos["hash"] if success else "",
            contract_address="",
            function="swap_tokens",
            success=success,
            detail="Swap confirmed." if success else "Failed to execute swap in WDK.",
        )
        return resultado



