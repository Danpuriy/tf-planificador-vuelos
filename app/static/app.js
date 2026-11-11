/* =========================================================================
   app.js -- Lógica del navegador: mapa, buscadores y resultados.

   Este archivo hace 4 cosas:
     1. Dibuja el mapa de OpenStreetMap con Leaflet.
     2. Autocompleta los aeropuertos consultando /api/aeropuertos.
     3. Pide la ruta a /api/ruta y dibuja BFS y Dijkstra en el mapa,
        con un tooltip por tramo que muestra aerolínea, equipo y precio.
     4. Bajo demanda, valida el resultado con Bellman-Ford usando
        /api/ruta?validar=true (es O(V*E), así que no corre por defecto).
   ========================================================================= */

/* -------------------- 1. MAPA -------------------- */

// Creamos el mapa dentro del <main id="mapa"> y lo centramos mirando el mundo.
const mapa = L.map("mapa", { worldCopyJump: true, zoomControl: false }).setView([15, -30], 2);

L.control.zoom({ position: "bottomright" }).addTo(mapa);

// Leaflet mide el contenedor UNA sola vez al crearse. Si en ese momento el
// panel lateral todavía no reservó su ancho, el mapa se cree más chico de lo
// que es y fitBounds() calcula mal el zoom. invalidateSize() lo vuelve a medir.
window.addEventListener("load", () => mapa.invalidateSize());
window.addEventListener("resize", () => mapa.invalidateSize());

// Capa de teselas de OpenStreetMap (el "fondo" del mapa).
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(mapa);

// Grupo de capas para poder borrar todo lo dibujado en cada nueva búsqueda.
let capaActual = L.featureGroup().addTo(mapa);

// Guardamos la última búsqueda para poder validarla después con Bellman-Ford.
let ultimaBusqueda = null;


/* -------------------- 2. UTILIDADES GEOGRÁFICAS -------------------- */

/**
 * Devuelve puntos intermedios entre dos coordenadas siguiendo un arco
 * de círculo máximo (así se ven las rutas aéreas reales en un mapa plano).
 */
function granCirculo(lat1, lon1, lat2, lon2, pasos = 64) {
  const aRad = Math.PI / 180;
  const p1 = lat1 * aRad, l1 = lon1 * aRad;
  const p2 = lat2 * aRad, l2 = lon2 * aRad;

  // Distancia angular entre los dos puntos.
  const d = 2 * Math.asin(
    Math.sqrt(
      Math.sin((p2 - p1) / 2) ** 2 +
      Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2
    )
  );

  // Si son el mismo punto, no hay arco que dibujar.
  if (d === 0) return [[lat1, lon1]];

  const puntos = [];
  for (let i = 0; i <= pasos; i++) {
    const f = i / pasos;
    const A = Math.sin((1 - f) * d) / Math.sin(d);
    const B = Math.sin(f * d) / Math.sin(d);

    const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
    const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
    const z = A * Math.sin(p1) + B * Math.sin(p2);

    const lat = Math.atan2(z, Math.sqrt(x * x + y * y));
    const lon = Math.atan2(y, x);
    puntos.push([lat / aRad, lon / aRad]);
  }
  return puntos;
}


/* -------------------- 3. UTILIDADES DE FORMATO -------------------- */

/** Devuelve la palabra en singular o plural según la cantidad (1 escala / 2 escalas). */
function plural(cantidad, singular, pluralForma) {
  return cantidad === 1 ? singular : pluralForma;
}

/** 486 -> "8 h 06 min". */
function formatearDuracion(minutos) {
  const total = Math.round(minutos);
  const horas = Math.floor(total / 60);
  const resto = total % 60;
  if (horas === 0) return `${resto} min`;
  return `${horas} h ${String(resto).padStart(2, "0")} min`;
}

