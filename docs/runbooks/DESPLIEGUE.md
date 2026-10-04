# Despliegue y rollback

Uso este runbook para publicar una versión nueva del piloto o volver a la anterior.

## Antes

1. CI en verde para el commit que voy a desplegar.
2. Hago un respaldo manual ([Respaldo](RESPALDO.md)) y anoto su hash.
3. Reviso si la versión trae migraciones nuevas (`migrations/versions/`) y si tienen `downgrade`.

## Desplegar

```sh
export CHAINSIGNAL_VERSION=<commit>
docker compose -f deploy/compose.piloto.yml build
docker compose -f deploy/compose.piloto.yml run --rm migrate      # una sola vez
docker compose -f deploy/compose.piloto.yml up -d --scale api=2 --wait
```

Verifico:

- `GET /ready` da 200 a través de la interfaz;
- `python -m operacion.vida_worker` sale con 0 en el worker;
- en `/metrics`, `chainsignal_workers_alive` vale 1 o más y `jobs_oldest_pending_age_seconds` no crece.

Si una réplica no arranca, el log dice `EsquemaDesactualizado`: falta el paso de migración. No lo arreglo poniendo `DB_AUTO_MIGRATE=true`.

## Rollback

1. Vuelvo la imagen: `export CHAINSIGNAL_VERSION=<anterior>` y `up -d --scale api=2 --wait`.
2. Si la versión nueva migró y la anterior no entiende el esquema, la API anterior no va a arrancar (verifica head).
   - Si la migración es reversible: `docker compose -f deploy/compose.piloto.yml run --rm migrate alembic downgrade <revisión anterior>` y vuelvo al paso 1. Las migraciones de `0001` a `0008` tienen `downgrade` probado en CI (`downgrade base` y `upgrade head`).
   - Si no es reversible o perdí datos: restauro el respaldo previo al despliegue ([Respaldo](RESPALDO.md)). Pierdo lo escrito desde ese respaldo.
3. Anoto qué pasó, cuánto tardé y qué se perdió.
