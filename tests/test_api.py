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


def test_busqueda_rechaza_limite_cero(cliente):
    """Sin cota, limite=0 devolvería una lista vacía y limite=-5 un slicing raro."""
    r = cliente.get("/api/aeropuertos", params={"q": "a", "limite": 0})
    assert r.status_code == 422


def test_busqueda_rechaza_limite_negativo(cliente):
    r = cliente.get("/api/aeropuertos", params={"q": "a", "limite": -5})
    assert r.status_code == 422


def test_busqueda_rechaza_limite_desmedido(cliente):
    """Mas de 50 sugerencias no aportan nada y alientan pedidos abusivos."""
    r = cliente.get("/api/aeropuertos", params={"q": "a", "limite": 99999})
    assert r.status_code == 422


def test_busqueda_acepta_el_maximo_permitido(cliente):
    r = cliente.get("/api/aeropuertos", params={"q": "a", "limite": 50})
    assert r.status_code == 200
    assert len(r.json()) <= 50


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
    assert "renderizarComparacion" in cliente.get("/static/app.js").text


# ===========================================================================
# TIEMPO, COSTO Y VALIDACIÓN CON BELLMAN-FORD
# ===========================================================================
def test_ruta_devuelve_tiempo_y_costo(cliente):
    """Cada resultado debe traer duración y precio, no solo kilómetros."""
    r = cliente.get(
        "/api/ruta", params={"origen": "LIM", "destino": "BSB", "validar": True}
    )
    assert r.status_code == 200

    datos = r.json()
    for clave in ("bfs", "dijkstra", "bellman_ford"):
        res = datos[clave]
        assert res["tiempo_total_min"] > 0
        assert res["costo_total_usd"] > 0


def test_ruta_devuelve_detalle_por_tramo(cliente):
    """Cada tramo debe traer aerolínea, equipo, tiempo y costo."""
    r = cliente.get("/api/ruta", params={"origen": "LIM", "destino": "BSB"})
    datos = r.json()

    tramos = datos["dijkstra"]["detalle_tramos"]
    assert len(tramos) == datos["dijkstra"]["tramos"]

    for tramo in tramos:
        assert tramo["aerolinea"]
        assert tramo["avion"]
        assert tramo["km"] > 0
        assert tramo["tiempo_min"] > 0
        assert tramo["costo_usd"] > 0


def test_ruta_incluye_comparacion_de_tres_algoritmos(cliente):
    """La respuesta debe traer la tabla comparativa completa."""
    r = cliente.get(
        "/api/ruta", params={"origen": "LIM", "destino": "BSB", "validar": True}
    )
    datos = r.json()

    comparacion = datos["comparacion"]
    assert len(comparacion) == 3
    assert [c["algoritmo"] for c in comparacion] == ["BFS", "Dijkstra", "Bellman-Ford"]

    for entrada in comparacion:
        assert "visitados" in entrada
        assert "tiempo_ms" in entrada
        assert entrada["tiempo_ms"] >= 0


def test_dijkstra_y_bellman_ford_coinciden_en_la_api(cliente):
    """Validación de punta a punta: la web también debe ver la coincidencia."""
    r = cliente.get(
        "/api/ruta", params={"origen": "LIM", "destino": "BSB", "validar": True}
    )
    datos = r.json()

    dij = datos["dijkstra"]
    bf = datos["bellman_ford"]

    assert bf["encontrada"] is True
    assert bf["camino"] == dij["camino"]
    assert bf["distancia_total_km"] == pytest.approx(dij["distancia_total_km"], abs=0.01)


def test_bellman_ford_reporta_pasadas(cliente):
    """Bellman-Ford debe informar cuántas pasadas necesitó."""
    r = cliente.get(
        "/api/ruta", params={"origen": "LIM", "destino": "BSB", "validar": True}
    )
    datos = r.json()

    assert datos["bellman_ford"]["pasadas"] >= 1


def test_ruta_por_defecto_no_corre_bellman_ford(cliente):
    """Sin ?validar, la respuesta NO debe incluir Bellman-Ford ni la comparación.

    Protege el camino rápido: Bellman-Ford es O(V·E) y no puede colarse en
    cada búsqueda del usuario.
    """
    r = cliente.get("/api/ruta", params={"origen": "LIM", "destino": "BSB"})
    assert r.status_code == 200

    datos = r.json()
    assert "bfs" in datos and "dijkstra" in datos
    assert "bellman_ford" not in datos
    assert "comparacion" not in datos