/** 470.25 -> "$470.25". */
function formatearPrecio(usd) {
  return "$" + usd.toLocaleString("es-PE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** 4329.52 -> "4,329.52". */
function formatearKm(km) {
  return km.toLocaleString("es-PE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Los nombres completos de OpenFlights son largos
 * ("Avianca - Aerovias Nacionales de Colombia"). Para la tarjeta usamos
 * solo la primera parte; el nombre completo queda en el tooltip.
 */
function nombreCorto(aerolinea) {
  if (!aerolinea) return "Aerolínea";
  return aerolinea.split(" - ")[0].trim();
}

/** Dos letras para el badge: "Avianca" -> "AV". */
function iniciales(aerolinea) {
  const corto = nombreCorto(aerolinea).replace(/[^A-Za-zÁÉÍÓÚÑ]/g, "");
  return corto.slice(0, 2).toUpperCase() || "··";
}


/* -------------------- 4. BUSCADOR CON AUTOCOMPLETADO -------------------- */

/**
 * Configura un input para que, al escribir, sugiera aeropuertos.
 * @param {string} idInput  id del <input>
 * @param {string} idLista  id del <ul> donde se muestran las sugerencias
 */
function configurarBuscador(idInput, idLista) {
  const input = document.getElementById(idInput);
  const lista = document.getElementById(idLista);
  let temporizador = null;

  // Cada vez que se escribe, esperamos 200 ms y consultamos al servidor.
  input.addEventListener("input", () => {
    clearTimeout(temporizador);
    const texto = input.value.trim();

    if (texto.length < 1) {
      ocultarLista(lista);
      return;
    }

    temporizador = setTimeout(async () => {
      try {
        const respuesta = await fetch(
          `/api/aeropuertos?q=${encodeURIComponent(texto)}&limite=12`
        );
        const aeropuertos = await respuesta.json();
        renderizarSugerencias(lista, aeropuertos, input);
      } catch (error) {
        console.error("Error buscando aeropuertos:", error);
      }
    }, 200);
  });

  // Ocultar la lista cuando se pierde el foco (con retraso para permitir el clic).
  input.addEventListener("blur", () => setTimeout(() => ocultarLista(lista), 150));
}

function renderizarSugerencias(lista, aeropuertos, input) {
  lista.innerHTML = "";

  if (!aeropuertos.length) {
    ocultarLista(lista);
    return;
  }

  aeropuertos.forEach((a) => {
    const item = document.createElement("li");
    item.innerHTML = `<strong>${a.iata}</strong> · ${a.ciudad}<small>${a.nombre}</small>`;

    // Al hacer clic, se escribe el código IATA en el input.
    item.addEventListener("mousedown", (evento) => {
      evento.preventDefault(); // evita que el blur oculte la lista antes del clic
      input.value = a.iata;
      ocultarLista(lista);
    });

    lista.appendChild(item);
  });

  lista.classList.add("visible");
}

function ocultarLista(lista) {
  lista.innerHTML = "";
  lista.classList.remove("visible");
}


/* -------------------- 5. DIBUJAR EN EL MAPA -------------------- */

/** Borra todo lo dibujado en la búsqueda anterior. */
function limpiarMapa() {
  capaActual.clearLayers();
}

/**
 * HTML del tooltip de un tramo. Se muestra al pasar el cursor sobre la
 * línea del mapa, igual que en una app de vuelos real.
 */
function tooltipTramoHTML(tramo, numero) {
  return `
    <div class="t-titulo">${tramo.de} → ${tramo.a}</div>
    <div class="t-aerolinea">${tramo.aerolinea}</div>
    <div class="t-fila"><span>Equipo</span><b>${tramo.avion}</b></div>
    <div class="t-fila"><span>Duración</span><b>${formatearDuracion(tramo.tiempo_min)}</b></div>
    <div class="t-fila"><span>Distancia</span><b>${formatearKm(tramo.km)} km</b></div>
    <div class="t-fila"><span>Tramo</span><b>${numero}</b></div>
    <div class="t-precio">${formatearPrecio(tramo.costo_usd)}</div>
  `;
}

/**
 * Dibuja una ruta completa: un arco por tramo, cada uno con su tooltip.
 * El tooltip se engancha a una polilínea gemela invisible y más gruesa
 * (18 px) para que sea fácil acertarle al pasar el cursor: la línea
 * visible tiene solo 3 px de ancho.
 */
function dibujarRuta(resultado, color, estiloTrazo) {
  if (!resultado.encontrada || resultado.puntos.length < 2) return;

  const puntos = resultado.puntos;
  const tramos = resultado.detalle_tramos || [];

  for (let i = 0; i < puntos.length - 1; i++) {
    const a = puntos[i];
    const b = puntos[i + 1];
    const arco = granCirculo(a.lat, a.lon, b.lat, b.lon, 64);

    // Línea visible.
    L.polyline(arco, {
      color: color,
      weight: 3,
      opacity: 0.9,
      dashArray: estiloTrazo || null,
    }).addTo(capaActual);

    // Zona de hover invisible, solo para el tooltip.
    const tramo = tramos[i];
    if (tramo) {
      L.polyline(arco, { color: color, weight: 18, opacity: 0 })
        .bindTooltip(tooltipTramoHTML(tramo, i + 1), {
          sticky: true,
          className: "tooltip-vuelo",
          direction: "top",
          offset: [0, -8],
        })
        .addTo(capaActual);
    }
  }
}

/** Dibuja un marcador por cada aeropuerto único de ambas rutas. */
function dibujarMarcadores(datos) {
  const unicos = new Map();

  // Juntamos los aeropuertos de las dos rutas sin repetir.
  [datos.dijkstra, datos.bfs].forEach((resultado) => {
    (resultado.puntos || []).forEach((p) => unicos.set(p.iata, p));
  });

  unicos.forEach((p) => {
    let color = "#64748b";
    let radio = 4;

    if (p.iata === datos.origen.iata) {
      color = "#059669"; // verde = origen
      radio = 8;
    } else if (p.iata === datos.destino.iata) {
      color = "#e11d48"; // rojo = destino
      radio = 8;
    }

    L.circleMarker([p.lat, p.lon], {
      radius: radio,
      color: "#ffffff",
      weight: 2,
      fillColor: color,
      fillOpacity: 1,
    })
      .bindPopup(
        `<strong>${p.iata}</strong><br>${p.nombre || ""}<br>${p.ciudad || ""}${
          p.pais ? ", " + p.pais : ""
        }`
      )
      .addTo(capaActual);
  });
}


/* -------------------- 6. RESULTADOS -------------------- */

/**
 * Diagrama del trayecto: extremos con código IATA y un punto por escala,
 * ubicado en su posición proporcional dentro del recorrido.
 */
function diagramaHTML(camino, duracionMin, escalas) {
  const paradas = camino.slice(1, -1);
  const nodos = paradas
    .map((_, i) => {
      const posicion = ((i + 1) / (paradas.length + 1)) * 100;
      return `<span class="parada" style="left: calc(${posicion}% - 2.5px)"></span>`;
    })
    .join("");

  return `<div class="diagrama">
      <span class="duracion">${formatearDuracion(duracionMin)}</span>
      <span class="linea"></span>
      <span class="nodo inicio"></span>
      ${nodos}
      <span class="nodo fin"></span>
      <span class="escalas">${escalas} ${plural(escalas, "escala", "escalas")}</span>
    </div>`;
}

/** Genera el HTML de una tarjeta de resultado. */
function tarjetaHTML(resultado, tipo, etiqueta) {
  if (!resultado.encontrada) {
    return `<div class="tarjeta ${tipo}">
      <div class="titulo">${etiqueta}</div>
      <p>No se encontró ruta.</p>
    </div>`;
  }

  const camino = resultado.camino;
  const primerTramo = (resultado.detalle_tramos || [])[0] || {};
  const escalas = resultado.escalas;
  const ruta = camino.join(" → ");

  // Si la ruta usa más de una aerolínea, lo aclaramos al pie.
  const aerolineas = [
    ...new Set((resultado.detalle_tramos || []).map((t) => nombreCorto(t.aerolinea))),
  ];
  const detalleAerolineas =
    aerolineas.length > 1
      ? `${aerolineas.length} aerolíneas`
      : nombreCorto(primerTramo.aerolinea);

  return `<div class="tarjeta ${tipo}">
    <div class="vuelo-cabecera">
      <div class="badge-aerolinea ${tipo}">${iniciales(primerTramo.aerolinea)}</div>
      <div>
        <div class="vuelo-aerolinea">${nombreCorto(primerTramo.aerolinea)}</div>
        <div class="vuelo-equipo">Equipo ${primerTramo.avion || "—"}</div>
      </div>
      <span class="etiqueta-opcion ${tipo === "dijkstra" ? "azul" : "ambar"}">${etiqueta}</span>
    </div>

    <div class="vuelo-trayecto">
      <div class="extremo">
        <div class="iata">${camino[0]}</div>
      </div>
      ${diagramaHTML(camino, resultado.tiempo_total_min, escalas)}
      <div class="extremo derecha">
        <div class="iata">${camino[camino.length - 1]}</div>
      </div>
    </div>

    <div class="ruta-texto">${ruta}</div>

    <div class="vuelo-pie">
      <div class="detalle">
        <strong>${formatearKm(resultado.distancia_total_km)}</strong> km<br />
        ${resultado.tramos} ${plural(resultado.tramos, "tramo", "tramos")} · ${detalleAerolineas}
      </div>
      <div class="precio">
        <span class="monto">${formatearPrecio(resultado.costo_total_usd)}</span>
        <span class="nota">${resultado.tiempo_ms} ms</span>
      </div>
    </div>
  </div>`;
}

/**
 * Explica la diferencia entre las dos rutas. Es clave cuando EMPATAN en
 * escalas: ahí se ve que BFS no mira los kilómetros y puede elegir una
 * ruta mucho más larga, porque BFS solo garantiza el mínimo de tramos.
 */
function tarjetaComparacion(datos) {
  const { bfs, dijkstra } = datos;
  if (!bfs.encontrada || !dijkstra.encontrada) return "";

  const diferenciaKm = Math.abs(bfs.distancia_total_km - dijkstra.distancia_total_km);
  const diferenciaEscalas = bfs.escalas - dijkstra.escalas;
  let texto;

  if (bfs.escalas === dijkstra.escalas) {
    if (diferenciaKm < 0.01) {
      texto = `Las dos rutas son <strong>idénticas</strong>: ${bfs.escalas} ${plural(
        bfs.escalas,
        "escala",
        "escalas"
      )} y la misma distancia.`;
    } else {
      texto =
        `<strong>Empate en escalas</strong>: ambas rutas tienen ${bfs.escalas} ${plural(
          bfs.escalas,
          "escala",
          "escalas"
        )}. ` +
        `Dijkstra elige la de menor distancia (<strong>${formatearKm(diferenciaKm)} km menos</strong>). ` +
        `BFS no minimiza kilómetros: entre rutas con las mismas escalas devuelve la primera que encuentra.`;
    }
  } else if (diferenciaEscalas < 0) {
    texto =
      `BFS usa <strong>${-diferenciaEscalas} ${plural(
        -diferenciaEscalas,
        "escala",
        "escalas"
      )} menos</strong> que Dijkstra, ` +
      `pero Dijkstra recorre <strong>${formatearKm(diferenciaKm)} km menos</strong>.`;
  } else {
    texto =
      `Dijkstra usa <strong>${diferenciaEscalas} ${plural(
        diferenciaEscalas,
        "escala",
        "escalas"
      )} menos</strong> que BFS ` +
      `y además recorre <strong>${formatearKm(diferenciaKm)} km menos</strong>.`;
  }

  return `<div class="comparacion">${texto}</div>`;
}

/**
 * Panel de validación. Bellman-Ford es O(V*E) y tarda ~37x más que
 * Dijkstra en el grafo real, así que NO se ejecuta en cada búsqueda:
 * el usuario lo pide con un botón y ahí se consulta /api/ruta?validar=true.
 */
function panelValidacionHTML() {
  return `<div class="validacion" id="panel-validacion">
    <div class="validacion-cabecera">
      <h3>Validar con Bellman-Ford</h3>
    </div>
    <p>Un tercer algoritmo confirma que la ruta de Dijkstra es realmente la de menor distancia.</p>
    <button class="boton-validar" id="boton-validar">Ejecutar validación</button>
  </div>`;
}

/** Tabla con los tres algoritmos, una vez que Bellman-Ford terminó. */
function tablaValidacionHTML(comparacion) {
  const filas = comparacion
    .map((fila) => {
      const clase = fila.algoritmo === "BFS" ? "ambar" : fila.algoritmo === "Dijkstra" ? "azul" : "violeta";
      return `<tr>
        <td><span class="punto ${clase}"></span>${fila.algoritmo}
          <span class="ruta-mini">${fila.camino.join(" → ")}</span>
        </td>
        <td>${formatearKm(fila.distancia_total_km)}</td>
        <td>${fila.visitados.toLocaleString("es-PE")}</td>
        <td>${fila.pasadas || "—"}</td>
        <td>${fila.tiempo_ms}</td>
      </tr>`;
    })
    .join("");

  return `<div class="validacion" id="panel-validacion">
    <div class="validacion-cabecera">
      <h3>Validación con Bellman-Ford</h3>
      <span class="marca-ok">Coinciden</span>
    </div>
    <table class="tabla-validacion">
      <thead>
        <tr>
          <th>Algoritmo</th>
          <th>km</th>
          <th>Visitados</th>
          <th>Pasadas</th>
          <th>ms</th>
        </tr>
      </thead>
      <tbody>${filas}</tbody>
    </table>
  </div>`;
}

function mostrarResultados(datos) {
  const contenedor = document.getElementById("resultados");
  contenedor.innerHTML =
    tarjetaHTML(datos.dijkstra, "dijkstra", "Menos km") +
    tarjetaHTML(datos.bfs, "bfs", "Menos escalas") +
    tarjetaComparacion(datos) +
    panelValidacionHTML();

  document.getElementById("boton-validar").addEventListener("click", ejecutarValidacion);
}

/** Pide la misma ruta con ?validar=true y reemplaza el panel por la tabla. */
async function ejecutarValidacion() {
  const boton = document.getElementById("boton-validar");
  const panel = document.getElementById("panel-validacion");
  if (!boton || !ultimaBusqueda) return;

  boton.disabled = true;
  boton.textContent = "Ejecutando Bellman-Ford...";

  try {
    const { origen, destino } = ultimaBusqueda;
    const respuesta = await fetch(
      `/api/ruta?origen=${encodeURIComponent(origen)}&destino=${encodeURIComponent(destino)}&validar=true`
    );
    const datos = await respuesta.json();

    if (!respuesta.ok || !datos.comparacion) {
      boton.disabled = false;
      boton.textContent = "No se pudo validar";
      return;
    }

    panel.outerHTML = tablaValidacionHTML(datos.comparacion);
  } catch (error) {
    console.error(error);
    boton.disabled = false;
    boton.textContent = "Error de conexión";
  }
}

function mostrarMensaje(texto) {
  document.getElementById("mensaje").textContent = texto || "";
}

function limpiarMensaje() {
  document.getElementById("mensaje").textContent = "";
}


/* -------------------- 7. BÚSQUEDA PRINCIPAL -------------------- */

async function buscarRuta() {
  const boton = document.getElementById("buscar");
  const origen = document.getElementById("origen").value.trim().toUpperCase();
  const destino = document.getElementById("destino").value.trim().toUpperCase();

  limpiarMensaje();
  const resultados = document.getElementById("resultados");
  resultados.innerHTML = "";

  // Validación básica en el navegador.
  if (!origen || !destino) {
    mostrarMensaje("Escribe un origen y un destino.");
    return;
  }

  boton.disabled = true;
  boton.textContent = "Buscando...";

  try {
    // Sin ?validar: la respuesta rápida, solo BFS + Dijkstra.
    const respuesta = await fetch(
      `/api/ruta?origen=${encodeURIComponent(origen)}&destino=${encodeURIComponent(destino)}`
    );

    const datos = await respuesta.json();

    if (!respuesta.ok) {
      mostrarMensaje(datos.error || "No se pudo calcular la ruta.");
      return;
    }

    ultimaBusqueda = { origen, destino };

    limpiarMapa();

    // Dibujamos Dijkstra (sólido azul) y BFS (punteado ámbar) encima.
    dibujarRuta(datos.dijkstra, "#2563eb", null);
    dibujarRuta(datos.bfs, "#d97706", "8 6");
    dibujarMarcadores(datos);

    // Ajustamos el zoom para que se vea toda la ruta. El invalidateSize()
    // va ANTES de fitBounds(): si el contenedor cambió de tamaño, Leaflet
    // necesita re-medirlo para calcular bien el encuadre.
    mapa.invalidateSize();
    const limites = capaActual.getBounds();
    if (limites.isValid()) {
      mapa.fitBounds(limites.pad(0.06));
      // Repetimos en el siguiente frame por si el layout terminó de acomodarse
      // después de este cálculo.
      requestAnimationFrame(() => {
        mapa.invalidateSize();
        mapa.fitBounds(limites.pad(0.06));
      });
    }

    mostrarResultados(datos);
  } catch (error) {
    console.error(error);
    mostrarMensaje("Error de conexión con el servidor.");
  } finally {
    boton.disabled = false;
    boton.textContent = "Buscar ruta";
  }
}


/* -------------------- 8. ARRANQUE -------------------- */

configurarBuscador("origen", "lista-origen");
configurarBuscador("destino", "lista-destino");

document.getElementById("buscar").addEventListener("click", buscarRuta);

// También permitir buscar con la tecla Enter.
["origen", "destino"].forEach((id) => {
  document.getElementById(id).addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") buscarRuta();
  });
});
