"""
servidor.py -- La web del proyecto (backend con FastAPI).

===========================================================================
MAPA DE ESTE ARCHIVO
===========================================================================
Este archivo es el "puente" entre los algoritmos y el navegador.

  1) CARGA DE DATOS: al arrancar, carga el grafo UNA sola vez (tarda ~0.3 s).
  2) ENDPOINTS (las "URLs" que usa la web):
        GET /                     -> devuelve la página (index.html)
        GET /health               -> chequeo de salud (lo usa Render)
        GET /api/estadisticas     -> números del grafo
        GET /api/aeropuertos?q=   -> autocompletado de aeropuertos
        GET /api/ruta?origen=&destino= -> BFS + Dijkstra + Bellman-Ford de una ruta
  3) ARRANQUE LOCAL: al final del archivo.

¿QUÉ ES UN ENDPOINT?
    Es una URL que el navegador puede llamar y que devuelve datos (normalmente
    JSON). Por ejemplo, la web pedirá /api/ruta?origen=LIM&destino=SCL y el
    servidor responderá con la ruta y sus números.

Curso : 1ACC0184 - Complejidad Algorítmica (UPC, 2026-20)
===========================================================================
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from algoritmos import ResultadoRuta
from cargador_datos import cargar_grafo


# ===========================================================================
# RUTAS DE ARCHIVOS
# ===========================================================================
DIR_APP = Path(__file__).resolve().parent
DIR_ESTATICOS = DIR_APP / "static"


# ===========================================================================
# 1) CARGA DE DATOS (una sola vez, al arrancar)
# ===========================================================================
# Esto se ejecuta cuando el servidor inicia. Dejamos el grafo y la info
# de aeropuertos en dos variables globales para reutilizarlos en cada consulta.
# Así NO volvemos a leer los .dat en cada búsqueda.
print("[servidor] Cargando dataset de OpenFlights...")
GRAFO, INFO = cargar_grafo()
print("[servidor] Dataset listo. Servidor preparado.")


# ===========================================================================
# 2) APLICACIÓN FastAPI
# ===========================================================================
app = FastAPI(
    title="Planificador de Vuelos",
    description="Rutas óptimas con BFS, Dijkstra y Bellman-Ford sobre la red aérea mundial.",
    version="1.0.0",
)

# CORS: permite que la página haga peticiones al servidor sin bloqueos
# (útil si algún día el frontend se sirve desde otro dominio).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir los archivos del frontend (HTML, CSS, JS) desde /static
app.mount("/static", StaticFiles(directory=DIR_ESTATICOS), name="static")


# ===========================================================================
# ENDPOINT: página principal
# ===========================================================================
@app.get("/")
def pagina_principal() -> FileResponse:
    """Devuelve la página principal (index.html) cuando alguien entra a la raíz."""
    return FileResponse(DIR_ESTATICOS / "index.html")


# ===========================================================================
# ENDPOINT: salud (para Render y para saber que está vivo)
# ===========================================================================
@app.get("/health")
def salud() -> dict:
    """Respuesta rápida de que el servidor está funcionando."""
    return {
        "estado": "ok",
        "aeropuertos": GRAFO.num_nodos,
        "rutas": GRAFO.num_aristas,
    }


# ===========================================================================
# ENDPOINT: estadísticas del grafo
# ===========================================================================
@app.get("/api/estadisticas")
def estadisticas() -> dict:
    """Números generales del grafo, para mostrar o citar en el informe."""
    con_salidas = sum(1 for iata in INFO if GRAFO.grado_salida(iata) > 0)
    return {
        "aeropuertos": GRAFO.num_nodos,
        "rutas": GRAFO.num_aristas,
        "aeropuertos_con_salidas": con_salidas,
    }


# ===========================================================================
# Utilidades internas
# ===========================================================================
def _info_publica(iata: str) -> dict:
    """Devuelve la información de un aeropuerto lista para JSON."""
    aeropuerto = INFO.get(iata)
    if aeropuerto is None:
        return {"iata": iata}
    return {
        "iata": aeropuerto.iata,
        "nombre": aeropuerto.nombre,
        "ciudad": aeropuerto.ciudad,
        "pais": aeropuerto.pais,
        "lat": aeropuerto.lat,
        "lon": aeropuerto.lon,
    }


def _resultado_publico(resultado: ResultadoRuta, tiempo_ms: float) -> dict:
    """Convierte un ResultadoRuta a JSON, agregando tiempo y coordenadas.

    Las coordenadas (lat/lon) de cada aeropuerto del camino son lo que usa
    el mapa para dibujar la ruta. Por eso las incluimos acá.

    `detalle_tramos` ya viene armado desde algoritmos.py: un dict por vuelo
    con aerolínea, equipo, kilómetros, minutos y costo.
    """
    datos = resultado.a_diccionario()
    datos["tiempo_ms"] = round(tiempo_ms, 3)
    # Puntos con coordenadas, para dibujar la línea en el mapa.
    datos["puntos"] = [_info_publica(iata) for iata in resultado.camino]
    return datos


def _entrada_comparacion(resultado: ResultadoRuta, tiempo_ms: float) -> dict:
    """Versión liviana de un resultado, solo para la tabla de comparación.

    La comparación no necesita coordenadas ni el detalle de cada tramo:
    alcanza con qué algoritmo, qué ruta, cuánto midió y cuánto tardó.
    """
    return {
        "algoritmo": resultado.algoritmo,
        "encontrada": resultado.encontrada,
        "camino": resultado.camino,
        "distancia_total_km": round(resultado.distancia_total_km, 2),
        "tiempo_total_min": round(resultado.tiempo_total_min, 0),
        "costo_total_usd": round(resultado.costo_total_usd, 2),
        "visitados": resultado.visitados,
        "pasadas": resultado.pasadas,
        "tiempo_ms": round(tiempo_ms, 3),
    }


# ===========================================================================
# ENDPOINT: autocompletado de aeropuertos
# ===========================================================================
@app.get("/api/aeropuertos")
def buscar_aeropuertos(q: str = "", limite: int = 12) -> list[dict]:
    """Busca aeropuertos por código IATA, ciudad, nombre o país.

    PSEUDOCÓDIGO:
        1. Si la consulta está vacía -> devolver lista vacía.
        2. Normalizar a mayúsculas.
        3. Recorrer todos los aeropuertos y quedarse con los que contienen el texto.
        4. Ordenar: primero coincidencia exacta de IATA, luego las demás.
        5. Devolver como máximo 'limite' resultados.

    COMPLEJIDAD: O(A) donde A = cantidad de aeropuertos (una pasada).
    """
    texto = q.strip().upper()
    if not texto:
        return []

    encontrados: list[tuple[int, dict]] = []
    for iata, aeropuerto in INFO.items():
        if (
            texto in iata
            or texto in aeropuerto.ciudad.upper()
            or texto in aeropuerto.nombre.upper()
            or texto in aeropuerto.pais.upper()
        ):
            # Prioridad: 0 = IATA exacto, 1 = IATA que empieza con el texto, 2 = resto.
            if iata == texto:
                prioridad = 0
            elif iata.startswith(texto):
                prioridad = 1
            else:
                prioridad = 2

            encontrados.append(
                (
                    prioridad,
                    {
                        "iata": iata,
                        "nombre": aeropuerto.nombre,
                        "ciudad": aeropuerto.ciudad,
                        "pais": aeropuerto.pais,
                    },
                )
            )

    # Ordenar por prioridad y, dentro de cada prioridad, por código IATA.
    encontrados.sort(key=lambda par: (par[0], par[1]["iata"]))
    return [datos for _, datos in encontrados[:limite]]


# ===========================================================================
# ENDPOINT: calcular la ruta (BFS + Dijkstra + Bellman-Ford)
# ===========================================================================
@app.get("/api/ruta")
def calcular_ruta(origen: str, destino: str, validar: bool = False):
    """Calcula la ruta con BFS y Dijkstra, y opcionalmente valida con Bellman-Ford.

    PARÁMETRO `validar`:
        False (por defecto) -> BFS + Dijkstra. Camino rápido (~0.5 ms).
        True                -> agrega Bellman-Ford y la tabla de comparación.
                               Cuesta ~16 ms extra porque Bellman-Ford es O(V·E).

    PSEUDOCÓDIGO:
        1. Normalizar origen y destino a mayúsculas.
        2. Si alguno no existe en el grafo -> responder error 404.
        3. Medir tiempo y ejecutar BFS   -> resultado_bfs.
        4. Medir tiempo y ejecutar Dijkstra -> resultado_dijkstra.
        5. Si `validar` es True:
             a. Medir tiempo y ejecutar Bellman-Ford -> resultado_bellman.
             b. Agregar la tabla de comparación de los tres.
        6. Devolver los resultados con su información y coordenadas.

    COMPLEJIDAD:
        BFS: O(V+E) · Dijkstra: O((V+E) log V) · Bellman-Ford: O(V·E) con
        terminación temprana. Bellman-Ford solo corre si se pide.
    """
    o = origen.strip().upper()
    d = destino.strip().upper()

    # Paso 2: validar que existan.
    if not GRAFO.tiene_nodo(o):
        return JSONResponse(
            status_code=404,
            content={"error": f"El aeropuerto de origen '{o}' no existe."},
        )
    if not GRAFO.tiene_nodo(d):
        return JSONResponse(
            status_code=404,
            content={"error": f"El aeropuerto de destino '{d}' no existe."},
        )

    # Paso 3: BFS cronometrado.
    inicio_bfs = time.perf_counter()
    resultado_bfs = GRAFO.bfs_min_escalas(o, d)
    tiempo_bfs = (time.perf_counter() - inicio_bfs) * 1000  # milisegundos

    # Paso 4: Dijkstra cronometrado.
    inicio_dijkstra = time.perf_counter()
    resultado_dijkstra = GRAFO.dijkstra_min_distancia(o, d)
    tiempo_dijkstra = (time.perf_counter() - inicio_dijkstra) * 1000

    # Paso 5: respuesta base. Es el camino rápido: dos algoritmos, ~0.5 ms.
    respuesta = {
        "origen": _info_publica(o),
        "destino": _info_publica(d),
        "bfs": _resultado_publico(resultado_bfs, tiempo_bfs),
        "dijkstra": _resultado_publico(resultado_dijkstra, tiempo_dijkstra),
    }

    # Paso 6: validación opcional con Bellman-Ford.
    #
    # ¿POR QUÉ ES OPCIONAL?
    #   Bellman-Ford es O(V·E): en este grafo tarda ~16 ms contra ~0.5 ms de
    #   BFS+Dijkstra juntos. Correrlo en cada búsqueda multiplicaría por ~31 el
    #   trabajo del endpoint para hacer una comprobación que el usuario no pidió.
    #   Solo se ejecuta cuando el cliente lo pide explícitamente con ?validar=true,
    #   que es lo que hace el panel de validación de la web.
    if validar:
        inicio_bellman = time.perf_counter()
        resultado_bellman = GRAFO.bellman_ford_min_distancia(o, d)
        tiempo_bellman = (time.perf_counter() - inicio_bellman) * 1000

        respuesta["bellman_ford"] = _resultado_publico(resultado_bellman, tiempo_bellman)
        respuesta["comparacion"] = [
            _entrada_comparacion(resultado_bfs, tiempo_bfs),
            _entrada_comparacion(resultado_dijkstra, tiempo_dijkstra),
            _entrada_comparacion(resultado_bellman, tiempo_bellman),
        ]

    # Paso 7.
    return respuesta


# ===========================================================================
# 3) ARRANQUE LOCAL
# ===========================================================================
# Se ejecuta con:  python servidor.py
# o con:           uvicorn servidor:app --reload
if __name__ == "__main__":
    import uvicorn

    # host 127.0.0.1 = solo tu máquina. En Render se usa 0.0.0.0 (ver Dockerfile).
    uvicorn.run("servidor:app", host="127.0.0.1", port=8000, reload=True)
