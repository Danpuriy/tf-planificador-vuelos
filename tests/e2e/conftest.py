"""Fixtures de las pruebas end-to-end.

Levanta un servidor uvicorn REAL en un puerto libre y lo apaga al terminar.
Playwright abre un Chromium real y navega contra ese servidor.
"""

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

DIR_TF = Path(__file__).resolve().parents[2]
DIR_APP = DIR_TF / "app"


def _puerto_libre() -> int:
    """Pide al sistema un puerto TCP libre (el sistema elige uno)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def servidor_url():
    """Arranca el servidor una vez para toda la sesión de pruebas E2E."""
    puerto = _puerto_libre()
    proceso = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "servidor:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(puerto),
        ],
        cwd=str(DIR_APP),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{puerto}"

    try:
        arrancado = False
        for _ in range(150):  # esperar hasta ~15 segundos
            if proceso.poll() is not None:
                salida = proceso.stdout.read() if proceso.stdout else ""
                pytest.fail(f"El servidor terminó al arrancar:\n{salida}")
            try:
                with urllib.request.urlopen(f"{url}/health", timeout=1) as respuesta:
                    if respuesta.status == 200:
                        arrancado = True
                        break
            except Exception:
                time.sleep(0.1)

        if not arrancado:
            pytest.fail("El servidor no respondió /health a tiempo")

        yield url
    finally:
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()


@pytest.fixture(autouse=True)
def abrir_app(page, servidor_url):
    """Cada prueba arranca con la página recién cargada."""
    page.goto(servidor_url, wait_until="load")
    return page
