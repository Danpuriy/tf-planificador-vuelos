"""Pruebas de los algoritmos: Haversine, grafo, BFS y Dijkstra.

La prueba más importante es `test_bfs_y_dijkstra_contra_fuerza_bruta`:
genera grafos aleatorios pequeños, enumera TODOS los caminos simples y
compara los resultados con los de BFS y Dijkstra.
"""

import itertools
import random

import pytest

from algoritmos import GrafoVuelos, distancia_haversine


# ---------------------------------------------------------------------------
# Utilidades de las pruebas
# ---------------------------------------------------------------------------
def grafo_ejemplo() -> GrafoVuelos:
    """Grafo del ejemplo didáctico: BFS y Dijkstra dan rutas distintas."""
    g = GrafoVuelos()
    for codigo in ("A", "B", "C", "D"):
        g.agregar_nodo(codigo)

    g.agregar_arista("A", "B", 10.0)
    g.agregar_arista("B", "D", 1.0)
    g.agregar_arista("A", "C", 2.0)
    g.agregar_arista("C", "D", 2.0)
    return g


def extremos_fuerza_bruta(aristas, origen, destino):
    """Enumera todos los caminos simples y devuelve (mín_tramos, mín_km)."""
    mejor_tramos = None
    mejor_km = None

    def dfs(u, visitados, km, tramos):
        nonlocal mejor_tramos, mejor_km
        if u == destino:
            if mejor_tramos is None or tramos < mejor_tramos:
                mejor_tramos = tramos
            if mejor_km is None or km < mejor_km:
                mejor_km = km
            return
        for (a, b), peso in aristas.items():
            if a == u and b not in visitados:
                dfs(b, visitados | {b}, km + peso, tramos + 1)

    dfs(origen, {origen}, 0.0, 0)
    return mejor_tramos, mejor_km


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------
def test_haversine_mismo_punto_es_cero():
    assert distancia_haversine(-12.0, -77.0, -12.0, -77.0) == pytest.approx(0.0)


def test_haversine_un_grado_de_longitud_en_el_ecuador():
    # 1 grado de longitud en el ecuador mide ~111.19 km.
    assert distancia_haversine(0, 0, 0, 1) == pytest.approx(111.19, abs=0.05)


def test_haversine_es_simetrica():
    ida = distancia_haversine(-12.02, -77.11, -33.39, -70.79)
    vuelta = distancia_haversine(-33.39, -70.79, -12.02, -77.11)
    assert ida == pytest.approx(vuelta, rel=1e-9)


# ---------------------------------------------------------------------------
# Construcción del grafo
# ---------------------------------------------------------------------------
def test_agregar_nodo_es_idempotente():
    g = GrafoVuelos()
    assert g.agregar_nodo("LIM") == g.agregar_nodo("LIM")
    assert g.num_nodos == 1


def test_agregar_arista_rechaza_duplicados():
    g = GrafoVuelos()
    g.agregar_nodo("A")
    g.agregar_nodo("B")
    assert g.agregar_arista("A", "B", 5.0) is True
    assert g.agregar_arista("A", "B", 9.0) is False
    assert g.num_aristas == 1


def test_agregar_arista_con_nodo_inexistente_falla():
    g = GrafoVuelos()
    g.agregar_nodo("A")
    assert g.agregar_arista("A", "Z", 1.0) is False


def test_grado_salida():
    g = grafo_ejemplo()
    assert g.grado_salida("A") == 2
    assert g.grado_salida("B") == 1
    assert g.grado_salida("D") == 0
    assert g.grado_salida("NOEXISTE") == 0


# ---------------------------------------------------------------------------
# BFS
# ---------------------------------------------------------------------------
def test_bfs_directo_no_tiene_escalas():
    r = grafo_ejemplo().bfs_min_escalas("A", "B")
    assert r.encontrada
    assert r.camino == ["A", "B"]
    assert r.tramos == 1
    assert r.escalas == 0


def test_bfs_minimiza_tramos_aunque_la_ruta_sea_mas_larga():
    r = grafo_ejemplo().bfs_min_escalas("A", "D")
    assert r.encontrada
    assert r.tramos == 2          # A->B->D o A->C->D, ambas 2 aristas
    assert r.escalas == 1
    assert r.camino[0] == "A" and r.camino[-1] == "D"


def test_bfs_mismo_origen_y_destino():
    r = grafo_ejemplo().bfs_min_escalas("A", "A")
    assert r.encontrada
    assert r.camino == ["A"]
    assert r.tramos == 0 and r.escalas == 0


