# Worker parado o jobs acumulados

**Síntomas:**

- el healthcheck del worker falla (`python -m operacion.vida_worker` sale con 1);
- `chainsignal_workers_alive` vale 0;
- `chainsignal_jobs_oldest_pending_age_seconds` crece.

**Pasos:**

1. Miro el log del worker. El latido guarda el tipo del último error (`worker_heartbeats.last_error`).
2. Si es la base, sigo [Base de datos](BASE_DE_DATOS.md).
3. Si el proceso está colgado o murió, lo reinicio: `docker compose -f deploy/compose.piloto.yml restart worker`.
   - Un job que quedó tomado no se pierde ni se duplica: lo retoma el próximo worker cuando vence su lease (`WORKER_LEASE_SECONDS`).
   - Lo ensayé: con un lease de 15 s, el job se completó a los 15,6 s, una vez.
4. Si los jobs crecen con el worker vivo, falta capacidad: levanto otro worker. Varios workers no se pisan, porque el reclamo es atómico y con lease.
5. Los jobs en `dead` agotaron sus intentos. Reviso su `last_error`. No los reactivo a mano: la próxima programación de la cuenta crea uno nuevo.
