"""Pruebas end-to-end (E2E): navegador real contra servidor real.

Playwright abre Chromium, carga la página, completa los buscadores, hace
clic en "Buscar ruta" y verifica lo que ve el usuario: tarjetas, textos y
las líneas dibujadas en el mapa.

No modifican el código de la app: solo la usan como lo haría una persona.
"""

import re

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


# ---------------------------------------------------------------------------
# Interacciones del buscador y de los resultados
# ---------------------------------------------------------------------------
def test_intercambiar_origen_y_destino(page):
    page.fill("#origen", "LIM")
    page.wait_for_timeout(500)
    page.locator("#lista-origen li").first.click()
    page.fill("#destino", "BSB")
    page.wait_for_timeout(500)
    page.locator("#lista-destino li").first.click()

    page.click("#intercambiar")

    assert page.input_value("#origen") == "BSB"
    assert page.input_value("#destino") == "LIM"


def test_contador_de_pasajeros_duplica_el_precio(page):
    # El contador vive en la portada: se ajusta ANTES de buscar.
    page.click("#campo-pasajeros")
    page.click('[data-paso="adultos"][data-delta="1"]')
    page.click("#cerrar-popover")
    expect(page.locator("#resumen-pasajeros")).to_contain_text("2 adultos")

    buscar(page, "LIM", "BSB")

    # 1 adulto cuesta $ 470.25; con 2 adultos se duplica.
    expect(page.locator(".tarjeta.dijkstra")).to_contain_text("$ 940.50")


def test_ordenar_por_escalas_cambia_el_orden_de_las_tarjetas(page):
    # BKI->BIK es un par donde los algoritmos NO empatan: BFS hace 2 escalas
    # y Dijkstra 3. Por eso sirve para probar que el orden cambia de verdad.
    # (LIM->BSB no sirve: Dijkstra gana en los cuatro criterios y el orden
    # queda igual, que es justamente lo que hacía parecer roto al botón.)
    buscar(page, "BKI", "BIK")

    # "Mejor" ordena por distancia: Dijkstra primero.
    expect(page.locator(".tarjeta").first).to_have_class(re.compile(r"\bdijkstra\b"))

    page.locator(".orden button").nth(3).click()

    expect(page.locator(".tarjeta").first).to_have_class(re.compile(r"\bbfs\b"))


def test_la_nota_de_orden_explica_el_criterio(page):
    buscar(page, "BKI", "BIK")

    nota = page.locator("#nota-orden")
    expect(nota).to_be_visible()
    expect(nota).to_contain_text("distancia")

    page.locator(".orden button").nth(3).click()
    expect(nota).to_contain_text("escalas")


def test_badge_de_bfs_no_miente_cuando_empatan_en_escalas(page):
    # En LIM->BSB los dos algoritmos hacen 1 escala, así que la tarjeta de BFS
    # no puede afirmar "Menos escalas".
    buscar(page, "LIM", "BSB")

    badge = page.locator(".tarjeta.bfs .etiqueta-opcion")
    expect(badge).to_have_text("Mismas escalas")
    expect(badge).not_to_have_text("Menos escalas")


def test_badge_de_bfs_dice_menos_escalas_cuando_realmente_gana(page):
    buscar(page, "BKI", "BIK")

    expect(page.locator(".tarjeta.bfs .etiqueta-opcion")).to_have_text("Menos escalas")


def test_solo_ida_hace_una_sola_busqueda(page):
    page.click('[data-tipo="solo-ida"]')
    buscar(page, "LIM", "BSB")

    # Sin pestañas de tramo y sin total de ida y vuelta.
    expect(page.locator("#selector-tramos")).to_be_hidden()
    expect(page.locator("#res-total")).to_be_hidden()


def test_ida_y_vuelta_calcula_los_dos_tramos(page):
    page.click('[data-tipo="ida-vuelta"]')
    buscar(page, "LIM", "BSB")

    # Dos pestañas: ida y vuelta.
    tramos = page.locator("#selector-tramos .tramo")
    expect(tramos).to_have_count(2)
    expect(tramos.nth(0)).to_contain_text("Ida")
    expect(tramos.nth(1)).to_contain_text("Vuelta")

    # La ida arranca en LIM.
    expect(page.locator(".tarjeta.dijkstra .iata").first).to_have_text("LIM")

    # Al cambiar de tramo, la vuelta arranca en BSB.
    tramos.nth(1).click()
    expect(page.locator(".tarjeta.dijkstra .iata").first).to_have_text("BSB")

    # El total del viaje suma ida y vuelta.
    expect(page.locator("#res-total")).to_be_visible()
    expect(page.locator("#res-total")).to_contain_text("Ida y vuelta")
    expect(page.locator("#res-total")).to_contain_text("total")


def test_campo_vuelta_se_atenua_con_solo_ida(page):
    page.click('[data-tipo="ida-vuelta"]')
    expect(page.locator(".campo-vuelta")).not_to_have_class(re.compile(r"\binactivo\b"))

    page.click('[data-tipo="solo-ida"]')
    expect(page.locator(".campo-vuelta")).to_have_class(re.compile(r"\binactivo\b"))


def test_boarding_pass_se_abre_y_se_cierra(page):
    buscar(page, "LIM", "BSB")

    page.locator('[data-ver="dijkstra"]').click()
    expect(page.locator("#velo.visible")).to_be_visible()
    expect(page.locator("#bp-aerolinea")).to_contain_text("Avianca")
    expect(page.locator(".bp-grid")).to_contain_text("GRU")
    expect(page.locator(".bp-precio-final")).to_contain_text("$ 470.25")

    page.keyboard.press("Escape")
    expect(page.locator("#velo.visible")).to_have_count(0)


def test_modificar_busqueda_vuelve_a_la_portada(page):
    buscar(page, "LIM", "BSB")

    page.click("#boton-modificar")

    expect(page.locator("#inicio.activa")).to_be_visible()
    expect(page.locator("#resultados.activa")).to_have_count(0)


def test_sin_desborde_horizontal_en_mobile(page):
    page.set_viewport_size({"width": 390, "height": 844})
    buscar(page, "LIM", "BSB")

    ancho = page.evaluate("() => document.documentElement.scrollWidth")
    assert ancho <= 390, f"la página desborda a {ancho}px"
