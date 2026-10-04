# Mi auditoría de ChainSignal

Revisión: 3 de octubre de 2026.

## Mi conclusión

Encuentro una base aprovechable para monitoreo on-chain, pero todavía no considero que esté lista para operar dinero de clientes ni salir al mercado como producto autónomo. Mi decisión es evolucionar hacia monitoreo de posiciones DeFi, alertas con evidencia y seguimiento por organización. Después evalúo propuestas simuladas con aprobación humana.

## Mi alcance y sus límites

Revisé el checkout local asociado a JuliaGastellu/ChainSignal-project: backend, ingestión, features, perfiles, decisiones, contratos de plantilla, ejecución, persistencia, frontend, pruebas y despliegue. Incluí cambios sin confirmar; no equiparo este estado con la rama pública actual.

Contrasté la revisión anterior de agosto con el código. Preservé una copia local de la documentación antes de actualizarla. No ejecuté transacciones, no usé secretos reales, no comprobé el servicio remoto y no hice una auditoría criptográfica de dependencias o historial completo de Git. Distingo defectos estáticos, comportamiento comprobado e hipótesis de negocio.

## Mi verificación

| Comprobación | Resultado que obtuve | Interpretación |
|---|---|---|
| npm run build | Pasó; 1668 módulos; JS principal de 346,40 kB | Puedo generar el bundle, pero no certifica tipos o flujos |
| npm test | 1 prueba aprobada | Solo compara true con true |
| npm run lint | 45 errores y 9 advertencias | Tengo deuda de tipos y hooks |
| tsc -p tsconfig.app.json --noEmit | 6 errores | Vite no exige que TypeScript pase |
| node --check wdk_service/server.js | Pasó | Solo comprobé sintaxis |
| Python: features, perfiles, estrategia, configuración y protección | 31 pruebas aprobadas, 1 advertencia | Comprobé esas reglas aisladas |
| Python: recolección de toda la suite | 58 pruebas recolectadas; 7 errores por falta de sqlalchemy | No declaro aprobada la suite completa |

Aislé Python con red bloqueada, dotenv deshabilitado, variables ficticias y directorio temporal. No alteré estado operativo existente. Build y tests frontend pasaron después de resolver la restricción inicial de lectura del entorno.

En el entorno virtual también falta openai. SQLAlchemy está declarado pero no instalado; openai y pydantic-settings se importan directamente pero no figuran como dependencias directas. Diferencio entorno desactualizado de manifiesto incompleto.

## Las mejoras que ya encuentro

| Tema antiguo | Estado actual que observé | Límite pendiente |
|---|---|---|
| Destino por defecto a quema | settings exige destino y rechaza null/burn | Falta validar formato, red y autorización |
| Ejecución forzada de todos los casos | Existe NO_ACTION y el overlay respeta decisiones terminales | Persisten dos motores distintos |
| Saldo compartido como presupuesto individual | get_effective_balance_eth usa la fila propia | Sigue custodia compartida sin identidad ni reservas atómicas |
| Servicio de firma abierto | WDK exige X-WDK-Token salvo /health y no publica puerto en Compose | Token compartido y permisos amplios |
| Seed en JSON por operación | Los métodos principales ya no la transmiten | API y WDK siguen recibiendo el mismo .env; Python puede leerla |
| Imports faltantes del ejecutor | asyncio y logger están presentes | Sigue evitando ExecutionGuard |
| Estado solo en JSON | Planes, presupuestos e historial usan SQLAlchemy | Tracking, watch queue y aprendizaje siguen locales |
| Carrera del mismo plan nuevo | try_claim_plan usa clave única y tiene tests | No cubre toda intención económica ni reintentos |

## Mis hallazgos

Uso P0 para bloqueos antes de exponer operaciones con fondos; P1 para condiciones previas a un piloto comercial; P2 para mejoras posteriores. Una ruta alcanzable no demuestra que haya ocurrido un ataque.

