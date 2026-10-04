"""Receptor HTTPS de webhooks para entornos de prueba controlados.

    python -m operacion.receptor_prueba --puerto 9443 --certificado c.pem --clave k.pem --registro llegadas.jsonl

Responde 200 a cualquier POST, salvo rutas que contienen "/falla" (500), y
anota cada llegada (ruta, encabezados de ChainSignal y tamaño del cuerpo) en
un archivo JSONL. Lo uso para validar entregas externas sin salir a internet
ni mandar datos a terceros. No es para producción.
"""

import argparse
import http.server
import json
import shutil
import ssl
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple


def generar_certificado(directorio: Path, nombre: str = "localhost", prefijo: str = "receptor") -> Optional[Tuple[Path, Path]]:
    """Certificado autofirmado de un día para `nombre`. None si no hay openssl."""
    if shutil.which("openssl") is None:
        return None
    cert, clave = directorio / f"{prefijo}-cert.pem", directorio / f"{prefijo}-clave.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", f"/CN={nombre}",
                    "-addext", f"subjectAltName=DNS:{nombre}", "-keyout", str(clave), "-out", str(cert)], check=True, capture_output=True)
    return cert, clave


def servir(puerto: int, cert: Path, clave: Path, registro: Path, host: str = "127.0.0.1") -> http.server.HTTPServer:
    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            cuerpo = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            codigo = 500 if "/falla" in self.path else 200
            with registro.open("a", encoding="utf-8") as archivo:
                archivo.write(json.dumps({
                    "at": time.time(), "path": self.path, "status": codigo, "bytes": len(cuerpo),
                    "signature": self.headers.get("X-ChainSignal-Signature"), "idempotency_key": self.headers.get("Idempotency-Key"),
                }) + "\n")
            self.send_response(codigo)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    servidor = http.server.HTTPServer((host, puerto), Manejador)
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(str(cert), str(clave))
    servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--puerto", type=int, default=9443)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--certificado", required=True)
    parser.add_argument("--clave", required=True)
    parser.add_argument("--registro", required=True)
    args = parser.parse_args()
    servir(args.puerto, Path(args.certificado), Path(args.clave), Path(args.registro), args.host)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