def test_bfs_respeta_la_direccion_de_las_aristas():
    g = GrafoVuelos()
    g.agregar_nodo("A")
    g.agregar_nodo("B")
    g.agregar_arista("A", "B", 1.0)
    assert g.bfs_min_escalas("B", "A").encontrada is False


def test_bfs_nodo_inexistente_no_encontrada():
    assert grafo_ejemplo().bfs_min_escalas("A", "Z").encontrada is False


# ---------------------------------------------------------------------------
# Dijkstra
# ---------------------------------------------------------------------------
def test_dijkstra_elige_la_menor_distancia():
    r = grafo_ejemplo().dijkstra_min_distancia("A", "D")
    assert r.encontrada
    assert r.camino == ["A", "C", "D"]
    assert r.distancia_total_km == pytest.approx(4.0)
    assert r.tramos == 2 and r.escalas == 1


def test_dijkstra_directo():
    r = grafo_ejemplo().dijkstra_min_distancia("A", "B")
    assert r.camino == ["A", "B"]
    assert r.distancia_total_km == pytest.approx(10.0)


def test_dijkstra_mismo_origen_y_destino():
    r = grafo_ejemplo().dijkstra_min_distancia("A", "A")
    assert r.encontrada and r.camino == ["A"]
    assert r.distancia_total_km == pytest.approx(0.0)


def test_dijkstra_sin_ruta():
    g = GrafoVuelos()
    g.agregar_nodo("A")
    g.agregar_nodo("B")
    g.agregar_arista("A", "B", 1.0)
    assert g.dijkstra_min_distancia("B", "A").encontrada is False


def test_dijkstra_nodo_inexistente_no_encontrada():
    assert grafo_ejemplo().dijkstra_min_distancia("Z", "A").encontrada is False


# ---------------------------------------------------------------------------
# Propiedades y comparación contra fuerza bruta
# ---------------------------------------------------------------------------
def test_dijkstra_nunca_es_peor_que_bfs_en_distancia():
    g = grafo_ejemplo()
    for origen in "ABCD":
        for destino in "ABCD":
            if origen == destino:
                continue
            bfs = g.bfs_min_escalas(origen, destino)
            dij = g.dijkstra_min_distancia(origen, destino)
            if bfs.encontrada and dij.encontrada:
                assert dij.distancia_total_km <= bfs.distancia_total_km + 1e-9


def test_bfs_y_dijkstra_contra_fuerza_bruta():
    """Genera 40 grafos aleatorios y compara con TODOS los caminos simples."""
    random.seed(1234)
    for _ in range(40):
        nodos = [f"N{i}" for i in range(5)]
        g = GrafoVuelos()
        for nodo in nodos:
            g.agregar_nodo(nodo)

        aristas = {}
        for a, b in itertools.permutations(nodos, 2):
            if random.random() < 0.35:
                peso = round(random.uniform(1, 100), 2)
                if g.agregar_arista(a, b, peso):
                    aristas[(a, b)] = peso

        for origen in nodos:
            for destino in nodos:
                if origen == destino:
                    continue

                tramos, km = extremos_fuerza_bruta(aristas, origen, destino)
                bfs = g.bfs_min_escalas(origen, destino)
                dij = g.dijkstra_min_distancia(origen, destino)

                if tramos is None:
                    assert bfs.encontrada is False
                    assert dij.encontrada is False
                else:
                    assert bfs.encontrada is True
                    assert bfs.tramos == tramos
                    assert dij.encontrada is True
                    assert dij.distancia_total_km == pytest.approx(km, abs=1e-9)


# ===========================================================================
# BELLMAN-FORD: VALIDACIÓN CONTRA DIJKSTRA
# ===========================================================================
def test_bellman_ford_coincide_con_dijkstra():
    """Bellman-Ford y Dijkstra deben dar la MISMA ruta y la MISMA distancia.

    Es la prueba central del proyecto: con pesos no negativos, los dos
    algoritmos resuelven el mismo problema de optimización. Si difieren,
    hay un bug en alguno de los dos.
    """
    g = grafo_ejemplo()

    dij = g.dijkstra_min_distancia("A", "D")
    bf = g.bellman_ford_min_distancia("A", "D")

    assert bf.encontrada is True
    assert bf.camino == dij.camino
    assert bf.distancia_total_km == pytest.approx(dij.distancia_total_km)


