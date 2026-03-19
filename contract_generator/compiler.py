from loguru import logger

try:
    import solcx
except ImportError:
    logger.error("La librería py-solc-x no está instalada. Ejecute: pip install py-solc-x")
    raise

def instalar_solc_si_falta():
    """Verifica e instala la versión necesaria del compilador Solidity."""
    version = "0.8.20"
    try:
        if version not in solcx.get_installed_solc_versions():
            logger.info(f"Instalando solc v{version}...")
            solcx.install_solc(version)
        solcx.set_solc_version(version)
    except Exception as e:
        logger.error(f"Error instalando solc: {e}")
        raise RuntimeError(f"No se pudo preparar el compilador Solidity: {e}")

def compilar_contrato(codigo_solidity: str, nombre_contrato: str):
    """
    Compila un contrato de Solidity y devuelve su ABI y Bytecode.
    
    Args:
        codigo_solidity: El código fuente del contrato.
        nombre_contrato: El nombre del contrato a compilar.
        
    Returns:
        dict: Diccionario con 'abi', 'bytecode' y 'nombre'.
        
    Raises:
        Exception: Si la compilación falla con detalles en castellano.
    """
    instalar_solc_si_falta()
    
    try:
        logger.info(f"Compilando contrato {nombre_contrato}...")
        compilacion = solcx.compile_source(
            codigo_solidity,
            output_values=["abi", "bin"],
            solc_version="0.8.20"
        )
        
        # El ID en el diccionario de compilación suele ser "<stdin>:NombreContrato"
        id_contrato = f"<stdin>:{nombre_contrato}"
        if id_contrato not in compilacion:
            # Buscar coincidencia parcial si el nombre no es exacto
            encontrado = None
            for key in compilacion.keys():
                if key.endswith(f":{nombre_contrato}"):
                    encontrado = key
                    break
            if not encontrado:
                raise ValueError(f"No se encontró el contrato '{nombre_contrato}' en el código compilado.")
            id_contrato = encontrado

        datos = compilacion[id_contrato]
        
        return {
            "abi": datos["abi"],
            "bytecode": f"0x{datos['bin']}",
            "nombre": nombre_contrato
        }
        
    except solcx.exceptions.SolcError as e:
        error_msg = str(e)
        logger.error(f"Error de compilación Solidity: {error_msg}")
        raise Exception(f"La compilación de Solidity ha fallado: {error_msg}")
    except Exception as e:
        logger.error(f"Error inesperado en compilación: {e}")
        raise Exception(f"Error crítico durante la compilación: {str(e)}")