| ID | Prioridad | Evidencia que encontré | Consecuencia y corrección que propongo |
|---|---|---|---|
| A01 | P0 | api/main.py: run_agent_stream y aliases; AgentService._run_stream | GET público entra al pipeline que puede ejecutar. Separo análisis de escritura; GET solo observa |
| A02 | P0 | GuardianAgentLoop; AgentExecutor.execute | Invoca WalletAgent sin guard ni presupuesto individual. Retiro esa escritura del runtime comercial |
| A03 | P0 | _execute_with_esl; ExecutionGuard.validate_plan | simulation_success depende de APP_ENV != production. No hay simulación real que autorice producción. Mantengo lectura y después exijo evidencia verificable |
| A04 | P0 | ExecutionRunner.run/_verify_post_state; WDK /wallet/send | El runner marca COMPLETED tras leer saldo; captura fallos de verificación; send devuelve hash antes de confirmar. Separo envío, confirmación y resultado |
| A05 | P0 | ExecutionPlan.generate_fingerprint | Incluye bloque y riesgo, y ordena acciones. Cambia entre bloques y pierde orden del lote. Diseño identidad económica con cadena, cuenta y acciones ordenadas |
| A06 | P0 | PersistenceManager.try_claim_plan | FAILED/ABORTED se reclaman mediante lectura y actualización sin comparación atómica. Reconcilio antes de reintentar y uso transiciones condicionales |
| A07 | P0 | AgentBudgetService.verify_and_fund | Verifico destino y valor pero no vinculo remitente/wallet con usuario autenticado. Retiro depósitos; una futura versión exige intención y atribución |
| A08 | P0 | AgentBudgetService.consume; modelos DB | Float, saldo truncado a cero y falta de reserva atómica permiten contabilidad inconsistente. Uso unidades enteras y ledger si recupero capital |
| A09 | P0 | _run_runner_stream y _execute_with_esl | Espero task pero no propago booleano; contabilizo valor planeado aunque falle. Registro solo efectos reconciliados |
| A10 | P0 | AgentExecutor.execute | Un hash se vuelve confirmed y falta de respuesta puede aparecer simulated. Centralizo modos y nunca convierto error real en éxito simulado |
| A11 | P1 | Etherscan.chainid=1; RPC, WDK y MetaMask Sepolia | Mezclo redes. Pongo chain_id en todo y valido proveedor/mercado |
| A12 | P1 | ClienteEtherscan | Una página de 200 tx; errores como None/[]/cero. Distingo vacío, parcial, caído y fresco; agrego cursor y retries |
| A13 | P1 | ExtractorFeatures | Edad sobre muestra truncada, tokens por símbolo y diversidad sin entropía estándar. Explicito ventana y uso red+contrato |
| A14 | P1 | Scorer, SignalDetector, ProtocolIntelService | Salidas llamadas acumulación, interacción llamada liquidez y diversidad llamada spike. Reemplazo inferencias por evidencia real de posición |
| A15 | P1 | LearningStore.summary; StrategyEngine.select | Contar éxitos no prueba aprendizaje; sesgo sin denominador económico. Lo llamo historial y quito adaptación no evaluada |
| A16 | P1 | ReasoningEngine.decide/_llm_reasoning | Reglas eligen acción; el modelo redacta explicación. Lo mantengo opcional y sin escritura |
| A17 | P1 | require_api_key; historial, colas y SSE públicos | Clave global sin organizaciones ni ownership. Autorizo también lecturas privadas y streams |
| A18 | P1 | Index, OperationsCenter y paneles: fetch | No envían X-API-Key y algunos ignoran response.ok. Integro sesión y errores; no pongo secreto global en VITE_* |
| A19 | P1 | AgentFundingPanel | Campo budget vs agent_budget, wallet=agentWallet y confirmación por delta global. Retiro funding del MVP |
| A20 | P1 | /agent/state y AgentHeroSection | PnL como valor movido menos gasto no representa rendimiento. Uso métricas operativas verificables |
| A21 | P1 | Contratos de plantilla y _execute_with_esl | Desplegar no protege wallet externa; constructors necesitan argumentos pero envío None. Retiro despliegue por score |
| A22 | P1 | Lifespan API y ambos loops | Workers HTTP pueden multiplicar loops; locks de wallet observada no protegen firmante compartido. Extraigo worker y jobs persistentes |
| A23 | P1 | Tracking, QueueManager, LearningStore y EventBus | Estado local y SSE sin replay. Persisto eventos, cursor y límites por organización |
| A24 | P1 | infra/db.py | Producción puede usar SQLite temporal; create_all no migra. Exijo Postgres y migraciones con restore |
| A25 | P1 | Dockerfile, Compose y render.yaml | CMD api.server inexistente; web legacy con --reload; Render solo API. Diseño despliegue completo |
| A26 | P1 | requirements; WDK latest; orquestación externa no-op | Instalación no reproducible y dependencias sin valor comprobado. Declaro imports directos y fijo versiones probadas |
| A27 | P1 | Vitest, lint, tsc y test_x402 | Prueba trivial, hook condicional, tipos inválidos y tests premium frente a report gratuito. CI y pruebas de comportamiento |
| A28 | P1 | git ls-files de logs/cache/storage | Versiono estado operativo; ignore no lo desversiona. Inventario, preservación y bajas revisables |
| A29 | P1 | Documentación y manifiestos | No encuentro LICENSE raíz ni política de seguridad; existía crédito de herramienta en plan. Documento en mi voz y dejo licencia como decisión explícita |
| A30 | P1 | API y streams | No encuentro cuotas comerciales ni límites completos de clientes/eventos. Rate limits, paginación, timeouts y backpressure |
| A31 | P2 | UI duplicada y tipos laxos | Mantenimiento costoso. Una app con cliente API tipado y componentes por tarea |
| A32 | P2 | Onboarding, analytics y billing | Falta recorrido comercial y entitlement. Instrumento activación y cobro después de validar piloto |

## Qué conservaría

Conservaría FastAPI, React/Vite, PostgreSQL, separación inicial de módulos y tests de seguridad existentes. Aprovecharía trazabilidad de decisiones y componentes visuales que expliquen posiciones e incidentes.

Mantendría experimentos testnet fuera del runtime comercial. No necesito reescribir todo ni aumentar infraestructura para lanzar un monitoreo útil.

## Qué no certifico

No certifico mainnet, precisión predictiva, rentabilidad, conformidad legal, disponibilidad remota ni ausencia de secretos en todo el historial. Tampoco doy por demostrada demanda o voluntad de pago.

Primero cierro escritura y preparo entorno reproducible; después identidad y datos; luego alertas, experiencia y pilotos pagos. Condiciono propuestas con firma humana a demanda y seguridad demostradas.
