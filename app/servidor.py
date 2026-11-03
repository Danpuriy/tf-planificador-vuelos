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
        GET /api/ruta?origen=&destino= -> BFS + Dijkstra de una ruta
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
    description="Rutas óptimas con BFS y Dijkstra sobre la red aérea mundial.",
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
    """
    datos = resultado.a_diccionario()
    datos["tiempo_ms"] = round(tiempo_ms, 3)
    # Puntos con coordenadas, para dibujar la línea en el mapa.
    datos["puntos"] = [_info_publica(iata) for iata in resultado.camino]
    return datos


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
# ENDPOINT: calcular la ruta (BFS + Dijkstra)
# ===========================================================================
@app.get("/api/ruta")
def calcular_ruta(origen: str, destino: str):
    """Calcula la ruta con BFS y con Dijkstra y devuelve ambos resultados.

    PSEUDOCÓDIGO:
        1. Normalizar origen y destino a mayúsculas.
        2. Si alguno no existe en el grafo -> responder error 404.
        3. Medir tiempo y ejecutar BFS   -> resultado_bfs.
        4. Medir tiempo y ejecutar Dijkstra -> resultado_dijkstra.
        5. Devolver ambos con su información y coordenadas.

    COMPLEJIDAD:
        BFS: O(V+E) · Dijkstra: O((V+E) log V). En la práctica, milisegundos.
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

    # Paso 5.
    return {
        "origen": _info_publica(o),
        "destino": _info_publica(d),
        "bfs": _resultado_publico(resultado_bfs, tiempo_bfs),
        "dijkstra": _resultado_publico(resultado_dijkstra, tiempo_dijkstra),
    }


# ===========================================================================
# 3) ARRANQUE LOCAL
# ===========================================================================
# Se ejecuta con:  python servidor.py
# o con:           uvicorn servidor:app --reload
if __name__ == "__main__":
    import uvicorn

    # host 127.0.0.1 = solo tu máquina. En Render se usa 0.0.0.0 (ver Dockerfile).
    uvicorn.run("servidor:app", host="127.0.0.1", port=8000, reload=True)
