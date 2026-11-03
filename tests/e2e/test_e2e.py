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
