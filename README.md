# Planificador de Vuelos · TF Complejidad Algorítmica

Aplicación web que calcula y **visualiza rutas óptimas de vuelo** sobre un mapa
de OpenStreetMap, comparando dos algoritmos:

- **BFS** → la ruta con **menos escalas** (mínimo número de tramos).
- **Dijkstra** → la ruta con **menor distancia total** en kilómetros.

Los datos vienen del dataset público **OpenFlights** (aeropuertos y rutas).

---

## Estructura del proyecto

```
TF/
├── app/
│   ├── algoritmos.py       # Grafo + BFS + Dijkstra (núcleo, comentado)
│   ├── cargador_datos.py   # Lee airports.dat y routes.dat, arma el grafo
│   ├── servidor.py         # API con FastAPI (endpoints /api/...)
│   └── static/             # Frontend: mapa, buscadores y resultados
│       ├── index.html
│       ├── styles.css
│       └── app.js
├── data/
│   ├── airports.dat        # Dataset OpenFlights: aeropuertos
│   └── routes.dat          # Dataset OpenFlights: rutas
├── requirements.txt
├── Dockerfile
├── render.yaml             # Despliegue opcional en Render
└── README.md
```

---

## Requisitos

- Python 3.9 o superior.
- Conexión a internet (el mapa usa teselas de OpenStreetMap y Leaflet por CDN).

---

## Cómo correr en local

Desde la carpeta `TF/`:

```bash
# 1) Crear y activar el entorno virtual
python3 -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate

# 2) Instalar dependencias
pip install -r requirements.txt

# 3) Entrar a la carpeta de la app y levantar el servidor
cd app
uvicorn servidor:app --reload
```

Abre en el navegador: **http://127.0.0.1:8000**

> Importante: el servidor se ejecuta **dentro de `app/`**, porque `cargador_datos.py`
> busca los `.dat` en `../data`.

---

## Pruebas (QA)

Desde la carpeta `TF/`:

```bash
pip install -r requirements-dev.txt
pytest
```

Son **44 pruebas** (37 de lógica/API + 7 end-to-end) y cubren:

- **Haversine**: distancia cero, simetría, un grado de longitud.
- **Grafo**: nodos idempotentes, aristas duplicadas, nodos inexistentes, grados.
- **BFS**: directo, mínimo de tramos, dirección de las aristas, sin ruta.
- **Dijkstra**: menor distancia, directo, sin ruta.
- **Fuerza bruta**: en 40 grafos aleatorios se enumeran TODOS los caminos simples
  y se comprueba que BFS da el mínimo de tramos y Dijkstra la mínima distancia.
- **Dataset real**: 6,072 aeropuertos, 36,707 rutas, LIM→SCL, empate LIM→BSB.
- **API HTTP**: 200 en los endpoints, 404 para aeropuertos inexistentes,
  422 si faltan parámetros, y que la página y los estáticos se sirvan.
- **E2E (navegador real)**: Chromium abre la app, usa el autocompletado, busca
  LIM→BSB y LIM→SCL, y verifica las tarjetas, el texto de empate y que el mapa
  dibuje las rutas.

La primera vez hay que descargar el navegador de Playwright (~100 MB):

```bash
.venv/bin/playwright install chromium
```

Comandos útiles:

```bash
.venv/bin/python -m pytest              # todo (44 pruebas)
.venv/bin/python -m pytest tests/e2e    # solo navegador
.venv/bin/python -m pytest -m "not e2e" # todo menos el navegador
```

> Las pruebas de API y E2E usan el dataset real. La suite completa tarda ~4 s.

---

## API (por si quieres probarla con curl)

| Endpoint | Qué devuelve |
|---|---|
| `GET /health` | Estado del servidor y conteo de aeropuertos/rutas |
| `GET /api/estadisticas` | Totales del grafo |
| `GET /api/aeropuertos?q=LIM&limite=10` | Buscador de aeropuertos (autocompletado) |
| `GET /api/ruta?origen=LIM&destino=SCL` | Resultado de BFS y Dijkstra con los puntos del mapa |

Ejemplo:

```bash
curl "http://127.0.0.1:8000/api/ruta?origen=LIM&destino=SCL"
```

---

## Desplegar en Render (gratis)

### Opción A — Blueprint (más rápido)

1. Sube el proyecto a un repositorio de GitHub (solo la carpeta `TF/` o el repo completo).
2. En Render: **New → Blueprint**, elige el repo y confirma. Render lee `render.yaml`
   y crea el servicio con Docker automáticamente.

### Opción B — Manual

1. Sube el proyecto a GitHub.
2. En Render: **New → Web Service** → conecta el repo.
3. En **Language / Runtime** elige **Docker**.
4. Render detecta el `Dockerfile`. Deja el resto por defecto.
5. **Create Web Service**.

Cuando termine el despliegue, Render te da una URL pública
(`https://tf-vuelos-xxxx.onrender.com`). Esa es la que usas en la exposición.

> ⚠️ El plan gratuito **duerme** el servicio tras unos minutos sin uso. La primera
> visita puede tardar **30–60 segundos** en despertar. Durante la exposición,
> **abre la URL unos minutos antes** para "precalentarla".

---

## Datos y alcance

- Dataset: OpenFlights (`airports.dat` + `routes.dat`).
- Se conservan **6,072 aeropuertos** y **36,707 rutas únicas** (más que el mínimo
  de 1,500 nodos que pide el curso).
- Los pesos de las aristas son distancias reales calculadas con la fórmula de
  **Haversine** (km).
- Limitaciones a declarar en el informe: el dataset no incluye precios, horarios
  ni capacidad; es una fotografía histórica, no vuelos en tiempo real.

---

## Algoritmos implementados

- **BFS** (`bfs_min_escalas`): recorre el grafo por niveles; en un grafo sin pesos
  devuelve el camino con menos aristas = menos escalas. Complejidad `O(V + E)`.
  Si hay varias rutas con el **mismo número de escalas**, devuelve la primera que
  encuentra (no necesariamente la de menos km). Ejemplo: `LIM → BSB` tiene 8 rutas
  con 1 escala; BFS puede devolver `LIM → MIA → BSB` (10,026 km) mientras Dijkstra
  devuelve `LIM → GRU → BSB` (4,329 km).
- **Dijkstra** (`dijkstra_min_distancia`): con cola de prioridad (`heapq`) sobre
  pesos positivos (km); devuelve la distancia mínima. Complejidad `O((V + E) log V)`.

Ambos devuelven un `ResultadoRuta` con: camino, distancia total, tramos, escalas
y cuántos nodos se visitaron (útil para comparar en el informe).

---

## Autores

- Daniel Kevin Rodriguez Espinoza — U20221b150
- Alfaro Auris Rodrigo Sebastián — U202424566
- Ramos Cusinga Renzo Silvester

Curso: 1ACC0184 Complejidad Algorítmica — UPC 2026-20
