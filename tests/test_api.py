"""Pruebas de la API HTTP con FastAPI TestClient.

Cubren: salud, estadísticas, autocompletado, cálculo de rutas, errores
(404 / 422) y que la página y los estáticos se sirvan bien.
"""

import pytest
from fastapi.testclient import TestClient

from servidor import app


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Salud y estadísticas
# ---------------------------------------------------------------------------
def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["aeropuertos"] == 6072
    assert cuerpo["rutas"] == 36707


def test_estadisticas(cliente):
    r = cliente.get("/api/estadisticas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["aeropuertos"] == 6072
    assert cuerpo["rutas"] == 36707
    assert cuerpo["aeropuertos_con_salidas"] == 3178


# ---------------------------------------------------------------------------
# Autocompletado
# ---------------------------------------------------------------------------
def test_busqueda_vacia_devuelve_lista_vacia(cliente):
    r = cliente.get("/api/aeropuertos")
    assert r.status_code == 200
    assert r.json() == []


def test_busqueda_prioriza_coincidencia_exacta(cliente):
    r = cliente.get("/api/aeropuertos", params={"q": "LIM", "limite": 5})
    assert r.status_code == 200
    assert r.json()[0]["iata"] == "LIM"


def test_busqueda_respeta_el_limite(cliente):
    r = cliente.get("/api/aeropuertos", params={"q": "a", "limite": 4})
    assert r.status_code == 200
    assert len(r.json()) <= 4


def test_busqueda_por_ciudad(cliente):
    r = cliente.get("/api/aeropuertos", params={"q": "lima", "limite": 10})
    assert r.status_code == 200
    assert any(a["ciudad"].lower() == "lima" for a in r.json())


# ---------------------------------------------------------------------------
# Cálculo de rutas
# ---------------------------------------------------------------------------
def test_ruta_lim_scl_normaliza_minusculas(cliente):
    r = cliente.get("/api/ruta", params={"origen": "lim", "destino": "scl"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["origen"]["iata"] == "LIM"
    assert datos["destino"]["iata"] == "SCL"

    for clave in ("bfs", "dijkstra"):
        res = datos[clave]
        assert res["encontrada"] is True
        assert res["camino"][0] == "LIM"
        assert res["camino"][-1] == "SCL"
        assert len(res["puntos"]) == len(res["camino"])
        assert res["tiempo_ms"] >= 0
        assert res["escalas"] == res["tramos"] - 1


def test_ruta_lim_bsb_empate_de_escalas(cliente):
    r = cliente.get("/api/ruta", params={"origen": "LIM", "destino": "BSB"})
    assert r.status_code == 200
    datos = r.json()
    assert datos["bfs"]["escalas"] == 1
    assert datos["dijkstra"]["escalas"] == 1
    assert datos["dijkstra"]["distancia_total_km"] < datos["bfs"]["distancia_total_km"]


def test_ruta_origen_inexistente_da_404(cliente):
    r = cliente.get("/api/ruta", params={"origen": "ZZZ", "destino": "SCL"})
    assert r.status_code == 404
    assert "no existe" in r.json()["error"].lower()


def test_ruta_destino_inexistente_da_404(cliente):
    r = cliente.get("/api/ruta", params={"origen": "LIM", "destino": "ZZZ"})
    assert r.status_code == 404


def test_ruta_sin_parametros_da_422(cliente):
    assert cliente.get("/api/ruta").status_code == 422
    assert cliente.get("/api/ruta", params={"origen": "LIM"}).status_code == 422


# ---------------------------------------------------------------------------
# Página y estáticos
# ---------------------------------------------------------------------------
def test_pagina_principal_sirve_html(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Planificador de Vuelos" in r.text


def test_estaticos_se_sirven(cliente):
    for archivo in ("app.js", "styles.css"):
        assert cliente.get(f"/static/{archivo}").status_code == 200
    assert "tarjetaComparacion" in cliente.get("/static/app.js").text
