/* =========================================================================
   app.js -- Lógica del navegador: mapa, buscadores y resultados.

   Este archivo hace 3 cosas:
     1. Dibuja el mapa de OpenStreetMap con Leaflet.
     2. Autocompleta los aeropuertos consultando /api/aeropuertos.
     3. Pide la ruta a /api/ruta y dibuja BFS y Dijkstra en el mapa.
   ========================================================================= */

/* -------------------- 1. MAPA -------------------- */

// Creamos el mapa dentro del <main id="mapa"> y lo centramos mirando el mundo.
const mapa = L.map("mapa", { worldCopyJump: true }).setView([15, -30], 2);

// Capa de teselas de OpenStreetMap (el "fondo" del mapa).
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(mapa);

// Grupo de capas para poder borrar todo lo dibujado en cada nueva búsqueda.
let capaActual = L.featureGroup().addTo(mapa);


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


/* -------------------- 3. BUSCADOR CON AUTOCOMPLETADO -------------------- */

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


/* -------------------- 4. DIBUJAR EN EL MAPA -------------------- */

/** Borra todo lo dibujado en la búsqueda anterior. */
function limpiarMapa() {
  capaActual.clearLayers();
}

/** Dibuja la línea de una ruta (sin marcadores). */
function dibujarLinea(resultado, color, estiloTrazo) {
  if (!resultado.encontrada || resultado.puntos.length < 2) return;

  const puntos = resultado.puntos;
  const linea = [];

  // Convertimos cada tramo en un arco de círculo máximo.
  for (let i = 0; i < puntos.length - 1; i++) {
    const a = puntos[i];
    const b = puntos[i + 1];
    const tramo = granCirculo(a.lat, a.lon, b.lat, b.lon, 64);
    if (i > 0) tramo.shift(); // evitar punto repetido entre tramos
    linea.push(...tramo);
  }

  L.polyline(linea, {
    color: color,
    weight: 3,
    opacity: 0.9,
    dashArray: estiloTrazo || null,
  }).addTo(capaActual);
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
      color = "#16a34a"; // verde = origen
      radio = 8;
    } else if (p.iata === datos.destino.iata) {
      color = "#dc2626"; // rojo = destino
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


/* -------------------- 5. RESULTADOS -------------------- */

/** Devuelve la palabra en singular o plural según la cantidad (1 escala / 2 escalas). */
function plural(cantidad, singular, pluralForma) {
  return cantidad === 1 ? singular : pluralForma;
}

/** Genera el HTML de una tarjeta de resultado. */
function tarjetaHTML(resultado, tipo, etiqueta) {
  if (!resultado.encontrada) {
    return `<div class="tarjeta ${tipo}">
      <div class="titulo">${etiqueta}</div>
      <p>No se encontró ruta.</p>
    </div>`;
  }

  const ruta = resultado.camino.join(" → ");
  return `<div class="tarjeta ${tipo}">
    <div class="titulo">${etiqueta}</div>
    <div class="ruta-texto">${ruta}</div>
    <div class="metricas">
      <span><strong>${resultado.distancia_total_km.toLocaleString("es-PE")}</strong> km</span>
      <span><strong>${resultado.escalas}</strong> ${plural(resultado.escalas, "escala", "escalas")}</span>
      <span><strong>${resultado.tramos}</strong> ${plural(resultado.tramos, "tramo", "tramos")}</span>
      <span><strong>${resultado.tiempo_ms}</strong> ms</span>
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
      texto = `Las dos rutas son idénticas: ${bfs.escalas} ${plural(bfs.escalas, "escala", "escalas")} y la misma distancia.`;
    } else {
      texto =
        `Empate en escalas: ambas rutas tienen ${bfs.escalas} ${plural(bfs.escalas, "escala", "escalas")}. ` +
        `Dijkstra elige la de menor distancia (${diferenciaKm.toLocaleString("es-PE")} km menos). ` +
        `BFS no minimiza kilómetros: entre rutas con las mismas escalas devuelve la primera que encuentra.`;
    }
  } else if (diferenciaEscalas < 0) {
    texto =
      `BFS usa ${-diferenciaEscalas} ${plural(-diferenciaEscalas, "escala", "escalas")} menos que Dijkstra, ` +
      `pero Dijkstra recorre ${diferenciaKm.toLocaleString("es-PE")} km menos.`;
  } else {
    texto =
      `Dijkstra usa ${diferenciaEscalas} ${plural(diferenciaEscalas, "escala", "escalas")} menos que BFS ` +
      `y además recorre ${diferenciaKm.toLocaleString("es-PE")} km menos.`;
  }

  return `<div class="comparacion">${texto}</div>`;
}

function mostrarResultados(datos) {
  const contenedor = document.getElementById("resultados");
  contenedor.innerHTML =
    tarjetaHTML(datos.dijkstra, "dijkstra", "Dijkstra · menor distancia") +
    tarjetaHTML(datos.bfs, "bfs", "BFS · mínimo de escalas") +
    tarjetaComparacion(datos);
}

function mostrarMensaje(texto) {
  document.getElementById("mensaje").textContent = texto || "";
}

function limpiarMensaje() {
  document.getElementById("mensaje").textContent = "";
}


/* -------------------- 6. BÚSQUEDA PRINCIPAL -------------------- */

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
    const respuesta = await fetch(
      `/api/ruta?origen=${encodeURIComponent(origen)}&destino=${encodeURIComponent(destino)}`
    );

    const datos = await respuesta.json();

    if (!respuesta.ok) {
      mostrarMensaje(datos.error || "No se pudo calcular la ruta.");
      return;
    }

    limpiarMapa();

    // Dibujamos Dijkstra (sólido azul) y BFS (punteado naranja) encima.
    dibujarLinea(datos.dijkstra, "#2563eb", null);
    dibujarLinea(datos.bfs, "#f59e0b", "8 6");
    dibujarMarcadores(datos);

    // Ajustamos el zoom para que se vea toda la ruta.
    const limites = capaActual.getBounds();
    if (limites.isValid()) {
      mapa.fitBounds(limites.pad(0.25));
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


/* -------------------- 7. ARRANQUE -------------------- */

configurarBuscador("origen", "lista-origen");
configurarBuscador("destino", "lista-destino");

document.getElementById("buscar").addEventListener("click", buscarRuta);

// También permitir buscar con la tecla Enter.
["origen", "destino"].forEach((id) => {
  document.getElementById(id).addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") buscarRuta();
  });
});
