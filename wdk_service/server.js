const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const dotenv = require('dotenv');
const { ethers } = require('ethers');

// Cargar variables de entorno
dotenv.config({ path: '../.env' });
dotenv.config();

const app = express();
app.use(cors());
app.use(bodyParser.json());

const PORT = process.env.WDK_PORT || 3001;
const NETWORK = process.env.WDK_NETWORK || 'sepolia';
const RPC_URL = process.env.WDK_RPC_URL || 'https://rpc.sepolia.org';

// Clases del SDK (se cargarán dinámicamente)
let WalletAccountEvm, VeloraProtocolEvm, WalletAccountEvmErc4337;
let wdkInstance; // Para compatibilidad o lógica genérica

console.log(`--- Iniciando Microservicio WDK en red: ${NETWORK} ---`);

/**
 * Inicialización asíncrona de los módulos ESM de Tether
 */
async function initWDK() {
    try {
        // Al ser paquetes ESM puros, usamos import() dinámico
        const evmModule = await import('@tetherto/wdk-wallet-evm');
        const swapModule = await import('@tetherto/wdk-protocol-swap-velora-evm');
        const erc4337Module = await import('@tetherto/wdk-wallet-evm-erc-4337');

        WalletAccountEvm = evmModule.WalletAccountEvm;
        VeloraProtocolEvm = swapModule.default;
        WalletAccountEvmErc4337 = erc4337Module.WalletAccountEvmErc4337;

        console.log(`[EXITO] Módulos WDK cargados correctamente`);
    } catch (error) {
        console.error(`[ERROR] No se pudieron cargar los módulos WDK: ${error.message}`);
    }
}

/**
 * Función auxiliar para obtener una cuenta WDK
 */
async function getAccountForSeed(seed, useAA = false) {
    if (useAA) {
        return new WalletAccountEvmErc4337(seed, "0'/0/0", {
            chainId: NETWORK === 'mainnet' ? 1 : 11155111,
            provider: RPC_URL,
            bundlerUrl: process.env.WDK_BUNDLER_URL,
            paymasterUrl: process.env.WDK_PAYMASTER_URL
        });
    }
    return new WalletAccountEvm(seed, "0'/0/0", { provider: RPC_URL });
}

/**
 * Endpoint: Salud y estado del servicio
 */
app.get('/health', (req, res) => {
    // WalletAccountEvm es la variable que se asigna tras initWDK()
    res.json({
        estado: "activo",
        red: NETWORK,
        rpc: RPC_URL,
        sdk_cargado: !!WalletAccountEvm,
        mensaje: "Microservicio WDK de ChainSignal operativo"
    });
});

/**
 * Endpoint: Crear/Cargar Wallet
 */
