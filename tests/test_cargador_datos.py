"""Pruebas de integración con el dataset real de OpenFlights.

Sirven como "prueba de regresión": si alguien cambia el cargador o el dataset,
estos números tienen que seguir cuadrando.
"""

import pytest

from cargador_datos import cargar_grafo


@pytest.fixture(scope="module")
def grafo_e_info():
    """Carga el grafo una sola vez para todas las pruebas de este archivo."""
    return cargar_grafo()


def test_cantidades_esperadas(grafo_e_info):
    grafo, info = grafo_e_info
    assert grafo.num_nodos == 6072
    assert grafo.num_aristas == 36707
    assert len(info) == grafo.num_nodos


def test_lim_tiene_metadatos_y_salidas(grafo_e_info):
    grafo, info = grafo_e_info
    assert grafo.tiene_nodo("LIM")
    assert grafo.grado_salida("LIM") > 0
    assert info["LIM"].ciudad == "Lima"
    assert info["LIM"].pais == "Peru"


def test_lim_scl_es_directo(grafo_e_info):
    grafo, _ = grafo_e_info
    ruta = grafo.bfs_min_escalas("LIM", "SCL")
    assert ruta.encontrada
    assert ruta.camino == ["LIM", "SCL"]
    assert ruta.tramos == 1
    assert ruta.escalas == 0
    assert ruta.distancia_total_km == pytest.approx(2461.89, abs=1.0)


def test_caso_empate_lim_bsb(grafo_e_info):
    """BFS y Dijkstra empatan en escalas, pero BFS no minimiza kilómetros."""
    grafo, _ = grafo_e_info
    bfs = grafo.bfs_min_escalas("LIM", "BSB")
    dij = grafo.dijkstra_min_distancia("LIM", "BSB")

    assert bfs.encontrada and dij.encontrada
    assert bfs.tramos == 2 and dij.tramos == 2      # 1 escala cada una
    assert bfs.escalas == 1 and dij.escalas == 1
    assert dij.distancia_total_km < bfs.distancia_total_km


def test_no_hay_ruta_entre_aeropuertos_desconectados(grafo_e_info):
    """Un aeropuerto sin rutas de salida no puede alcanzar a otro."""
    grafo, info = grafo_e_info
    sin_salidas = [iata for iata in info if grafo.grado_salida(iata) == 0]
    assert sin_salidas, "el dataset debería tener aeropuertos sin salidas"
    aislado = sin_salidas[0]
    assert grafo.bfs_min_escalas(aislado, "LIM").encontrada is False
    assert grafo.dijkstra_min_distancia(aislado, "LIM").encontrada is False


# ===========================================================================
# AEROLÍNEAS Y EQUIPO REALES
# ===========================================================================
def test_las_aristas_tienen_aerolinea_real(grafo_e_info):
    """El grafo real debe traer nombres de aerolínea, no el valor por defecto."""
    grafo, _ = grafo_e_info

    ruta = grafo.dijkstra_min_distancia("LIM", "BSB")
    assert ruta.encontrada is True

    for tramo in ruta.detalle_tramos:
        assert tramo["aerolinea"]
        assert tramo["aerolinea"] != "Desconocida"


def test_las_aristas_tienen_equipo(grafo_e_info):
    """routes.dat trae el equipo declarado en la columna 8."""
    grafo, _ = grafo_e_info

    ruta = grafo.dijkstra_min_distancia("LIM", "BSB")

    for tramo in ruta.detalle_tramos:
        assert tramo["avion"]
        assert tramo["avion"] != "—"
