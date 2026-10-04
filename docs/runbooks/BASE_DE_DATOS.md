# Base de datos caída o lenta

**Síntomas:**

- `/ready` da 503 con `reason: database` (o `schema`);
- el worker no late;
- errores de timeout en los logs.

**Pasos:**

1. **`reason: schema`:** se desplegó código sin correr la migración. Corro `migrate` ([Despliegue](DESPLIEGUE.md)). No activo `DB_AUTO_MIGRATE`.
2. **`reason: database`:** reviso el contenedor o servicio `db` (`pg_isready`, disco y conexiones).
   - El balanceador ya saca las réplicas que no están listas.
   - La API corta en 5 s al conectar y en 15 s por sentencia, así que no se acumulan requests colgados.
3. **Si la base está lenta:** busco consultas largas con `pg_stat_activity`. No cancelo migraciones en curso.
4. **Si la base no vuelve o el volumen está dañado:** sigo [Respaldo y restauración](RESPALDO.md).
5. **Al volver:**
   - verifico `/ready` y el latido del worker;
   - verifico que los jobs pendientes bajen;
   - verifico que la cobertura se recupere.
