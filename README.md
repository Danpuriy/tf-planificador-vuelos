# AeroRutas · Planificador de Vuelos

**TF — 1ACC0184 Complejidad Algorítmica · UPC 2026-20**

Aplicación web que calcula y **visualiza rutas de vuelo** sobre un mapa de
OpenStreetMap, comparando dos criterios de optimalidad y validando el resultado
con un tercer algoritmo.

🔗 **Demo en vivo:** https://tf-vuelos.onrender.com

| Algoritmo | Optimiza | Complejidad |
|---|---|---|
| **BFS** | menos escalas (mínimo de tramos) | `O(V + E)` |
| **Dijkstra** | menor distancia (km) | `O((V + E) log V)` |
| **Bellman-Ford** | menor distancia (validación) | `O(V · E)` |

BFS y Dijkstra son las dos **opciones de vuelo** que ve el usuario, porque
optimizan cosas distintas. Bellman-Ford optimiza lo mismo que Dijkstra, así que
no se ofrece como tercera opción: se usa como **validación independiente**. Si
ambos coinciden, la ruta de menor distancia está bien calculada.

Datos: dataset público **OpenFlights** (aeropuertos, aerolíneas y rutas).

---

## Estructura del proyecto

```
TF/
├── app/
│   ├── algoritmos.py       # Grafo + BFS + Dijkstra + Bellman-Ford
│   ├── cargador_datos.py   # Lee los .dat de OpenFlights y arma el grafo
│   ├── servidor.py         # API con FastAPI
│   └── static/             # Frontend (dos pantallas + mapa Leaflet)
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── data/
│   ├── airports.dat        # OpenFlights: aeropuertos
│   ├── airlines.dat        # OpenFlights: aerolíneas
│   └── routes.dat          # OpenFlights: rutas
├── mockup/
│   └── aerorutas.html      # Referencia visual aprobada (una sola página)
├── tests/
│   ├── test_algoritmos.py
│   ├── test_cargador_datos.py
│   ├── test_api.py
│   └── e2e/test_e2e.py     # Playwright
├── requirements.txt        # Producción
├── requirements-dev.txt    # Desarrollo y pruebas
├── Dockerfile
├── render.yaml
└── README.md
```

---

## Requisitos

- Python 3.9 o superior.
- Conexión a internet: el mapa usa Leaflet y teselas de OpenStreetMap por CDN.

---

## Cómo correr en local

Desde la carpeta `TF/`:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cd app
uvicorn servidor:app --reload
```

Abrir en el navegador: **http://127.0.0.1:8000**

> El servidor se ejecuta **dentro de `app/`** porque `cargador_datos.py` busca
> los `.dat` en `../data`.

Para probar los algoritmos sin levantar el servidor:

```bash
python app/algoritmos.py       # autotest: BFS vs Dijkstra vs Bellman-Ford
python app/cargador_datos.py   # conteos del dataset + ruta de ejemplo
```

---

## Pruebas

```bash
pip install -r requirements-dev.txt
.venv/bin/playwright install chromium   # solo la primera vez (~100 MB)

pytest                                  # todo
pytest tests/e2e                        # solo navegador real
pytest -m "not e2e"                     # todo menos el navegador
```

**78 pruebas en verde**, en unos 15 segundos:

| Archivo | Pruebas | Qué cubre |
|---|---|---|
| `test_algoritmos.py` | 30 | Haversine, grafo, BFS, Dijkstra, Bellman-Ford y verificación por fuerza bruta en grafos aleatorios |
| `test_api.py` | 19 | Endpoints 200/404/422, estáticos y casos límite |
| `test_cargador_datos.py` | 7 | Parseo de los `.dat`, nulos `\N`, unión por ID |
| `e2e/test_e2e.py` | 22 | Navegador real: autocompletado, tarjetas, tooltips, validación, boarding pass, ida y vuelta, mobile |

La verificación por fuerza bruta enumera **todos los caminos simples** en grafos
aleatorios y comprueba que BFS devuelve el mínimo de tramos y que Dijkstra y
Bellman-Ford devuelven la mínima distancia.

---

## API

| Endpoint | Qué devuelve |
|---|---|
| `GET /health` | Estado del servidor y conteo de aeropuertos/rutas |
| `GET /api/estadisticas` | Totales del grafo |
| `GET /api/aeropuertos?q=LIM&limite=10` | Buscador para el autocompletado |
| `GET /api/ruta?origen=LIM&destino=BSB` | BFS y Dijkstra con los puntos del mapa |
| `GET /api/ruta?origen=LIM&destino=BSB&validar=true` | Agrega Bellman-Ford y la comparación |

`validar` es **opcional a propósito**: Bellman-Ford cuesta `O(V · E)` y no hace
falta para dibujar la pantalla. Medido en local: **1.75 ms** sin validar contra
**17.58 ms** con validar.

```bash
curl "http://127.0.0.1:8000/api/ruta?origen=LIM&destino=BSB&validar=true"
```

---

## Modelo de tiempo y costo

El dataset **no trae** precios, horarios ni duración: solo origen, destino y
aerolínea. Por eso tiempo y costo son un **modelo declarado**, no datos reales.
Las constantes están en `app/algoritmos.py` y se pueden cambiar en un solo lugar.

```
tiempo_tramo = km / 850 km/h + 45 min de rodaje
tiempo_total = suma de tramos + 90 min por cada escala