def test_bellman_ford_coincide_con_dijkstra_en_grafos_aleatorios():
    """La coincidencia se mantiene en 20 grafos aleatorios, para todo par."""
    random.seed(99)

    for _ in range(20):
        nodos = [f"N{i}" for i in range(5)]
        g = GrafoVuelos()
        for nodo in nodos:
            g.agregar_nodo(nodo)

        for a, b in itertools.permutations(nodos, 2):
            if random.random() < 0.4:
                g.agregar_arista(a, b, round(random.uniform(1, 100), 2))

        for origen in nodos:
            for destino in nodos:
                if origen == destino:
                    continue

                dij = g.dijkstra_min_distancia(origen, destino)
                bf = g.bellman_ford_min_distancia(origen, destino)

                assert bf.encontrada == dij.encontrada
                if dij.encontrada:
                    assert bf.distancia_total_km == pytest.approx(
                        dij.distancia_total_km, abs=1e-9
                    )


def test_bellman_ford_terminacion_temprana():
    """Nunca debe hacer las V-1 pasadas si el grafo converge antes."""
    g = grafo_ejemplo()

    bf = g.bellman_ford_min_distancia("A", "D")

    assert bf.encontrada is True
    assert bf.pasadas >= 1
    assert bf.pasadas < g.num_nodos


def test_bellman_ford_nodo_inexistente():
    """Con un aeropuerto que no existe, no hay ruta."""
    g = grafo_ejemplo()

    assert g.bellman_ford_min_distancia("A", "Z").encontrada is False


def test_bellman_ford_mismo_origen_y_destino():
    """Origen igual a destino: camino trivial de un solo nodo."""
    g = grafo_ejemplo()

    bf = g.bellman_ford_min_distancia("A", "A")

    assert bf.encontrada is True
    assert bf.camino == ["A"]
    assert bf.tramos == 0


# ===========================================================================
# MODELO DE TIEMPO Y COSTO
# ===========================================================================
def test_tiempo_incluye_escala():
    """El tiempo total debe incluir los 90 min de conexión de cada escala."""
    g = grafo_ejemplo()

    ruta = g.dijkstra_min_distancia("A", "D")

    assert ruta.escalas == 1
    suma_tramos = sum(t["tiempo_min"] for t in ruta.detalle_tramos)
    assert ruta.tiempo_total_min == pytest.approx(suma_tramos + 90.0, abs=0.2)


def test_tiempo_directo_no_suma_escala():
    """Un vuelo directo no tiene conexión: solo rodaje y crucero."""
    g = grafo_ejemplo()

    ruta = g.dijkstra_min_distancia("A", "B")

    assert ruta.escalas == 0
    suma_tramos = sum(t["tiempo_min"] for t in ruta.detalle_tramos)
    assert ruta.tiempo_total_min == pytest.approx(suma_tramos, abs=0.2)


def test_costo_es_deterministico():
    """La misma ruta debe costar siempre lo mismo, entre llamadas y procesos."""
    from algoritmos import costo_tramo_usd

    primero = costo_tramo_usd("LIM", "GRU", 3474.66)
    segundo = costo_tramo_usd("LIM", "GRU", 3474.66)

    assert primero == pytest.approx(segundo)


def test_costo_positivo():
    """Ningún tramo puede costar cero o menos, con cualquier distancia."""
    from algoritmos import costo_tramo_usd

    for km in (0.0, 1.0, 500.0, 3474.66, 20000.0):
        assert costo_tramo_usd("LIM", "BSB", km) > 0.0


def test_detalle_tramos_trae_aerolinea_y_equipo():
    """Cada tramo debe llevar el nombre de la aerolínea y el equipo."""
    g = GrafoVuelos()
    for codigo in ("A", "B", "C"):
        g.agregar_nodo(codigo)

    g.agregar_arista("A", "B", 100.0, "Aerolínea Uno", "A320")
    g.agregar_arista("B", "C", 200.0, "Aerolínea Dos", "B737")

    ruta = g.dijkstra_min_distancia("A", "C")

    assert len(ruta.detalle_tramos) == 2
    assert ruta.detalle_tramos[0]["aerolinea"] == "Aerolínea Uno"
    assert ruta.detalle_tramos[0]["avion"] == "A320"
    assert ruta.detalle_tramos[1]["aerolinea"] == "Aerolínea Dos"
    assert ruta.detalle_tramos[1]["avion"] == "B737"


def test_costo_total_es_la_suma_de_los_tramos():
    """El costo total del viaje debe ser la suma exacta de sus tramos."""
    g = grafo_ejemplo()

    ruta = g.dijkstra_min_distancia("A", "D")
    suma = sum(t["costo_usd"] for t in ruta.detalle_tramos)

    assert ruta.costo_total_usd == pytest.approx(suma, abs=0.05)
