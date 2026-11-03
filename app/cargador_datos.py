"""
cargador_datos.py -- Lee los archivos .dat de OpenFlights y arma el grafo.

===========================================================================
MAPA DE ESTE ARCHIVO
===========================================================================
Este archivo tiene 1 solo trabajo: convertir dos archivos de texto
(airports.dat y routes.dat) en objetos que el resto del proyecto entiende.

  airports.dat  ->  lista de aeropuertos con nombre, ciudad, país y coordenadas.
  routes.dat    ->  lista de vuelos (origen -> destino) entre aeropuertos.

Al final obtiene:
  1) Un GrafoVuelos (el que hicimos en algoritmos.py), ya cargado y ponderado.
  2) Un diccionario con la información de cada aeropuerto (para mostrarla en la web).

¿POR QUÉ UN ARCHIVO APARTE?
  Porque leer archivos es una responsabilidad distinta a calcular rutas.
  Si mañana cambia el formato del .dat, solo tocamos este archivo.

Curso : 1ACC0184 - Complejidad Algorítmica (UPC, 2026-20)
===========================================================================
"""

# --- Importaciones ---
from __future__ import annotations   # permite escribir tipos como int | None

import csv                       # lector de archivos separados por comas
from dataclasses import dataclass
from pathlib import Path         # manejo de rutas de archivos

# Importamos nuestras propias piezas desde algoritmos.py.
from algoritmos import GrafoVuelos, distancia_haversine


# ===========================================================================
# CONSTANTES: dónde están los archivos
# ===========================================================================
# "Path(__file__)" es la ruta de ESTE archivo.
# .parent        -> carpeta app/
# .parent.parent -> carpeta TF/
# / "data"       -> carpeta TF/data/
DIR_APP = Path(__file__).resolve().parent
DIR_DATOS = DIR_APP.parent / "data"

ARCHIVO_AEROPUERTOS = "airports.dat"
ARCHIVO_RUTAS = "routes.dat"

# Valor que OpenFlights usa para "dato vacío".
VACIO = "\\N"


# ===========================================================================
# ESTRUCTURA DE UN AEROPUERTO
# ===========================================================================
@dataclass
class InfoAeropuerto:
    """Datos descriptivos de un aeropuerto (no participa en los cálculos)."""

    iata: str            # código de 3 letras, por ejemplo "LIM"
    nombre: str          # nombre completo del aeropuerto
    ciudad: str          # ciudad donde está
    pais: str            # país
    lat: float           # latitud (para Haversine y para el mapa)
    lon: float           # longitud (para Haversine y para el mapa)
    altitud: int | None  # altitud en pies (puede no existir)
    zona_horaria: str    # por ejemplo "America/Lima"
    tipo: str            # por ejemplo "airport"


# ===========================================================================
# UTILIDADES DE LECTURA (conversiones seguras)
# ===========================================================================
def _a_float(texto: str) -> float | None:
    """Convierte un texto a número decimal. Devuelve None si no se puede."""
    try:
        return float(texto)
    except (ValueError, TypeError):
        return None


def _a_entero(texto: str) -> int | None:
    """Convierte un texto a número entero. Devuelve None si no se puede."""
    try:
        return int(float(texto))
    except (ValueError, TypeError):
        return None


