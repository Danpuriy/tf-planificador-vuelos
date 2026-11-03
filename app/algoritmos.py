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
from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass, field

# Radio medio de la Tierra en kilómetros. Lo necesita la fórmula de Haversine.
RADIO_TIERRA_KM = 6371.0


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
# PARTE 2: EL RESULTADO DE UNA BÚSQUEDA
# ===========================================================================
@dataclass
class ResultadoRuta:
    """Molde con el resultado de una búsqueda de ruta.

    Sirve para que BFS y Dijkstra devuelvan EXACTAMENTE la misma forma de datos.
    Así el frontend (la web) no tiene que saber qué algoritmo se usó.

    Campos:
        algoritmo:          "BFS" o "Dijkstra".
        encontrada:         True si existe un camino.
        camino:             Lista de códigos IATA, del origen al destino.
        distancia_total_km: Suma de los pesos (km) a lo largo del camino.
        tramos:             Cantidad de vuelos (aristas).
        escalas:            Aeropuertos intermedios = tramos - 1.
        visitados:          Nodos que el algoritmo tuvo que revisar (para el informe).
    """

    algoritmo: str
    encontrada: bool
    camino: list[str] = field(default_factory=list)
    distancia_total_km: float = 0.0
    tramos: int = 0
    escalas: int = 0
    visitados: int = 0

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
        }


# ===========================================================================
# PARTE 3: EL GRAFO Y SUS ALGORITMOS
# ===========================================================================
class GrafoVuelos:
    """Grafo dirigido y ponderado guardado como lista de adyacencia.

    QUÉ HACE:
        Guarda aeropuertos (nodos) y vuelos (aristas con peso en km).
        Da dos métodos de búsqueda: bfs_min_escalas() y dijkstra_min_distancia().

    CÓMO GUARDA LOS DATOS (importante para entender):
        _indice_de:  {"LIM": 0, "SCL": 1, ...}   -> de código IATA a número.
        _iata_de:    ["LIM", "SCL", ...]         -> de número a código IATA.
        _adyacencia: [[ (1, 2450.0), ... ], ...] -> para cada aeropuerto,
                     la lista de (vecino, kilómetros).

    ¿POR QUÉ NÚMEROS Y NO TEXTOS?
        Buscar y comparar números enteros es más rápido que comparar textos,
        y ocupa menos memoria. Con 6,072 aeropuertos y 36,707 rutas, esto importa.
    """

    def __init__(self) -> None:
        # Empezamos con todo vacío.
        self._indice_de: dict[str, int] = {}                  # IATA -> número
        self._iata_de: list[str] = []                         # número -> IATA
        self._adyacencia: list[list[tuple[int, float]]] = []  # número -> [(vecino, km)]

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

    def agregar_arista(self, origen: str, destino: str, peso: float) -> bool:
        """Agrega un vuelo dirigido origen -> destino con su distancia en km.

        Devuelve False si algún aeropuerto no existe o si el vuelo ya estaba.

        PSEUDOCÓDIGO:
            1. Si origen o destino no existen -> devolver False.
            2. Obtener los números internos de origen y destino.
            3. Si ya hay una arista hacia ese destino -> devolver False (evitar duplicado).
            4. Agregar (destino, peso) a la lista del origen.
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
        for existente, _ in self._adyacencia[u]:
            if existente == v:
                return False

        # Paso 4.
        self._adyacencia[u].append((v, peso))
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

            for v, _ in self._adyacencia[u]:
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
            for v, peso in self._adyacencia[u]:
                nueva_distancia = distancia_actual + peso
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
    # 3.E) FUNCIONES INTERNAS (las usan BFS y Dijkstra)
    # ------------------------------------------------------------------
    def _construir_resultado(
        self, algoritmo: str, padre: list[int], inicio: int, objetivo: int, visitados: int
    ) -> ResultadoRuta:
        """Reconstruye el camino desde los punteros 'padre' y calcula sus métricas.

        PSEUDOCÓDIGO:
            1. Empezar en el objetivo y "subir" por padre[] hasta el inicio.
            2. Dar vuelta la lista para que quede inicio -> destino.
            3. Convertir números a códigos IATA.
            4. Sumar los pesos del camino (distancia total).
            5. Calcular tramos (aristas) y escalas (intermedios).
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
            return ResultadoRuta(algoritmo, encontrada=False, visitados=visitados)

        # Paso 3.
        camino = [self._iata_de[i] for i in camino_idx]

        # Paso 4.
        total = self._distancia_camino(camino_idx)

        # Paso 5.
        tramos = len(camino) - 1
        return ResultadoRuta(
            algoritmo=algoritmo,
            encontrada=True,
            camino=camino,
            distancia_total_km=total,
            tramos=tramos,
            escalas=max(tramos - 1, 0),   # directo = 0 escalas
            visitados=visitados,
        )

    def _distancia_camino(self, camino_idx: list[int]) -> float:
        """Suma los pesos de las aristas a lo largo de un camino ya calculado."""
        total = 0.0
        # Recorremos pares consecutivos: (a0,a1), (a1,a2), ...
        for a, b in zip(camino_idx, camino_idx[1:]):
            # Buscamos el peso de la arista a -> b en la adyacencia de a.
            for vecino, peso in self._adyacencia[a]:
                if vecino == b:
                    total += peso
                    break
        return total


# ===========================================================================
# PRUEBA RÁPIDA (se ejecuta con: python algoritmos.py)
# ===========================================================================
# Crea un grafo diminuto para ver la diferencia entre BFS y Dijkstra.
if __name__ == "__main__":
    g = GrafoVuelos()
    for codigo in ("A", "B", "C", "D"):
        g.agregar_nodo(codigo)

    # A -> B -> D: 2 tramos pero 11 km (largo).
    # A -> C -> D: 2 tramos pero 4 km (corto).
    g.agregar_arista("A", "B", 10.0)
    g.agregar_arista("B", "D", 1.0)
    g.agregar_arista("A", "C", 2.0)
    g.agregar_arista("C", "D", 2.0)

    bfs = g.bfs_min_escalas("A", "D")
    dijkstra = g.dijkstra_min_distancia("A", "D")

    print("BFS      :", bfs.a_diccionario())
    print("Dijkstra :", dijkstra.a_diccionario())
