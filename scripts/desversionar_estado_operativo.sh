#!/usr/bin/env sh
# Saco del índice de git el estado operativo local que versioné por error.
#
# Usa `git rm --cached`: los archivos quedan en mi disco, solo dejan de estar
# versionados en el próximo commit. No reescribe historial; lo ya publicado
# sigue en commits anteriores.
#
# Antes de aplicarlo preservé una copia verificada en ops_backup/2026-10-03/
# (ver SHA256SUMS). Por defecto solo simulo; para aplicar:
#   sh scripts/desversionar_estado_operativo.sh --aplicar
set -eu

cd "$(git rev-parse --show-toplevel)"

ARCHIVOS="
backend_log.txt
cache/used_payments.json
contratos_deployados.json
executions.json
health.json
health_check.json
storage/agent_budget.json
storage/learning_store.json
tracking.json
watched_wallets.json
"
PLANES=$(git ls-files 'storage/plans/*/plan.json')

if [ "${1:-}" = "--aplicar" ]; then
    # shellcheck disable=SC2086
    git rm --cached --ignore-unmatch -- $ARCHIVOS $PLANES
    echo "Listo. Reviso con 'git status' antes de confirmar."
else
    # shellcheck disable=SC2086
    git rm --cached --ignore-unmatch -n -- $ARCHIVOS $PLANES
    echo "Simulación: no cambié nada. Uso --aplicar para quitarlos del índice."
fi