# ===========================================================================
# LECTURA DE AEROPUERTOS
# ===========================================================================
def leer_aeropuertos(
    ruta: Path,
) -> tuple[dict[str, InfoAeropuerto], dict[str, str]]:
    """Lee airports.dat y devuelve la información de cada aeropuerto válido.

    QUÉ HACE:
        Recorre el archivo fila por fila. Se queda SOLO con aeropuertos que
        tengan código IATA de 3 letras y coordenadas válidas.

    PSEUDOCÓDIGO:
        1. Preparar dos diccionarios vacíos:
             info      -> iata -> InfoAeropuerto
             id_a_iata -> id numérico del aeropuerto -> iata
        2. Por cada fila del archivo:
             a. Si la fila no tiene las columnas mínimas -> saltar.
             b. Leer el código IATA.
             c. Si el IATA está vacío o no mide 3 letras -> saltar.
             d. Leer latitud y longitud.
             e. Si alguna coordenada no es número -> saltar.
             f. Guardar la información del aeropuerto.
             g. Guardar la relación id numérico -> iata.
        3. Devolver los dos diccionarios.

    ¿POR QUÉ GUARDAMOS id -> iata?
        routes.dat referencia los aeropuertos por su ID numérico. Ese mapa
        nos deja traducir ese número a su código IATA.

    COMPLEJIDAD: O(A) donde A = cantidad de aeropuertos (una sola pasada).
    """
    # Paso 1: diccionarios vacíos.
    info: dict[str, InfoAeropuerto] = {}
    id_a_iata: dict[str, str] = {}

    leidos = 0
    # Paso 2: abrir el archivo y recorrerlo fila por fila.
    with open(ruta, encoding="utf-8") as archivo:
        for fila in csv.reader(archivo):
            leidos += 1

            # Paso 2a: necesitamos al menos 13 columnas.
            if len(fila) < 13:
                continue

            # Columnas de airports.dat (índice):
            # 0=ID, 1=nombre, 2=ciudad, 3=país, 4=IATA, 5=ICAO,
            # 6=latitud, 7=longitud, 8=altitud, 11=zona horaria, 12=tipo
            iata = fila[4]

            # Paso 2b y 2c: descartar IATA inválido.
            if iata == VACIO or iata == "" or len(iata) != 3:
                continue

            # Paso 2d: leer coordenadas.
            lat = _a_float(fila[6])
            lon = _a_float(fila[7])

            # Paso 2e: descartar si faltan coordenadas.
            if lat is None or lon is None:
                continue

            # Paso 2f: guardar la información del aeropuerto.
            info[iata] = InfoAeropuerto(
                iata=iata,
                nombre=fila[1],
                ciudad=fila[2],
                pais=fila[3],
                lat=lat,
                lon=lon,
                altitud=_a_entero(fila[8]),
                zona_horaria=fila[11],
                tipo=fila[12],
            )

            # Paso 2g: guardar la relación id numérico -> IATA.
            id_a_iata[fila[0]] = iata

    print(f"[cargador] Aeropuertos leídos: {leidos} | válidos: {len(info)}")
    return info, id_a_iata


# ===========================================================================
# LECTURA DE RUTAS Y CONSTRUCCIÓN DEL GRAFO
# ===========================================================================
def leer_rutas(
    ruta: Path,
    info: dict[str, InfoAeropuerto],
    id_a_iata: dict[str, str],
) -> tuple[GrafoVuelos, dict[str, int]]:
    """Lee routes.dat y construye el grafo de vuelos ponderado.

    QUÉ HACE:
        Por cada vuelo origen->destino válido, calcula la distancia Haversine
        entre los dos aeropuertos y la guarda como peso de la arista.

    PSEUDOCÓDIGO:
        1. Crear un grafo vacío y agregar TODOS los aeropuertos como nodos.
        2. Preparar contadores (rutas leídas, válidas, guardadas).
        3. Por cada fila del archivo:
             a. Leer el ID de origen y de destino.
             b. Traducirlos a IATA usando id_a_iata.
             c. Si algún extremo no existe o es un lazo -> saltar.
             d. Obtener las coordenadas de origen y destino.
             e. Calcular la distancia Haversine.
             f. Agregar la arista dirigida al grafo.
             g. Contar si se agregó de verdad (no era duplicada).
        4. Imprimir el resumen.
        5. Devolver el grafo y los contadores.

    COMPLEJIDAD: O(R) donde R = cantidad de rutas (una sola pasada).
    """
    # Paso 1: crear el grafo y agregar todos los aeropuertos como nodos.
    grafo = GrafoVuelos()
    for iata in info:
        grafo.agregar_nodo(iata)

    # Paso 2: contadores.
    leidas = 0
    validas = 0
    guardadas = 0

    # Paso 3: recorrer routes.dat.
    with open(ruta, encoding="utf-8") as archivo:
        for fila in csv.reader(archivo):
            leidas += 1

            # Necesitamos al menos 6 columnas.
            if len(fila) < 6:
                continue

            # Columnas de routes.dat (índice):
            # 0=aerolínea, 1=id aerolínea, 2=IATA origen, 3=ID origen,
            # 4=IATA destino, 5=ID destino, 6=codeshare, 7=escalas, 8=equipo
            id_origen = fila[3]
            id_destino = fila[5]

            # Paso 3b: traducir ID numérico -> IATA.
            origen = id_a_iata.get(id_origen)
            destino = id_a_iata.get(id_destino)

            # Paso 3c: descartar si falta algún extremo o es un lazo (origen == destino).
            if origen is None or destino is None or origen == destino:
                continue

            validas += 1

            # Paso 3d: coordenadas de ambos aeropuertos.
            datos_origen = info[origen]
            datos_destino = info[destino]

            # Paso 3e: distancia Haversine -> peso de la arista.
            km = distancia_haversine(
                datos_origen.lat, datos_origen.lon,
                datos_destino.lat, datos_destino.lon,
            )

            # Paso 3f y 3g: agregar al grafo. True = ruta nueva, False = duplicada.
            if grafo.agregar_arista(origen, destino, km):
                guardadas += 1

    # Paso 4: resumen.
    print(
        f"[cargador] Rutas leídas: {leidas} | válidas: {validas} | "
        f"únicas guardadas: {guardadas}"
    )

    # Paso 5.
    return grafo, {"leidas": leidas, "validas": validas, "guardadas": guardadas}


