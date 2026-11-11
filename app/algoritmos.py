"""
algoritmos.py -- El "cerebro" del proyecto: el grafo y los dos algoritmos.

===========================================================================
MAPA DE ESTE ARCHIVO
===========================================================================
Este archivo tiene 3 partes, de arriba hacia abajo:

  1) distancia_haversine()  -> calcula la distancia real entre 2 coordenadas GPS.
  2) ResultadoRuta          -> el "molde" de lo que devuelve cada búsqueda.
  3) GrafoVuelos            -> el grafo + BFS + Dijkstra.

Este archivo NO sabe nada de la web ni de los archivos .dat.
Solo recibe llamadas como: "dame la mejor ruta de LIM a SCL".
Eso lo hace fácil de probar y de defender.

Curso : 1ACC0184 - Complejidad Algorítmica (UPC, 2026-20)
===========================================================================
"""

# --- Importaciones estándar de Python (no son nuestras, ya vienen con Python) ---
# heapq   -> nos da el "montículo" (min-heap) que usa Dijkstra.
# math     -> funciones matemáticas (seno, coseno, raíz, radianes).
# deque    -> una cola doble eficiente que usa BFS.
# dataclass-> decorador que crea clases simples para guardar datos.
# hashlib  -> hash estable para que el precio de una ruta no cambie entre ejecuciones.
# NamedTuple -> tupla inmutable con nombres de campo (la usamos para la arista).
from __future__ import annotations

import hashlib
import heapq
import math
from collections import deque
from dataclasses import dataclass, field
from typing import NamedTuple

# Radio medio de la Tierra en kilómetros. Lo necesita la fórmula de Haversine.
RADIO_TIERRA_KM = 6371.0


# ===========================================================================
# PARTE 0: SUPUESTOS DEL MODELO DE TIEMPO Y COSTO
# ===========================================================================
# Estos números NO salen del dataset: son supuestos declarados del proyecto.
# Van acá arriba, con nombre y en un solo lugar, para poder citarlos en el
# informe y para que cualquiera pueda cambiarlos sin buscar por todo el archivo.

# Velocidad de crucero típica de un avión comercial de pasajeros.
VELOCIDAD_CRUCERO_KMH = 850.0

# Minutos que se pierden en cada tramo por rodaje, despegue y aterrizaje.
TIEMPO_RODAJE_MIN = 45.0

# Minutos mínimos de conexión entre dos tramos (la escala).
TIEMPO_ESCALA_MIN = 90.0

# Costo fijo de emitir un pasaje (tasas, handling, servicio a bordo).
TARIFA_BASE_USD = 40.0

# Costo variable por kilómetro volado.
TARIFA_POR_KM_USD = 0.09

# Variación máxima de precio por ruta (±8%), para que no todas las rutas
# de la misma distancia cuesten exactamente lo mismo.
VARIACION_MAX = 0.08


