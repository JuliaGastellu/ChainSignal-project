# Respaldo y restauración

Metas internas: RPO 1 h y RTO 4 h. No son un SLA. Lo ensayé con una base chica: dump en 0,4 s, restore en 1,6 s y 21 s de punta a punta. Con datos reales tengo que volver a medirlo.

## Respaldo

Programo un respaldo por hora (cron o el programador de la plataforma) y guardo los archivos fuera del host de la base:

```sh
python -m operacion.respaldo respaldar --proyecto <proyecto> --compose deploy/compose.piloto.yml \
  --salida respaldos/chainsignal-$(date -u +%Y%m%dT%H%M).dump
```

La salida trae segundos, bytes y sha256. Guardo el sha256 junto al archivo. Si una plataforma ofrece respaldo continuo de PostgreSQL (PITR), lo prefiero y uso este script como copia independiente.

Una vez por semana restauro el último respaldo en un entorno aparte, con el paso de restauración de abajo. Un respaldo que nunca restauré no cuenta.

## Restauración

1. Detengo la escritura: `docker compose -f deploy/compose.piloto.yml stop api worker web`.
2. Preparo una base vacía. Si el volumen está dañado, recreo el servicio `db` con un volumen nuevo. Nunca restauro encima de datos: el script se niega.
3. Verifico el sha256 del archivo.
4. Restauro:
   ```sh
   python -m operacion.respaldo restaurar --proyecto <proyecto> --compose deploy/compose.piloto.yml --entrada <archivo>
   python -m operacion.respaldo huella   --proyecto <proyecto> --compose deploy/compose.piloto.yml
   ```
5. Corro la migración (no hace nada si ya está en head) y levanto todo: `up -d --scale api=2 --wait`.
6. Compruebo:
   - la huella coincide con la del respaldo, si la tengo;
   - una persona inicia sesión;
   - los incidentes activos se ven;
   - el worker late.
7. Aviso a las organizaciones que todo lo posterior al respaldo se perdió y anoto el intervalo.