# ===========================================================================
# FUNCIÓN PRINCIPAL
# ===========================================================================
def cargar_grafo(
    ruta_datos: Path | None = None,
) -> tuple[GrafoVuelos, dict[str, InfoAeropuerto]]:
    """Carga el dataset completo y devuelve (grafo, info de aeropuertos).

    PSEUDOCÓDIGO:
        1. Usar la carpeta de datos indicada o la carpeta por defecto.
        2. Leer los aeropuertos.
        3. Leer las rutas y armar el grafo.
        4. Mostrar el resumen final (nodos, aristas).
        5. Devolver grafo + info.

    Esta es la función que llamará el servidor web UNA sola vez al arrancar.
    """
    # Paso 1.
    carpeta = ruta_datos if ruta_datos is not None else DIR_DATOS

    # Paso 2.
    info, id_a_iata = leer_aeropuertos(carpeta / ARCHIVO_AEROPUERTOS)

    # Paso 3.
    grafo, contadores = leer_rutas(carpeta / ARCHIVO_RUTAS, info, id_a_iata)

    # Paso 4.
    con_salidas = sum(1 for iata in info if grafo.grado_salida(iata) > 0)
    print(
        f"[cargador] Grafo listo -> {grafo.num_nodos} aeropuertos, "
        f"{grafo.num_aristas} rutas, {con_salidas} con vuelos de salida"
    )

    # Paso 5.
    return grafo, info


# ===========================================================================
# PRUEBA REAL (se ejecuta con: python cargador_datos.py)
# ===========================================================================
# Carga el dataset completo y prueba una ruta real de ejemplo: Lima -> Santiago.
if __name__ == "__main__":
    print("Cargando dataset de OpenFlights...\n")

    grafo, info = cargar_grafo()

    print("\n--- Información de un aeropuerto de ejemplo ---")
    aeropuerto = info.get("LIM")
    if aeropuerto:
        print(f"  {aeropuerto.iata}: {aeropuerto.nombre}")
        print(f"  Ciudad: {aeropuerto.ciudad} ({aeropuerto.pais})")
        print(f"  Coordenadas: {aeropuerto.lat}, {aeropuerto.lon}")

    print("\n--- Ruta de ejemplo: LIM -> SCL ---")
    bfs = grafo.bfs_min_escalas("LIM", "SCL")
    dijkstra = grafo.dijkstra_min_distancia("LIM", "SCL")

    print("  BFS      :", bfs.a_diccionario())
    print("  Dijkstra :", dijkstra.a_diccionario())