# ===========================================================================
# PARTE 1: DISTANCIA ENTRE DOS PUNTOS DE LA TIERRA (Haversine)
# ===========================================================================
def distancia_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia de círculo máximo entre dos coordenadas, en kilómetros.

    QUÉ HACE:
        Dadas la latitud/longitud de dos aeropuertos, devuelve cuántos
        kilómetros hay entre ellos "en línea recta sobre la esfera terrestre".

    PSEUDOCÓDIGO:
        1. Convertir los 4 ángulos de grados a radianes.
        2. Calcular la diferencia de latitud y de longitud.
        3. Aplicar la fórmula de Haversine.
        4. Multiplicar por 2 * radio de la Tierra.

    COMPLEJIDAD: O(1), siempre el mismo número de operaciones.

    ¿POR QUÉ EXISTE?:
        Sin esta distancia, el grafo no tendría "pesos" y Dijkstra sería
        igual que BFS. Es lo que hace que cada arista (vuelo) pese distinto.
    """
    # Paso 1: pasar de grados a radianes (las funciones math.* usan radianes).
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)      # diferencia de latitud
    d_lambda = math.radians(lon2 - lon1)   # diferencia de longitud

    # Paso 2 y 3: fórmula de Haversine.
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    # Paso 4: distancia final en kilómetros.
    return 2 * RADIO_TIERRA_KM * math.asin(math.sqrt(a))


# ===========================================================================
# PARTE 1.B: TIEMPO Y COSTO (modelo declarado, no dato real)
# ===========================================================================
def factor_precio(origen: str, destino: str) -> float:
    """Factor de variación de precio para una ruta, entre 0.92 y 1.08.

    QUÉ HACE:
        Convierte el par (origen, destino) en un número estable y lo lleva al
        rango [1 - VARIACION_MAX, 1 + VARIACION_MAX].

    POR QUÉ HASH Y NO random:
        `random` devolvería un precio distinto en cada llamada. Necesitamos que
        la misma ruta cueste siempre lo mismo: para que la web no cambie los
        precios al recargar, y para que los tests sean reproducibles.
        Tampoco sirve el `hash()` de Python porque cambia entre procesos.

    COMPLEJIDAD: O(1).
    """
    digest = hashlib.sha256(f"{origen}-{destino}".encode("utf-8")).digest()

    # Tomamos los primeros 4 bytes como entero sin signo y lo normalizamos a [0, 1).
    entero = int.from_bytes(digest[:4], "big")
    proporcion = entero / 2**32

    # Llevamos [0, 1) a [1 - VARIACION_MAX, 1 + VARIACION_MAX].
    return 1.0 + (proporcion * 2.0 - 1.0) * VARIACION_MAX


def tiempo_tramo_min(km: float) -> float:
    """Minutos de vuelo de un tramo: crucero + rodaje.

    MODELO: (km / VELOCIDAD_CRUCERO_KMH) horas, más TIEMPO_RODAJE_MIN minutos.

    COMPLEJIDAD: O(1).
    """
    return (km / VELOCIDAD_CRUCERO_KMH) * 60.0 + TIEMPO_RODAJE_MIN


def costo_tramo_usd(origen: str, destino: str, km: float) -> float:
    """Costo estimado de un tramo en dólares.

    MODELO: TARIFA_BASE_USD + km * TARIFA_POR_KM_USD, ajustado por el factor
    de variación de la ruta.

    COMPLEJIDAD: O(1).
    """
    base = TARIFA_BASE_USD + km * TARIFA_POR_KM_USD
    return base * factor_precio(origen, destino)


# ===========================================================================
# PARTE 2: EL RESULTADO DE UNA BÚSQUEDA
# ===========================================================================
class Arista(NamedTuple):
    """Un vuelo dirigido dentro de la lista de adyacencia.

    POR QUÉ UNA NamedTuple Y NO UNA TUPLA PELADA:
        Antes la arista era `(vecino, km)`. Ahora necesita cuatro datos.
        Con una tupla normal, cada bucle tendría que escribir
        `for vecino, km, _aerolinea, _avion in ...`, que es ruido puro.
        Con NamedTuple se lee `arista.vecino` y `arista.km`, y sigue siendo
        inmutable y liviana (no crea objetos con __dict__).

    Campos:
        vecino:    Número interno del aeropuerto de destino.
        km:        Distancia Haversine del tramo (el peso del grafo).
        aerolinea: Nombre real de la aerolínea, según airlines.dat.
        avion:     Equipo declarado en routes.dat (ej. "A320", "789").
    """

    vecino: int
    km: float
    aerolinea: str = "Desconocida"
    avion: str = "—"


@dataclass
class ResultadoRuta:
    """Molde con el resultado de una búsqueda de ruta.

    Sirve para que BFS, Dijkstra y Bellman-Ford devuelvan EXACTAMENTE la misma
    forma de datos. Así el frontend (la web) no tiene que saber qué algoritmo
    se usó.

    Campos:
        algoritmo:          "BFS", "Dijkstra" o "Bellman-Ford".
        encontrada:         True si existe un camino.
        camino:             Lista de códigos IATA, del origen al destino.
        distancia_total_km: Suma de los pesos (km) a lo largo del camino.
        tramos:             Cantidad de vuelos (aristas).
        escalas:            Aeropuertos intermedios = tramos - 1.
        visitados:          Nodos que el algoritmo tuvo que revisar (para el informe).
        pasadas:            Vueltas del bucle externo (solo Bellman-Ford la usa).
        tiempo_total_min:   Duración del viaje completo, incluidas las escalas.
        costo_total_usd:    Suma de los costos estimados de cada tramo.
        detalle_tramos:     Un dict por tramo, con aerolínea, equipo, tiempo y costo.
    """

    algoritmo: str
    encontrada: bool
    camino: list[str] = field(default_factory=list)
    distancia_total_km: float = 0.0
    tramos: int = 0
    escalas: int = 0
    visitados: int = 0
    pasadas: int = 0
    tiempo_total_min: float = 0.0
    costo_total_usd: float = 0.0
    detalle_tramos: list[dict] = field(default_factory=list)

    def a_diccionario(self) -> dict:
        """Convierte el resultado a un diccionario (esto es lo que viaja a la web)."""
        return {
            "algoritmo": self.algoritmo,
            "encontrada": self.encontrada,
            "camino": self.camino,
            "distancia_total_km": round(self.distancia_total_km, 2),
            "tramos": self.tramos,
            "escalas": self.escalas,
            "visitados": self.visitados,
            "pasadas": self.pasadas,
            "tiempo_total_min": round(self.tiempo_total_min, 0),
            "costo_total_usd": round(self.costo_total_usd, 2),
            "detalle_tramos": self.detalle_tramos,
        }


# ===========================================================================
# PARTE 3: EL GRAFO Y SUS ALGORITMOS
# ===========================================================================
class GrafoVuelos:
    """Grafo dirigido y ponderado guardado como lista de adyacencia.

    QUÉ HACE:
        Guarda aeropuertos (nodos) y vuelos (aristas con peso en km).
        Da tres métodos de búsqueda: bfs_min_escalas(), dijkstra_min_distancia()
        y bellman_ford_min_distancia().

    CÓMO GUARDA LOS DATOS (importante para entender):
        _indice_de:  {"LIM": 0, "SCL": 1, ...}   -> de código IATA a número.
        _iata_de:    ["LIM", "SCL", ...]         -> de número a código IATA.
        _adyacencia: [[ Arista(1, 2450.0, "LATAM", "A320"), ... ], ...]
                     -> para cada aeropuerto, la lista de vuelos de salida.

    ¿POR QUÉ NÚMEROS Y NO TEXTOS?
        Buscar y comparar números enteros es más rápido que comparar textos,
        y ocupa menos memoria. Con 6,072 aeropuertos y 36,707 rutas, esto importa.
    """

    def __init__(self) -> None:
        # Empezamos con todo vacío.
        self._indice_de: dict[str, int] = {}          # IATA -> número
        self._iata_de: list[str] = []                 # número -> IATA
        self._adyacencia: list[list[Arista]] = []     # número -> [Arista]

    # ------------------------------------------------------------------
    # 3.A) CONSTRUIR EL GRAFO
    # ------------------------------------------------------------------
    def agregar_nodo(self, iata: str) -> int:
        """Agrega un aeropuerto si no existe. Devuelve su número interno.

        PSEUDOCÓDIGO:
            1. Si el aeropuerto ya está -> devolver su número y salir.
            2. Si no -> asignarle el siguiente número libre.
            3. Guardarlo en los 3 arreglos.
            4. Devolver el número.

        COMPLEJIDAD: O(1) en promedio (búsqueda en diccionario).
        """
        # Paso 1: ¿ya existe?
        indice = self._indice_de.get(iata)
        if indice is not None:
            return indice

        # Paso 2: nuevo número = tamaño actual.
        indice = len(self._iata_de)

        # Paso 3: guardar en los 3 arreglos.
        self._indice_de[iata] = indice
        self._iata_de.append(iata)
        self._adyacencia.append([])   # empieza sin vuelos de salida

        # Paso 4.
        return indice

    def agregar_arista(
        self,
        origen: str,
        destino: str,
        peso: float,
        aerolinea: str = "Desconocida",
        avion: str = "—",
    ) -> bool:
        """Agrega un vuelo dirigido origen -> destino con su distancia en km.

        Devuelve False si algún aeropuerto no existe o si el vuelo ya estaba.

        `aerolinea` y `avion` son opcionales para que el grafo se pueda usar en
        pruebas sin cargar el dataset completo. En la aplicación real siempre
        vienen de routes.dat y airlines.dat.

        PSEUDOCÓDIGO:
            1. Si origen o destino no existen -> devolver False.
            2. Obtener los números internos de origen y destino.
            3. Si ya hay una arista hacia ese destino -> devolver False (evitar duplicado).
            4. Agregar la Arista(destino, peso, aerolínea, avión) a la lista del origen.
            5. Devolver True.

        COMPLEJIDAD: O(grado de salida del origen) por revisar duplicados.
        """
        # Paso 1.
        if origen not in self._indice_de or destino not in self._indice_de:
            return False

        # Paso 2.
        u = self._indice_de[origen]
        v = self._indice_de[destino]

        # Paso 3: evitar la misma ruta dos veces (varias aerolíneas, misma ruta).
        for existente in self._adyacencia[u]:
            if existente.vecino == v:
                return False

        # Paso 4.
        self._adyacencia[u].append(Arista(v, peso, aerolinea, avion))
        return True

    # ------------------------------------------------------------------
    # 3.B) CONSULTAS BÁSICAS (para mostrar números y estadísticas)
    # ------------------------------------------------------------------
    @property
    def num_nodos(self) -> int:
        """Cantidad de aeropuertos del grafo."""
        return len(self._iata_de)

    @property
    def num_aristas(self) -> int:
        """Cantidad de rutas dirigidas del grafo."""
        return sum(len(vecinos) for vecinos in self._adyacencia)

    def tiene_nodo(self, iata: str) -> bool:
        """True si el aeropuerto existe en el grafo."""
        return iata in self._indice_de

    def aeropuertos(self) -> list[str]:
        """Devuelve todos los códigos IATA."""
        return list(self._iata_de)

    def grado_salida(self, iata: str) -> int:
        """Cantidad de destinos directos desde un aeropuerto."""
        indice = self._indice_de.get(iata)
        return 0 if indice is None else len(self._adyacencia[indice])

    # ------------------------------------------------------------------
    # 3.C) BFS: CAMINO CON MENOS ESCALAS
    # ------------------------------------------------------------------
    def bfs_min_escalas(self, origen: str, destino: str) -> ResultadoRuta:
        """Búsqueda en Anchura (BFS): camino con la menor cantidad de vuelos.

        QUÉ HACE:
            Explora el grafo "por capas". Primero todos los destinos directos
            del origen, después los que están a 2 vuelos, etc. La primera vez
            que toca el destino, lo hizo con la menor cantidad de tramos.

        PSEUDOCÓDIGO:
            1. Si origen o destino no existen -> no encontrada.
            2. Si origen == destino -> camino trivial [origen].
            3. Crear arreglo "padre" (quién me descubrió) y "visto" (ya visitado).
            4. Poner el origen en una cola y marcarlo como visto.
            5. Mientras la cola no esté vacía:
                 a. Sacar el primer nodo u.
                 b. Para cada vecino v de u:
                      - Si ya fue visto -> ignorar.
                      - Marcarlo visto, guardar que su padre es u.
                      - Si v es el destino -> reconstruir camino y devolver.
                      - Si no -> encolar v.
            6. Si la cola se vacía sin tocar el destino -> no encontrada.

        COMPLEJIDAD: O(V + E) tiempo, O(V) memoria.
        OJO: minimiza TRAMOS, no kilómetros.
        """
        # Paso 1.
        if origen not in self._indice_de or destino not in self._indice_de:
            return ResultadoRuta("BFS", encontrada=False)

        inicio = self._indice_de[origen]
        objetivo = self._indice_de[destino]

        # Paso 2.
        if inicio == objetivo:
            return ResultadoRuta("BFS", encontrada=True, camino=[origen], visitados=1)

        # Paso 3.
        padre = [-1] * len(self._adyacencia)   # -1 significa "sin padre"
        visto = [False] * len(self._adyacencia)

        # Paso 4.
        visto[inicio] = True
        cola: deque[int] = deque([inicio])
        visitados = 0

        # Paso 5.
        while cola:
            u = cola.popleft()   # sacar el primero de la cola (FIFO)
            visitados += 1

            for arista in self._adyacencia[u]:
                v = arista.vecino

                if visto[v]:
                    continue   # ya lo habíamos alcanzado por un camino igual de corto

                visto[v] = True
                padre[v] = u

                if v == objetivo:
                    # Llegamos con el mínimo de tramos: reconstruir y salir.
                    return self._construir_resultado("BFS", padre, inicio, objetivo, visitados)

                cola.append(v)   # encolar para explorarlo después

        # Paso 6.
        return ResultadoRuta("BFS", encontrada=False, visitados=visitados)

    # ------------------------------------------------------------------
    # 3.D) DIJKSTRA: CAMINO CON MENOR DISTANCIA
    # ------------------------------------------------------------------
    def dijkstra_min_distancia(self, origen: str, destino: str) -> ResultadoRuta:
        """Dijkstra: camino con la menor distancia total en kilómetros.

        QUÉ HACE:
            Explora siempre el nodo con menor distancia acumulada conocida.
            Usa un montículo (min-heap) para sacar rápido el más cercano.
            Garantiza la distancia mínima cuando los pesos son >= 0.

        PSEUDOCÓDIGO:
            1. Si origen o destino no existen -> no encontrada.
            2. Si origen == destino -> camino trivial [origen].
            3. distancia[] = infinito para todos; distancia[origen] = 0.
            4. padre[] = -1 para todos.
            5. Montículo con (0, origen).
            6. Mientras el montículo no esté vacío:
                 a. Sacar el nodo u con menor distancia d.
                 b. Si d es mayor que la distancia guardada -> ignorar (obsoleto).
                 c. Marcar u como visitado. Si u == destino -> cortar (salida temprana).
                 d. Para cada vecino v con peso w:
                      - nueva = d + w.
                      - Si nueva < distancia[v] -> actualizar distancia[v],
                        guardar padre[v] = u y meter (nueva, v) al montículo.
            7. Si distancia[destino] sigue en infinito -> no encontrada.
            8. Reconstruir camino con padre[].

        COMPLEJIDAD: O((V + E) log V) tiempo, O(V) memoria.
        REQUISITO: pesos no negativos (Haversine siempre es >= 0).
        """
        # Paso 1.
        if origen not in self._indice_de or destino not in self._indice_de:
            return ResultadoRuta("Dijkstra", encontrada=False)

        inicio = self._indice_de[origen]
        objetivo = self._indice_de[destino]

        # Paso 2.
        if inicio == objetivo:
            return ResultadoRuta("Dijkstra", encontrada=True, camino=[origen], visitados=1)

        # Paso 3 y 4.
        n = len(self._adyacencia)
        infinito = float("inf")
        distancia = [infinito] * n
        padre = [-1] * n
        distancia[inicio] = 0.0

        # Paso 5.
        monticulo: list[tuple[float, int]] = [(0.0, inicio)]
        visitados = 0

        # Paso 6.
        while monticulo:
            distancia_actual, u = heapq.heappop(monticulo)

            # Paso 6b: si esta entrada quedó vieja, la ignoramos.
            if distancia_actual > distancia[u]:
                continue

            # Paso 6c.
            visitados += 1
            if u == objetivo:
                break   # salida temprana: ya tenemos la distancia mínima al destino

            # Paso 6d.
            for arista in self._adyacencia[u]:
                v = arista.vecino
                nueva_distancia = distancia_actual + arista.km
                if nueva_distancia < distancia[v]:
                    distancia[v] = nueva_distancia
                    padre[v] = u
                    heapq.heappush(monticulo, (nueva_distancia, v))

        # Paso 7.
        if distancia[objetivo] == infinito:
            return ResultadoRuta("Dijkstra", encontrada=False, visitados=visitados)

        # Paso 8.
        return self._construir_resultado("Dijkstra", padre, inicio, objetivo, visitados)

    # ------------------------------------------------------------------
    # 3.D-bis) BELLMAN-FORD: VALIDACIÓN DE DIJKSTRA
    # ------------------------------------------------------------------
    def bellman_ford_min_distancia(self, origen: str, destino: str) -> ResultadoRuta:
        """Bellman-Ford: camino de menor distancia, por relajación repetida.

        QUÉ HACE:
            Repite V-1 veces un barrido sobre TODAS las aristas del grafo,
            mejorando la distancia cada vez que encuentra un atajo. No usa
            montículo ni cola: es fuerza bruta ordenada.

        ¿POR QUÉ ESTÁ ACÁ SI DIJKSTRA YA RESUELVE LO MISMO?
            Porque el curso pide comparar algoritmos. Bellman-Ford sirve para
            dos cosas en este proyecto:

              1. VALIDACIÓN. Con pesos no negativos, los dos DEBEN devolver la
                 misma ruta. Si algún día no coinciden, hay un bug. Eso es lo
                 que prueba tests/test_algoritmos.py.
              2. CONTRASTE DE COSTO. Es O(V·E) contra O((V+E) log V) de
                 Dijkstra. La diferencia se mide y se lleva al informe.

        ¿CUÁNDO SERÍA OBLIGATORIO BELLMAN-FORD?
            Si el grafo tuviera pesos negativos, Dijkstra daría resultados
            incorrectos y Bellman-Ford no. Nuestros pesos son kilómetros:
            nunca negativos. Por eso acá es validación, no reemplazo.

        PSEUDOCÓDIGO:
            1. Si origen o destino no existen -> no encontrada.
            2. Si origen == destino -> camino trivial [origen].
            3. distancia[] = infinito, padre[] = -1, distancia[inicio] = 0.
            4. Repetir hasta V-1 veces:
                 a. relajado = False
                 b. Para cada nodo u y cada arista (u -> v):
                      si distancia[u] + km < distancia[v] -> mejorar y relajado = True
                 c. Si NO se relajó nada -> cortar (TERMINACIÓN TEMPRANA).
            5. Si distancia[destino] es infinito -> no encontrada.
            6. Reconstruir el camino y devolver.

        TERMINACIÓN TEMPRANA:
            Si una pasada completa no mejora ninguna distancia, ninguna pasada
            siguiente puede mejorarla tampoco. Cortar ahí es lo que hace que
            este Bellman-Ford no sea siempre O(V·E) en la práctica.

        COMPLEJIDAD: O(V·E) en el peor caso; con terminación temprana suele
        cortar mucho antes. Memoria O(V).
        """
        # Paso 1.
        if origen not in self._indice_de or destino not in self._indice_de:
            return ResultadoRuta("Bellman-Ford", encontrada=False)

        inicio = self._indice_de[origen]
        objetivo = self._indice_de[destino]

        # Paso 2.
        if inicio == objetivo:
            return ResultadoRuta(
                "Bellman-Ford", encontrada=True, camino=[origen], visitados=1, pasadas=0
            )

        n = len(self._adyacencia)
        infinito = float("inf")

        # Paso 3.
        distancia = [infinito] * n
        padre = [-1] * n
        distancia[inicio] = 0.0

        visitados = 0
        pasadas = 0

        # Paso 4: como máximo V-1 pasadas.
        for _ in range(n - 1):
            relajado = False
            pasadas += 1

            for u in range(n):
                if distancia[u] == infinito:
                    continue   # todavía no se llegó a u, no hay nada que propagar

                for arista in self._adyacencia[u]:
                    nueva = distancia[u] + arista.km
                    if nueva < distancia[arista.vecino]:
                        distancia[arista.vecino] = nueva
                        padre[arista.vecino] = u
                        visitados += 1
                        relajado = True

            # Paso 4c: terminación temprana.
            if not relajado:
                break

        # Paso 5.
        if distancia[objetivo] == infinito:
            return ResultadoRuta(
                "Bellman-Ford", encontrada=False, visitados=visitados, pasadas=pasadas
            )

        # Paso 6.
        return self._construir_resultado(
            "Bellman-Ford", padre, inicio, objetivo, visitados, pasadas
        )

    # ------------------------------------------------------------------
    # 3.E) FUNCIONES INTERNAS (las usan BFS, Dijkstra y Bellman-Ford)
    # ------------------------------------------------------------------
    def _construir_resultado(
        self,
        algoritmo: str,
        padre: list[int],
        inicio: int,
        objetivo: int,
        visitados: int,
        pasadas: int = 0,
    ) -> ResultadoRuta:
        """Reconstruye el camino desde los punteros 'padre' y calcula sus métricas.

        PSEUDOCÓDIGO:
            1. Empezar en el objetivo y "subir" por padre[] hasta el inicio.
            2. Dar vuelta la lista para que quede inicio -> destino.
            3. Convertir números a códigos IATA.
            4. Recorrer el camino tramo por tramo, buscando la Arista de cada uno,
               y acumular distancia, tiempo y costo en detalle_tramos.
            5. Sumar el tiempo de las escalas (TIEMPO_ESCALA_MIN por intermedio).
            6. Calcular tramos (aristas) y escalas (intermedios).
        """
        # Paso 1: caminar hacia atrás.
        camino_idx: list[int] = []
        actual = objetivo
        while actual != -1:
            camino_idx.append(actual)
            if actual == inicio:
                break
            actual = padre[actual]

        # Paso 2.
        camino_idx.reverse()

        # Protección: si el camino no arranca en el inicio, algo falló.
        if not camino_idx or camino_idx[0] != inicio:
            return ResultadoRuta(algoritmo, encontrada=False, visitados=visitados, pasadas=pasadas)

        # Paso 3.
        camino = [self._iata_de[i] for i in camino_idx]

        # Paso 4: un dict por tramo, con todo lo que necesita la web.
        total_km = 0.0
        total_min = 0.0
        total_usd = 0.0
        detalle: list[dict] = []

        for a, b in zip(camino_idx, camino_idx[1:]):
            arista = self._buscar_arista(a, b)
            if arista is None:
                # No debería pasar: el camino salió de la adyacencia.
                continue

            minutos = tiempo_tramo_min(arista.km)
            dolares = costo_tramo_usd(self._iata_de[a], self._iata_de[b], arista.km)

            total_km += arista.km
            total_min += minutos
            total_usd += dolares

            detalle.append(
                {
                    "de": self._iata_de[a],
                    "a": self._iata_de[b],
                    "km": round(arista.km, 2),
                    "aerolinea": arista.aerolinea,
                    "avion": arista.avion,
                    "tiempo_min": round(minutos, 1),
                    "costo_usd": round(dolares, 2),
                }
            )

        # Paso 5: cada escala (aeropuerto intermedio) suma tiempo de conexión.
        tramos = len(camino) - 1
        escalas = max(tramos - 1, 0)   # directo = 0 escalas
        total_min += escalas * TIEMPO_ESCALA_MIN

        # Paso 6.
        return ResultadoRuta(
            algoritmo=algoritmo,
            encontrada=True,
            camino=camino,
            distancia_total_km=total_km,
            tramos=tramos,
            escalas=escalas,
            visitados=visitados,
            pasadas=pasadas,
            tiempo_total_min=total_min,
            costo_total_usd=total_usd,
            detalle_tramos=detalle,
        )

    def _buscar_arista(self, a: int, b: int) -> Arista | None:
        """Devuelve la Arista a -> b, o None si no existe.

        COMPLEJIDAD: O(grado de salida de a).
        """
        for arista in self._adyacencia[a]:
            if arista.vecino == b:
                return arista
        return None


# ===========================================================================
# PRUEBA RÁPIDA (se ejecuta con: python algoritmos.py)
# ===========================================================================
# Crea un grafo diminuto para ver la diferencia entre los tres algoritmos.
if __name__ == "__main__":
    g = GrafoVuelos()
    for codigo in ("A", "B", "C", "D"):
        g.agregar_nodo(codigo)

    # A -> B -> D: 2 tramos pero 11 km (largo).
    # A -> C -> D: 2 tramos pero 4 km (corto).
    g.agregar_arista("A", "B", 10.0, "Aerolínea Uno", "A320")
    g.agregar_arista("B", "D", 1.0, "Aerolínea Dos", "B737")
    g.agregar_arista("A", "C", 2.0, "Aerolínea Uno", "A320")
    g.agregar_arista("C", "D", 2.0, "Aerolínea Tres", "CR2")

    bfs = g.bfs_min_escalas("A", "D")
    dijkstra = g.dijkstra_min_distancia("A", "D")
    bellman = g.bellman_ford_min_distancia("A", "D")

    for resultado in (bfs, dijkstra, bellman):
        datos = resultado.a_diccionario()
        print(
            f"{datos['algoritmo']:13} ruta={' -> '.join(datos['camino']):15} "
            f"km={datos['distancia_total_km']:6.1f}  "
            f"min={datos['tiempo_total_min']:5.0f}  "
            f"usd={datos['costo_total_usd']:6.2f}  "
            f"visitados={datos['visitados']:3d}  pasadas={datos['pasadas']}"
        )

    # Dijkstra y Bellman-Ford deben coincidir: mismo problema, mismo óptimo.
    print()
    print("¿Dijkstra y Bellman-Ford coinciden?",
          dijkstra.camino == bellman.camino
          and abs(dijkstra.distancia_total_km - bellman.distancia_total_km) < 1e-9)
