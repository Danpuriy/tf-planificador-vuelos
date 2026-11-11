"""Pruebas end-to-end (E2E): navegador real contra servidor real.

Playwright abre Chromium, carga la página, completa los buscadores, hace
clic en "Buscar ruta" y verifica lo que ve el usuario: tarjetas, textos y
las líneas dibujadas en el mapa.

No modifican el código de la app: solo la usan como lo haría una persona.
"""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def buscar(page, origen: str, destino: str):
    """Completa los campos y busca.

    Setea los valores con JS para NO disparar el autocompletado (así el
    desplegable no tapa el botón). El autocompletado tiene su propia prueba.
    """
    page.evaluate(
        """([origen, destino]) => {
            document.getElementById('origen').value = origen;
            document.getElementById('destino').value = destino;
        }""",
        [origen, destino],
    )
    page.click("#buscar")
    expect(page.locator(".tarjeta.bfs")).to_be_visible(timeout=15000)
    expect(page.locator(".tarjeta.dijkstra")).to_be_visible(timeout=15000)


# ---------------------------------------------------------------------------
# Carga y autocompletado
# ---------------------------------------------------------------------------
def test_titulo_de_la_pagina(page):
    assert "Planificador de Vuelos" in page.title()


def test_autocompletado_de_lim(page):
    page.fill("#origen", "LIM")

    lista = page.locator("#lista-origen.visible")
    expect(lista).to_be_visible(timeout=5000)

    primer_item = lista.locator("li").first
    expect(primer_item).to_contain_text("LIM")
    primer_item.click()

    assert page.input_value("#origen") == "LIM"


# ---------------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------------
def test_busqueda_lim_bsb_muestra_empate_en_escalas(page):
    buscar(page, "LIM", "BSB")

    tarjeta_bfs = page.locator(".tarjeta.bfs")
    tarjeta_dijkstra = page.locator(".tarjeta.dijkstra")

    # BFS: 1 escala en singular (regresión del bug "1 escalas").
    expect(tarjeta_bfs).to_contain_text("1 escala")
    expect(tarjeta_bfs).not_to_contain_text("1 escalas")
    expect(tarjeta_bfs.locator(".ruta-texto")).to_contain_text("LIM")
    expect(tarjeta_bfs.locator(".ruta-texto")).to_contain_text("BSB")

    # Dijkstra: mismo número de escalas, pero menor distancia.
    expect(tarjeta_dijkstra).to_contain_text("1 escala")
    expect(tarjeta_dijkstra.locator(".ruta-texto")).to_contain_text("GRU")
    expect(tarjeta_dijkstra).to_contain_text("4,329.52")

    # La tarjeta de comparación explica el empate.
    comparacion = page.locator(".comparacion")
    expect(comparacion).to_be_visible()
    expect(comparacion).to_contain_text("Empate en escalas")
    expect(comparacion).to_contain_text("km menos")


def test_busqueda_directa_lim_scl(page):
    buscar(page, "LIM", "SCL")

    expect(page.locator(".tarjeta.bfs")).to_contain_text("0 escalas")
    expect(page.locator(".tarjeta.dijkstra")).to_contain_text("0 escalas")
    expect(page.locator(".comparacion")).to_contain_text("idénticas")


def test_mapa_dibuja_las_rutas(page):
    buscar(page, "LIM", "BSB")

    # Leaflet dibuja polilíneas y marcadores como <path> dentro del overlay.
    assert page.locator(".leaflet-overlay-pane path").count() >= 2
    expect(page.locator("#mapa.leaflet-container")).to_be_visible()


# ---------------------------------------------------------------------------
# Tiempo, costo y tooltips
# ---------------------------------------------------------------------------
def test_tarjetas_muestran_tiempo_y_precio(page):
    buscar(page, "LIM", "BSB")

    tarjeta_dijkstra = page.locator(".tarjeta.dijkstra")
    expect(tarjeta_dijkstra).to_contain_text("8 h 06 min")
    expect(tarjeta_dijkstra).to_contain_text("$ 470.25")

    # BFS llega por Miami: más largo y más caro.
    tarjeta_bfs = page.locator(".tarjeta.bfs")
    expect(tarjeta_bfs).to_contain_text("14 h 48 min")
    expect(tarjeta_bfs).to_contain_text("$ 1,048.84")


def test_tooltip_del_tramo_muestra_aerolinea_y_precio(page):
    buscar(page, "LIM", "BSB")

    # El mapa ajusta el encuadre dos veces (una al dibujar y otra en el
    # siguiente frame). Si medimos el punto antes de que termine, el mouse
    # cae fuera de la línea.
    page.wait_for_timeout(700)

    # Posición en píxeles del punto medio del tramo LIM->GRU, calculada con
    # la propia API de Leaflet para no depender de coordenadas a ojo.
    punto = page.evaluate(
        """() => {
            const a = mapa.latLngToContainerPoint([-12.0219, -77.114305]);
            const b = mapa.latLngToContainerPoint([-23.4356, -46.4731]);
            return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        }"""
    )
    caja = page.locator("#mapa").bounding_box()
    page.mouse.move(caja["x"] + punto["x"], caja["y"] + punto["y"])

    tooltip = page.locator(".tooltip-vuelo")
    expect(tooltip.first).to_be_visible(timeout=5000)
    expect(tooltip.first).to_contain_text("LIM → GRU")
    expect(tooltip.first).to_contain_text("Avianca")
    expect(tooltip.first).to_contain_text("3,474.66 km")
    expect(tooltip.first).to_contain_text("$ 346.68")


# ---------------------------------------------------------------------------
# Validación con Bellman-Ford (bajo demanda)
# ---------------------------------------------------------------------------
def test_panel_validacion_ejecuta_bellman_ford(page):
    buscar(page, "LIM", "BSB")

    # Por defecto NO se ejecuta: hay un botón esperando.
    expect(page.locator("#boton-validar")).to_be_visible()
    expect(page.locator(".tabla-validacion")).to_have_count(0)

    page.click("#boton-validar")
    expect(page.locator(".tabla-validacion")).to_be_visible(timeout=25000)

    # Una fila por algoritmo, y Bellman-Ford coincide con Dijkstra.
    assert page.locator(".tabla-validacion tbody tr").count() == 3
    expect(page.locator(".tabla-validacion")).to_contain_text("Bellman-Ford")
    expect(page.locator(".tabla-validacion")).to_contain_text("8,643")
    expect(page.locator(".marca-ok")).to_contain_text("Coinciden")


# ---------------------------------------------------------------------------
# Validaciones y errores
# ---------------------------------------------------------------------------
def test_campos_vacios_muestran_mensaje(page):
    page.click("#buscar")
    expect(page.locator("#mensaje")).to_have_text("Escribe un origen y un destino.")


def test_aeropuerto_inexistente_muestra_error(page):
    page.evaluate(
        """() => {
            document.getElementById('origen').value = 'ZZZ';
            document.getElementById('destino').value = 'SCL';
        }"""
    )
    page.click("#buscar")
    expect(page.locator("#mensaje")).to_contain_text("no existe", timeout=10000)
