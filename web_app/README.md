# Mi interfaz de ChainSignal

Construyo con React, TypeScript y Vite, conectados a FastAPI por HTTP y SSE.

## Mi estado

La interfaz es el producto de E06: landing, alta, demo sintética aislada y una app con Resumen, Posiciones, Incidentes y Configuración. Solo lee posiciones de Aave V3 en Ethereum mainnet; no firma ni mueve fondos. Describo el recorrido, los estados y las pruebas en [mi experiencia](../docs/EXPERIENCIA.md).

## Cómo trabajo

```powershell
npm ci
npm run dev        # http://localhost:8081, con proxy a la API en 127.0.0.1:8001
npm run typecheck
npm run lint
npm test           # Vitest
npm run build
npm run e2e        # Playwright: levanta API y worker aislados y vite preview
```

Uso Node 20 o superior y `package-lock.json` como único lockfile. Para `npm run e2e` defino `CHAINSIGNAL_PYTHON` con el Python 3.11 del proyecto. Fijé Playwright en 1.63.0 para usar el Chromium 1243 que ya tengo instalado.

La sesión viaja en una cookie HttpOnly que el código no lee, y `src/lib/api.ts` agrega el token CSRF en las mutaciones. Sin VITE_API_BASE uso el mismo origen: el proxy de Vite (`dev` y `preview`) reenvía `/health`, `/auth`, `/demo`, `/orgs` e `/invitations` a la API local o a `CHAINSIGNAL_API_PROXY`. Nunca lo apunto a producción.

No pongo secretos en VITE_*. Una prueba de Vitest falla si el código usa una variable VITE_* distinta de `VITE_API_BASE`.

## Estructura

- `src/lib/`: cliente tipado (`api.ts`, `tipos.ts`), consultas y reintentos (`consultas.ts`), formatos y estados (`formato.ts`, `calidad.ts`) y sesión y rol (`sesion.ts`).
- `src/hooks/useEventosOrg.ts`: eventos en vivo con reconexión.
- `src/components/`: `AppLayout`, `RequireSession` y estados comunes (`Estados.tsx`).
- `src/pages/`: `Landing`, `Registro`, `Login` y `app/` con las cuatro secciones y sus detalles.
- `e2e/`: escenarios de Playwright.

## Mi verificación

Al 4 de octubre de 2026:

- `typecheck` sin errores;
- `lint` sin errores, con 7 advertencias en `ui/` del scaffolding;
- 38 pruebas de Vitest en 9 archivos;
- build correcto;
- 10 escenarios E2E (9 de escritorio y 1 móvil).