app.post('/wallet/create', async (req, res) => {
    try {
        const { seedPhrase } = req.body;
        if (!seedPhrase) return res.status(400).json({ error: "seedPhrase requerida" });

        const account = await getAccountForSeed(seedPhrase);
        const address = await account.getAddress();

        console.log(`[OPERACION] Wallet obtenida: ${address}`);
        res.json({ address, status: "ok" });
    } catch (error) {
        console.error(`[ERROR] Error en wallet/create: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Endpoint: Consultar Balance
 */
app.get('/wallet/balance', async (req, res) => {
    try {
        const { address } = req.query;
        if (!address) return res.status(400).json({ error: "Dirección requerida" });

        // Usamos la instancia global o una temporal si es necesario
        // En WDK beta, getBalance se puede llamar desde la instancia o el account
        // Pero wdkInstance.getAccount('ethereum') requiere seed.
        // Usamos ethers directamente para el balance por dirección si no tenemos seed
        const provider = new ethers.JsonRpcProvider(RPC_URL);
        const balanceWei = await provider.getBalance(address);
        const balanceEth = ethers.formatEther(balanceWei);

        res.json({ address, balanceEth, balanceWei: balanceWei.toString() });
    } catch (error) {
        console.error(`[ERROR] Error en wallet/balance: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Endpoint: Enviar ETH
 */
app.post('/wallet/send', async (req, res) => {
    try {
        const { seedPhrase, to, valueWei, useAA } = req.body;
        if (!seedPhrase || !to || !valueWei) {
            return res.status(400).json({ error: "Faltan parámetros (seedPhrase, to, valueWei)" });
        }

        const account = await getAccountForSeed(seedPhrase, useAA);
        console.log(`[OPERACION] Enviando ${valueWei} Wei a ${to} (AA=${useAA || false})`);

        const tx = await account.transfer(to, BigInt(valueWei));

        console.log(`[EXITO] Transacción enviada: ${tx.hash}`);
        res.json({ hash: tx.hash, status: "enviada" });
    } catch (error) {
        console.error(`[ERROR] Fallo en wallet/send: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Endpoint: Cotizar Swap (Velora)
 */
app.post('/swap/quote', async (req, res) => {
    try {
        const { tokenIn, tokenOut, amount } = req.body;
        if (!tokenIn || !tokenOut || !amount) {
            return res.status(400).json({ error: "Faltan parámetros (tokenIn, tokenOut, amount)" });
        }

        const account = await getAccountForSeed(process.env.AGENT_SEED_PHRASE);
        const swapProtocol = new VeloraProtocolEvm(account, {
            swapMaxFee: BigInt(process.env.WDK_SWAP_MAX_FEE || "200000000000000")
        });

        const quote = await swapProtocol.quoteSwap({
            tokenIn,
            tokenOut,
            tokenInAmount: BigInt(amount)
        });

        res.json({
            fee: quote.fee.toString(),
            tokenInAmount: quote.tokenInAmount.toString(),
            tokenOutAmount: quote.tokenOutAmount.toString()
        });
    } catch (error) {
        console.error(`[ERROR] Fallo en swap/quote: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Endpoint: Ejecutar Swap (Velora)
 */
app.post('/swap/execute', async (req, res) => {
    try {
        const { seedPhrase, tokenIn, tokenOut, amount, useAA } = req.body;
        const seed = seedPhrase || process.env.AGENT_SEED_PHRASE;

        if (!seed || !tokenIn || !tokenOut || !amount) {
            return res.status(400).json({ error: "Faltan parámetros" });
        }

        const account = await getAccountForSeed(seed, useAA);
        const swapProtocol = new VeloraProtocolEvm(account, {
            swapMaxFee: BigInt(process.env.WDK_SWAP_MAX_FEE || "200000000000000")
        });

        const result = await swapProtocol.swap({
            tokenIn,
            tokenOut,
            tokenInAmount: BigInt(amount)
        });

        res.json({
            hash: result.hash,
            fee: result.fee.toString(),
            tokenInAmount: result.tokenInAmount.toString(),
            tokenOutAmount: result.tokenOutAmount.toString()
        });
    } catch (error) {
        console.error(`[ERROR] Fallo en swap/execute: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Endpoint: Desplegar Contrato
 */
app.post('/contract/deploy', async (req, res) => {
    try {
        const { seedPhrase, abi, bytecode, args } = req.body;
        if (!seedPhrase || !abi || !bytecode) {
            return res.status(400).json({ error: "Faltan parámetros para el despliegue" });
        }

        const provider = new ethers.JsonRpcProvider(RPC_URL);
        const wallet = ethers.HDNodeWallet.fromPhrase(seedPhrase.trim(), provider);
        const balance = await provider.getBalance(wallet.address);
        console.log(`[DEBUG] Dirección Deployer: ${wallet.address} (Saldo: ${ethers.formatEther(balance)} ETH)`);
        const factory = new ethers.ContractFactory(abi, bytecode, wallet);

        console.log(`[OPERACION] Desplegando contrato...`);
        const contract = await factory.deploy(...(args || []));
        await contract.waitForDeployment();

        const address = await contract.getAddress();
        console.log(`[EXITO] Contrato desplegado en: ${address}`);
        res.json({ address, hash: contract.deploymentTransaction().hash });
    } catch (error) {
        console.error(`[ERROR] Fallo en contract/deploy: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Endpoint: Llamar Contrato (Escritura)
 */
app.post('/contract/call', async (req, res) => {
    try {
        const { seedPhrase, address, abi, method, args, value, useAA } = req.body;
        if (!seedPhrase || !address || !abi || !method) {
            return res.status(400).json({ error: "Faltan parámetros para llamar al contrato" });
        }

        // Se instancia el provider aquí para poder verificar el código del contrato
        const provider = new ethers.JsonRpcProvider(RPC_URL);
        const account = await getAccountForSeed(seedPhrase, useAA);
        const contract = new ethers.Contract(address, abi, account);

        console.log(`[OPERACION] Ejecutando ${method} en ${address}...`);

        // Verificar que el contrato existe en la red
        const code = await provider.getCode(address);
        if (code === '0x' || code === '0x0') {
            throw new Error("El contrato no tiene código en esta dirección. Verifique la red o espere propagación.");
        }

        const overrides = {};
        if (value) overrides.value = BigInt(value);

        // Intento de estimación con fallback manual
        try {
            const estimate = await contract[method].estimateGas(...(args || []), overrides);
            overrides.gasLimit = (estimate * 130n) / 100n; // 30% de margen para Sepolia
        } catch (estimateError) {
            console.warn(`[WARN] No se pudo estimar gas: ${estimateError.message}`);
            overrides.gasLimit = 800000n; // Límite generoso
        }

        const tx = await contract[method](...(args || []), overrides);
        const receipt = await tx.wait();

        console.log(`[EXITO] Transacción confirmada: ${receipt.hash}`);
        res.json({ hash: receipt.hash, status: "confirmada" });
    } catch (error) {
        console.error(`[ERROR] Fallo en contract/call: ${error.message}`);
        res.status(500).json({ error: error.message, detail: error.code });
    }
});

/**
 * Endpoint: Consultar Contrato (Lectura)
 */
app.get('/contract/state', async (req, res) => {
    try {
        const { address, abi, method, args } = req.query;
        if (!address || !abi || !method) {
            return res.status(400).json({ error: "Faltan parámetros de consulta" });
        }

        const provider = new ethers.JsonRpcProvider(RPC_URL);
        const parsedAbi = JSON.parse(abi);
        const contract = new ethers.Contract(address, parsedAbi, provider);
        const parsedArgs = args ? JSON.parse(args) : [];

        const result = await contract[method](...parsedArgs);
        res.json({ result: result.toString() });
    } catch (error) {
        console.error(`[ERROR] Fallo en contract/state: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// SECCIÓN: Agent Skills — Habilidades nativas del agente accesibles via WDK
// Exponen las capacidades del toolkit como endpoints invocables por el motor
// de decisiones Python cuando la decisión es EXECUTE_ADVANCED.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Skill: Consultar Balance
 * Devuelve el balance en ETH de cualquier dirección sin necesidad de seed phrase.
 */
app.get('/skills/balance', async (req, res) => {
    try {
        const { address } = req.query;
        if (!address) {
            return res.status(400).json({ error: "Parámetro 'address' requerido" });
        }

        const provider = new ethers.JsonRpcProvider(RPC_URL);
        const balanceWei = await provider.getBalance(address);
        const balanceEth = ethers.formatEther(balanceWei);

        console.log(`[SKILL:balance] Dirección ${address} → ${balanceEth} ETH`);
        res.json({
            skill: "obtener_balance",
            address,
            balanceEth,
            balanceWei: balanceWei.toString(),
            red: NETWORK
        });
    } catch (error) {
        console.error(`[ERROR] Skill balance fallida: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Skill: Obtener Cotización de Swap
 * Devuelve el quote sin ejecutar la transacción.
 */
app.post('/skills/swap/quote', async (req, res) => {
    try {
        const { tokenIn, tokenOut, amount } = req.body;
        if (!tokenIn || !tokenOut || !amount) {
            return res.status(400).json({ error: "Faltan parámetros (tokenIn, tokenOut, amount)" });
        }

        if (!VeloraProtocolEvm) {
            return res.status(503).json({ error: "Módulo VeloraProtocolEvm no disponible. SDK no inicializado." });
        }

        const account = await getAccountForSeed(process.env.AGENT_SEED_PHRASE);
        const swapProtocol = new VeloraProtocolEvm(account, {
            swapMaxFee: BigInt(process.env.WDK_SWAP_MAX_FEE || "200000000000000")
        });

        const quote = await swapProtocol.quoteSwap({
            tokenIn,
            tokenOut,
            tokenInAmount: BigInt(amount)
        });

        console.log(`[SKILL:swap/quote] ${tokenIn} → ${tokenOut} | Out: ${quote.tokenOutAmount.toString()}`);
        res.json({
            skill: "obtener_cotizacion_swap",
            tokenIn,
            tokenOut,
            fee: quote.fee.toString(),
            tokenInAmount: quote.tokenInAmount.toString(),
            tokenOutAmount: quote.tokenOutAmount.toString()
        });
    } catch (error) {
        console.error(`[ERROR] Skill swap/quote fallida: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Skill: Ejecutar Swap
 * Ejecuta el intercambio usando la seed phrase del agente configurada en el entorno.
 */
app.post('/skills/swap/execute', async (req, res) => {
    try {
        const { tokenIn, tokenOut, amount, useAA } = req.body;
        const seed = process.env.AGENT_SEED_PHRASE;

        if (!tokenIn || !tokenOut || !amount) {
            return res.status(400).json({ error: "Faltan parámetros (tokenIn, tokenOut, amount)" });
        }

        if (!seed) {
            return res.status(400).json({ error: "AGENT_SEED_PHRASE no configurada en el entorno" });
        }

        if (!VeloraProtocolEvm) {
            return res.status(503).json({ error: "Módulo VeloraProtocolEvm no disponible. SDK no inicializado." });
        }

        const account = await getAccountForSeed(seed, useAA || false);
        const swapProtocol = new VeloraProtocolEvm(account, {
            swapMaxFee: BigInt(process.env.WDK_SWAP_MAX_FEE || "200000000000000")
        });

        const result = await swapProtocol.swap({
            tokenIn,
            tokenOut,
            tokenInAmount: BigInt(amount)
        });

        console.log(`[SKILL:swap/execute] Swap completado. Hash: ${result.hash}`);
        res.json({
            skill: "ejecutar_swap",
            hash: result.hash,
            fee: result.fee.toString(),
            tokenInAmount: result.tokenInAmount.toString(),
            tokenOutAmount: result.tokenOutAmount.toString()
        });
    } catch (error) {
        console.error(`[ERROR] Skill swap/execute fallida: ${error.message}`);
        res.status(500).json({ error: error.message });
    }
});

// Manejo de errores global
app.use((err, req, res, next) => {
    console.error(`[FATAL] Error no manejado: ${err.message}`);
    res.status(500).json({ error: "Error interno del servidor" });
});

// Inicio del servidor sincronizado con la carga del SDK
app.listen(PORT, async () => {
    await initWDK();
    console.log(`[INFO] Servidor WDK escuchando en el puerto ${PORT}`);
});

// Captura de rechazos de promesas
process.on('unhandledRejection', (reason, promise) => {
    console.error('[PROCESO] Unhandled Rejection at:', promise, 'reason:', reason);
});