costo_tramo  = 40 USD + km × 0.09 USD/km
```

Cada tramo lleva una variación determinística de ±8 % derivada de
`sha256(origen-destino)`, para que dos rutas del mismo largo no den idéntico.
Se usa `sha256` y no `hash()` porque el hash de Python cambia entre procesos.

En el frontend los horarios son **de referencia**: el primer tramo sale 08:35 y
cada escala suma 90 minutos. Las fechas son cosméticas; el grafo es estático.

---

## Algoritmos

- **BFS** (`bfs_min_escalas`): recorre por niveles; en un grafo sin pesos el
  primer camino que llega al destino tiene la menor cantidad de aristas.
  **No mira kilómetros**, así que entre varias rutas con las mismas escalas
  devuelve la primera que encuentra.
- **Dijkstra** (`dijkstra_min_distancia`): cola de prioridad (`heapq`) sobre
  pesos positivos; devuelve la distancia mínima.
- **Bellman-Ford** (`bellman_ford_min_distancia`): relaja todas las aristas
  `V-1` veces, con **terminación temprana** cuando una pasada no cambia nada.
  Sirve para validar y además detecta ciclos negativos (que con distancias
  Haversine nunca ocurren, pero el algoritmo los reporta).

Los tres devuelven un `ResultadoRuta` con camino, distancia total, tramos,
escalas, tiempo, costo y cuántos nodos se visitaron.

### Caso de referencia: LIM → BSB

| Algoritmo | Ruta | km | Tiempo | Costo | Visitados |
|---|---|---|---|---|---|
| BFS | LIM → MIA → BSB | 10,026.55 | 888 min | $ 1,048.84 | 10 |
| Dijkstra | LIM → GRU → BSB | 4,329.52 | 486 min | $ 470.25 | 317 |
| Bellman-Ford | LIM → GRU → BSB | 4,329.52 | 486 min | $ 470.25 | 8,643 (7 pasadas) |

Los dos caminos tienen **la misma cantidad de escalas**, pero difieren en
**5,697.03 km**. Es el ejemplo que mejor muestra que BFS y Dijkstra no son
intercambiables: optimizan cosas distintas.

Donde BFS sí gana en escalas es, por ejemplo, en **BKI → BIK**: BFS hace 2
escalas y Dijkstra 3, porque para ahorrar kilómetros Dijkstra acepta una escala
más. La interfaz muestra esa diferencia de forma explícita.

---

## Datos y limitaciones

- Dataset: **OpenFlights** (`airports.dat`, `airlines.dat`, `routes.dat`).
- **6,072 aeropuertos**, **36,707 rutas únicas**, **6,162 aerolíneas**
  (muy por encima del mínimo de 1,500 nodos del curso).
- Unión aerolínea ↔ ruta **por ID numérico**, no por código IATA.
- Pesos = distancia real en km por **Haversine**.
- Limitaciones a declarar: el dataset es una fotografía histórica (no vuelos en
  tiempo real), no incluye precios ni horarios, y no modela capacidad de vuelos.

---

## Desplegar en Render

### Opción A — Blueprint

1. Subir el repo a GitHub.
2. Render → **New → Blueprint** → elegir el repo. `render.yaml` crea el servicio
   Docker automáticamente.

### Opción B — Manual

1. Render → **New → Web Service** → conectar el repo.
2. Runtime: **Docker** (Render detecta el `Dockerfile`).
3. **Create Web Service**.

> ⚠️ El plan gratuito **duerme** el servicio tras unos minutos sin uso. La
> primera visita puede tardar **30–60 segundos**. Antes de la exposición, abrir
> la URL unos minutos antes para precalentarla.

---

## Autores

- Daniel Kevin Rodriguez Espinoza — U20221b150
- Alfaro Auris Rodrigo Sebastián — U202424566
- Ramos Cusinga Renzo Silvester

Curso: 1ACC0184 Complejidad Algorítmica — UPC 2026-20
