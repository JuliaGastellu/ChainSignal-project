import os

with open('api/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Paso 1
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "analizando_wallet", "estado": "completado", "detalle": f"Analizadas {metrics.total_transacciones} transacciones."})}\\n\\n\'',
    'msg1 = f"Analizadas {metrics.total_transacciones} transacciones."\n            yield f\'data: {json.dumps({"paso": "analizando_wallet", "estado": "completado", "detalle": msg1})}\\n\\n\''
)

# Paso 2
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "calculando_scores", "estado": "completado", "detalle": f"Riesgo: {scores_dict[\\'risk\\']}, Actividad: {scores_dict[\\'activity\\']}"})}\\n\\n\'',
    'msg2 = f"Riesgo: {scores_dict[\\'risk\\']}, Actividad: {scores_dict[\\'activity\\']}"\n            yield f\'data: {json.dumps({"paso": "calculando_scores", "estado": "completado", "detalle": msg2})}\\n\\n\''
)

# Paso 3
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "clasificando_perfil", "estado": "completado", "detalle": f"Perfil detectado: {perfil_crudo.tipo}"})}\\n\\n\'',
    'msg3 = f"Perfil detectado: {perfil_crudo.tipo}"\n            yield f\'data: {json.dumps({"paso": "clasificando_perfil", "estado": "completado", "detalle": msg3})}\\n\\n\''
)

# Paso 5
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "evaluando_decision", "estado": "completado", "detalle": f"Decisión: {decision[\\'decision\\']}", "data": decision})}\\n\\n\'',
    'msg5 = f"Decisión: {decision.get(\\'decision\\', \\'MONITOR\\')}"\n            yield f\'data: {json.dumps({"paso": "evaluando_decision", "estado": "completado", "detalle": msg5, "data": decision})}\\n\\n\''
)

# Paso 6.5
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "operacion_financiera", "estado": "iniciando", "detalle": f"Movilizando fondos de seguridad ({estrategia.cantidad_transferencia_wei} wei)..."})}\\n\\n\'',
    'msg65 = f"Movilizando fondos de seguridad ({estrategia.cantidad_transferencia_wei} wei)..."\n                    yield f\'data: {json.dumps({"paso": "operacion_financiera", "estado": "iniciando", "detalle": msg65})}\\n\\n\''
)

# Paso 6.2
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "operacion_swap", "estado": "iniciando", "detalle": f"Ejecutando swap preventivo ({decision_estrategia.token_in} -> {decision_estrategia.token_out})..."})}\\n\\n\'',
    'msg62 = f"Ejecutando swap preventivo ({decision_estrategia.token_in} -> {decision_estrategia.token_out})..."\n                    yield f\'data: {json.dumps({"paso": "operacion_swap", "estado": "iniciando", "detalle": msg62})}\\n\\n\''
)

# Paso 7
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "generando_contrato", "estado": "iniciando", "detalle": f"Creando código Solidity para {tipo_val}..."})}\\n\\n\'',
    'msg7 = f"Creando código Solidity para {tipo_val}..."\n                yield f\'data: {json.dumps({"paso": "generando_contrato", "estado": "iniciando", "detalle": msg7})}\\n\\n\''
)

# Paso 9
content = content.replace(
    'yield f\'data: {json.dumps({"paso": "deployando_contrato", "estado": "completado", "detalle": f"Desplegado en {desplegado.direccion}"})}\\n\\n\'',
    'msg9 = f"Desplegado en {desplegado.direccion}"\n                yield f\'data: {json.dumps({"paso": "deployando_contrato", "estado": "completado", "detalle": msg9})}\\n\\n\''
)


with open('api/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied.")
