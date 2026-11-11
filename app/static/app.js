/* =========================================================================
   app.js -- Lógica del navegador.

   Estructura:
     1. Estado y pantallas
     2. Autocompletado de aeropuertos
     3. Búsqueda contra /api/ruta
     4. Tarjetas de vuelo
     5. Comparación y validación con Bellman-Ford
     6. Mapa con tooltips por tramo
     7. Boarding pass
     8. Ordenar, intercambiar y pasajeros
   ========================================================================= */

/* -------------------- 1. ESTADO Y PANTALLAS -------------------- */

let origen = null;   // { iata, ciudad, pais }
let destino = null;

// Última respuesta de la API. Se guarda para reordenar sin volver a pedirla.
let datosActuales = null;

// Un viaje puede tener más de un tramo: "solo ida" tiene uno, "ida y vuelta"
// tiene dos. Se guardan todos juntos para poder cambiar entre ellos sin volver
// a pedirle nada al servidor.
let legs = [];            // [{ etiqueta: "Ida" | "Vuelta", datos }]
let legActivo = 0;        // índice del tramo que se está mostrando
let tipoViaje = "solo-ida";

// Fechas mostradas en pantalla. El grafo es estático, así que no afectan el
// cálculo: sirven para que el resumen diga algo coherente.
let fechaIdaTexto = "";
let fechaVueltaTexto = "";


// Pasajeros: solo afectan el precio mostrado, no la ruta.
const pasajeros = { adultos: 1, ninos: 0, bebes: 0 };

const pantallaInicio = document.getElementById("inicio");
const pantallaResultados = document.getElementById("resultados");

function mostrarPantalla(pantalla) {
  document.querySelectorAll(".pantalla").forEach((p) => p.classList.remove("activa"));
  pantalla.classList.add("activa");
}

/* -------------------- 2. AUTOCOMPLETADO -------------------- */

function configurarBuscador(idInput, idLista, alElegir) {
  const input = document.getElementById(idInput);
  const lista = document.getElementById(idLista);
  let temporizador = null;
  let peticion = 0;      // token para descartar respuestas que llegan tarde
  let indiceActivo = -1; // sugerencia resaltada con el teclado

  const opciones = () => Array.from(lista.querySelectorAll("li"));

  function cerrar() {
    ocultarLista(lista);
    input.setAttribute("aria-expanded", "false");
    indiceActivo = -1;
  }

  function resaltar(indice) {
    const items = opciones();
    if (!items.length) return;
    indiceActivo = (indice + items.length) % items.length;
    items.forEach((item, i) => {
      const activo = i === indiceActivo;
      item.classList.toggle("activo", activo);
      item.setAttribute("aria-selected", String(activo));
    });
    items[indiceActivo].scrollIntoView({ block: "nearest" });
  }

  function elegir(a) {
    input.value = a.iata;
    peticion++;          // invalida cualquier búsqueda todavía en vuelo
    cerrar();
    alElegir(a);
  }

  input.addEventListener("input", () => {
    clearTimeout(temporizador);
    indiceActivo = -1;
    const texto = input.value.trim();

    if (texto.length < 1) {
      cerrar();
      return;
    }

    // Cada búsqueda lleva un número. Si al volver ya hay una más nueva, esta
    // respuesta se descarta: si no, una petición lenta puede pisar el
    // resultado de una posterior y la lista queda mostrando lo que no es.
    const miPeticion = ++peticion;

    temporizador = setTimeout(async () => {
      try {
        const respuesta = await fetch(
          `/api/aeropuertos?q=${encodeURIComponent(texto)}&limite=12`
        );
        const aeropuertos = await respuesta.json();
        if (miPeticion !== peticion) return;

        renderizarSugerencias(lista, aeropuertos, elegir);
        input.setAttribute("aria-expanded", String(aeropuertos.length > 0));
      } catch (error) {
        console.error("Error buscando aeropuertos:", error);
      }
    }, 200);
  });

  input.addEventListener("keydown", (evento) => {
    const abierta = lista.classList.contains("visible");
    const items = opciones();

    if (evento.key === "ArrowDown" && abierta) {
      evento.preventDefault();
      evento.stopImmediatePropagation();
      resaltar(indiceActivo + 1);
    } else if (evento.key === "ArrowUp" && abierta) {
      evento.preventDefault();
      evento.stopImmediatePropagation();
      resaltar(indiceActivo <= 0 ? items.length - 1 : indiceActivo - 1);
    } else if (evento.key === "Enter" && abierta && indiceActivo >= 0) {
      evento.preventDefault();
      evento.stopImmediatePropagation();
      elegir(items[indiceActivo].aeropuerto);
    } else if (evento.key === "Escape") {
      cerrar();
    }
  });

  input.addEventListener("blur", () => setTimeout(cerrar, 150));
}

function renderizarSugerencias(lista, aeropuertos, elegir) {
  lista.innerHTML = "";

  if (!aeropuertos.length) {
    ocultarLista(lista);
    return;
  }

  aeropuertos.forEach((a) => {
    const item = document.createElement("li");
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", "false");
    item.aeropuerto = a;

    // textContent y no innerHTML: los nombres del dataset son texto, no HTML.
    // Hay aeropuertos con "&" en el nombre ("Bill & Hillary Clinton...").
    const codigo = document.createElement("strong");
    codigo.textContent = a.iata;
    item.appendChild(codigo);
    item.appendChild(document.createTextNode(` · ${a.ciudad}`));
    const detalle = document.createElement("small");
    detalle.textContent = a.nombre;
    item.appendChild(detalle);

    item.addEventListener("mousedown", (evento) => {
      evento.preventDefault();
      elegir(a);
    });

    lista.appendChild(item);
  });

  lista.classList.add("visible");
}

function ocultarLista(lista) {
  lista.innerHTML = "";
  lista.classList.remove("visible");
}

function pintarAeropuertos() {
  document.getElementById("origen-lugar").textContent = origen
    ? `${origen.ciudad}, ${origen.pais}`
    : "";
  document.getElementById("destino-lugar").textContent = destino
    ? `${destino.ciudad}, ${destino.pais}`
    : "";

  document.getElementById("res-origen").textContent = origen ? origen.iata : "—";
  document.getElementById("res-destino").textContent = destino ? destino.iata : "—";
}

/* -------------------- 3. BÚSQUEDA -------------------- */

function mostrarMensaje(texto) {
  document.getElementById("mensaje").textContent = texto || "";
}

async function pedirRuta(iataOrigen, iataDestino) {
  const respuesta = await fetch(
    `/api/ruta?origen=${encodeURIComponent(iataOrigen)}&destino=${encodeURIComponent(iataDestino)}`
  );
  const datos = await respuesta.json();

  if (!respuesta.ok) {
    throw new Error(datos.error || "No se pudo calcular la ruta.");
  }

  return datos;
}

async function buscar() {
  const boton = document.getElementById("buscar");
  const iataOrigen = document.getElementById("origen").value.trim().toUpperCase();
  const iataDestino = document.getElementById("destino").value.trim().toUpperCase();

  mostrarMensaje("");

  if (!iataOrigen || !iataDestino) {
    mostrarMensaje("Escribe un origen y un destino.");
    return;
  }

  boton.disabled = true;
  boton.textContent = "Buscando...";

  try {
    const ida = await pedirRuta(iataOrigen, iataDestino);
    const nuevos = [{ etiqueta: "Ida", datos: ida }];

    // "Ida y vuelta" es la misma búsqueda con los aeropuertos invertidos.
    // El grafo es dirigido, así que la vuelta no es espejo de la ida: se
    // calcula de verdad y puede dar un camino distinto.
    if (tipoViaje === "ida-vuelta") {
      const vuelta = await pedirRuta(iataDestino, iataOrigen);
      nuevos.push({ etiqueta: "Vuelta", datos: vuelta });
    }

    legs = nuevos;
    legActivo = 0;
    datosActuales = legs[0].datos;
    origen = datosActuales.origen;
    destino = datosActuales.destino;

    mostrarPantalla(pantallaResultados);
    pintarAeropuertos();
    pintarPasajeros();
    pintarFechas();
    pintarSelectorTramos();

    renderizarVuelos();
    renderizarComparacion();
    renderizarValidacion();

    // El mapa vive dentro de la pantalla de resultados: recién ahora tiene
    // tamaño, así que se inicializa (o se re-mide) en este momento.
    iniciarMapa();
    dibujarTodo();
  } catch (error) {
    console.error(error);
    mostrarMensaje(error.message || "Error de conexión con el servidor.");
  } finally {
    boton.disabled = false;
    boton.textContent = "Buscar vuelos";
  }
}

/* -------------------- 3b. TRAMOS DEL VIAJE -------------------- */

/** Pinta las pestañas "Ida" / "Vuelta". Solo aparecen si hay más de un tramo. */
function pintarSelectorTramos() {
  const contenedor = document.getElementById("selector-tramos");
  if (!contenedor) return;

  if (legs.length < 2) {
    contenedor.innerHTML = "";
    contenedor.hidden = true;
    pintarTotales();
    return;
  }

  contenedor.hidden = false;
  contenedor.innerHTML = legs
    .map((leg, indice) => {
      const activo = indice === legActivo ? " activo" : "";
      const dijkstra = leg.datos.dijkstra;
      const ruta = dijkstra && dijkstra.encontrada ? dijkstra.camino.join(" → ") : "sin ruta";
      return `<button class="tramo${activo}" data-tramo="${indice}">
        <span class="tramo-etiqueta">${leg.etiqueta}</span>
        <span class="tramo-ruta">${ruta}</span>
      </button>`;
    })
    .join("");

  contenedor.querySelectorAll("[data-tramo]").forEach((boton) => {
    boton.addEventListener("click", () => cambiarTramo(Number(boton.dataset.tramo)));
  });

  pintarTotales();
}

/** Cambia el tramo visible sin volver a pedir la ruta al servidor. */
function cambiarTramo(indice) {
  if (indice === legActivo || !legs[indice]) return;

  legActivo = indice;
  datosActuales = legs[indice].datos;
  origen = datosActuales.origen;
  destino = datosActuales.destino;

  pintarSelectorTramos();
  renderizarVuelos();
  renderizarComparacion();
  renderizarValidacion();
  dibujarTodo();
}

/** Muestra el total del viaje en la barra de resumen cuando hay varios tramos. */
function pintarTotales() {
  const contenedor = document.getElementById("res-total");
  if (!contenedor) return;

  if (legs.length < 2) {
    contenedor.hidden = true;
    contenedor.textContent = "";
    return;
  }

  let km = 0;
  let minutos = 0;
  let usd = 0;
  let completa = true;

  legs.forEach(({ datos }) => {
    const dijkstra = datos.dijkstra;
    if (!dijkstra || !dijkstra.encontrada) {
      completa = false;
      return;
    }
    km += dijkstra.distancia_total_km;
    minutos += dijkstra.tiempo_total_min;
    usd += dijkstra.costo_total_usd;
  });

  contenedor.hidden = false;

  if (!completa) {
    contenedor.textContent = "Ida y vuelta · una de las dos rutas no existe";
    return;
  }

  contenedor.innerHTML =
    `Ida y vuelta · ${formatearKm(km)} km · ${formatearDuracion(minutos)} · ` +
    `<strong>${formatearPrecio(precioConPasajeros(usd))}</strong> total`;
}


/* -------------------- 4. TARJETAS DE VUELO -------------------- */

function plural(cantidad, singular, formaPlural) {
  return cantidad === 1 ? singular : formaPlural;
}

function formatearDuracion(minutos) {
  const total = Math.round(minutos);
  const horas = Math.floor(total / 60);
  const resto = total % 60;
  if (horas === 0) return `${resto} min`;
  return `${horas} h ${String(resto).padStart(2, "0")} min`;
}

function formatearKm(km) {
  return km.toLocaleString("es-PE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatearPrecio(usd) {
  return "$ " + usd.toLocaleString("es-PE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Multiplica el precio base por los pasajeros que pagan (bebés no pagan). */
function precioConPasajeros(usd) {
  const pagantes = pasajeros.adultos + pasajeros.ninos;
  return usd * Math.max(pagantes, 1);
}

/** Aclara si el monto mostrado es de una persona o el total del grupo. */
function notaPrecio() {
  const pagantes = pasajeros.adultos + pasajeros.ninos;
  return pagantes > 1 ? `total ${pagantes} pasajeros` : "estimado por pasajero";
}

/**
 * Cuánto trabajo hizo cada algoritmo, con la unidad que corresponde.
 *
 * BFS y Dijkstra cuentan NODOS visitados. Bellman-Ford no: barre todas las
 * aristas en cada pasada, así que su contador son RELAJACIONES (las veces que
 * mejoró una distancia). Mezclarlos bajo una sola etiqueta "visitados" sería
 * comparar cosas distintas, y el número de Bellman-Ford es el mismo para
 * cualquier destino porque no corta al llegar.
 */
function textoTrabajo(fila) {
  if (fila.algoritmo === "Bellman-Ford") {
    return `${fila.visitados.toLocaleString("es-PE")} relaj. · ${fila.pasadas} pasadas`;
  }
  return `${fila.visitados.toLocaleString("es-PE")} nodos`;
}

/** "Avianca - Aerovias Nacionales de Colombia" -> "Avianca". */
function nombreCorto(aerolinea) {
  if (!aerolinea) return "Aerolínea";
  return aerolinea.split(" - ")[0].trim();
}

function iniciales(aerolinea) {
  const limpio = nombreCorto(aerolinea).replace(/[^A-Za-zÁÉÍÓÚÑ]/g, "");
  return (limpio.slice(0, 2) || "··").toUpperCase();
}

/** Degradado estable por aerolínea: suma de códigos de carácter módulo 6. */
function claseBadge(aerolinea) {
  const nombre = nombreCorto(aerolinea);
  let suma = 0;
  for (let i = 0; i < nombre.length; i++) suma += nombre.charCodeAt(i);
  return `c${(suma % 6) + 1}`;
}

/**
 * Horarios de referencia. El dataset de OpenFlights NO trae itinerarios, así
 * que la hora de salida es una convención: el primer tramo sale 08:35 y cada
 * escala consume los 90 minutos del modelo de tiempo. Se rotula como
 * "horario de referencia" para no presentarlo como un dato real.
 */
const SALIDA_BASE_MIN = 8 * 60 + 35;
const TIEMPO_ESCALA_MIN = 90;

function minutosAHora(minutos) {
  // Los tiempos del modelo son decimales (290.3 min); hay que redondear antes
  // de descomponer en horas y minutos o la hora sale con decimales.
  const total = Math.round(minutos);
  const dia = Math.floor(total / (24 * 60));
  const resto = total % (24 * 60);
  const hh = String(Math.floor(resto / 60)).padStart(2, "0");
  const mm = String(resto % 60).padStart(2, "0");
  return { hora: `${hh}:${mm}`, dia };
}

function calcularHorarios(tramos) {
  const horarios = [];
  let cursor = SALIDA_BASE_MIN;

  tramos.forEach((t) => {
    const sale = cursor;
    const llega = cursor + Math.round(t.tiempo_min);
    horarios.push({
      sale: minutosAHora(sale),
      llega: minutosAHora(llega),
    });
    cursor = llega + TIEMPO_ESCALA_MIN;
  });

  return horarios;
}

/** Diagrama del trayecto con la escala ubicada en su posición proporcional. */
function diagramaHTML(camino, duracionMin, escalas, relleno) {
  const paradas = camino.slice(1, -1);
  const nodos = paradas
    .map((iata, i) => {
      const posicion = ((i + 1) / (paradas.length + 1)) * 100;
      return `<div class="parada" style="left:${posicion}%"></div>`;
    })
    .join("");

  const textoEscalas =
    escalas === 0
      ? "0 escalas"
      : `${escalas} ${plural(escalas, "escala", "escalas")} · ${paradas.join(" · ")}`;

  return `<div class="diagrama">
      <div class="duracion">${formatearDuracion(duracionMin)}</div>
      <div class="linea${relleno ? " relleno" : ""}"></div>
      <div class="nodo inicio"></div>
      ${nodos}
      <div class="nodo fin"></div>
      <div class="escalas">${textoEscalas}</div>
    </div>`;
}

function tarjetaHTML(resultado, clave, etiqueta, clasesEtiqueta) {
  const camino = resultado.camino;
  const tramos = resultado.detalle_tramos || [];
  const primero = tramos[0] || {};
  const horarios = calcularHorarios(tramos);
  const salida = horarios[0] ? horarios[0].sale : { hora: "—", dia: 0 };
  const llegada = horarios.length ? horarios[horarios.length - 1].llega : { hora: "—", dia: 0 };

  const ciudadSalida = resultado.puntos[0] ? resultado.puntos[0].ciudad : "";
  const ultimoPunto = resultado.puntos[resultado.puntos.length - 1];
  const ciudadLlegada = ultimoPunto ? ultimoPunto.ciudad : "";

  const llegadaTexto =
    llegada.dia > 0 ? `${llegada.hora}<small class="dia-siguiente">+${llegada.dia} día</small>` : llegada.hora;

  const nombre = nombreCorto(primero.aerolinea);
  const esPrincipal = clave === "dijkstra";

  return `<article class="vuelo${esPrincipal ? " principal" : ""} tarjeta ${clave}" data-ruta="${clave}">
    <div class="vuelo-cabecera">
      <div class="badge-aerolinea ${claseBadge(primero.aerolinea)}">${iniciales(primero.aerolinea)}</div>
      <div>
        <div class="vuelo-aerolinea">${nombre}</div>
        <div class="vuelo-equipo">Equipo ${primero.avion || "—"}</div>
      </div>
      <span class="etiqueta-opcion ${clasesEtiqueta}">${etiqueta}</span>
    </div>

    <div class="vuelo-trayecto">
      <div class="extremo">
        <div class="hora">${salida.hora}</div>
        <div class="iata">${camino[0]}</div>
        <div class="ciudad">${ciudadSalida}</div>
      </div>

      ${diagramaHTML(camino, resultado.tiempo_total_min, resultado.escalas, esPrincipal)}

      <div class="extremo derecha">
        <div class="hora">${llegadaTexto}</div>
        <div class="iata">${camino[camino.length - 1]}</div>
        <div class="ciudad">${ciudadLlegada}</div>
      </div>
    </div>

    <div class="ruta-texto">${camino.join(" → ")}</div>

    <div class="vuelo-pie">
      <div class="detalle">
        <strong>${formatearKm(resultado.distancia_total_km)} km</strong><br>
        ${resultado.algoritmo} · ${resultado.visitados.toLocaleString("es-PE")} visitados · ${resultado.tiempo_ms} ms
      </div>
      <div class="precio">
        <span class="monto">${formatearPrecio(precioConPasajeros(resultado.costo_total_usd))}</span>
        <span class="nota">${notaPrecio()}</span>
      </div>
      <button class="boton-ver" data-ver="${clave}">Ver</button>
    </div>
  </article>`;
}

let ordenActual = "mejor";

function ordenar(resultados) {
  const copia = [...resultados];

  if (ordenActual === "barato") {
    copia.sort((a, b) => a.costo_total_usd - b.costo_total_usd);
  } else if (ordenActual === "rapido") {
    copia.sort((a, b) => a.tiempo_total_min - b.tiempo_total_min);
  } else if (ordenActual === "escalas") {
    copia.sort((a, b) => a.escalas - b.escalas || a.distancia_total_km - b.distancia_total_km);
  } else {
    // "Mejor": Dijkstra primero, que es la ruta recomendada.
    copia.sort((a, b) => a.distancia_total_km - b.distancia_total_km);
  }

  return copia;
}

/**
 * Etiqueta honesta para la tarjeta de BFS.
 *
 * BFS garantiza la menor cantidad de escalas, pero eso no siempre significa
 * que gane: cuando hay un vuelo directo, Dijkstra también lo encuentra y
 * empatan. Afirmar "Menos escalas" siempre sería mentirle al usuario.
 */
function etiquetaBfs(bfs, dijkstra) {
  if (!dijkstra.encontrada) return "Única ruta";
  if (bfs.escalas < dijkstra.escalas) return "Menos escalas";
  if (bfs.escalas > dijkstra.escalas) return "Ruta alternativa";
  return "Mismas escalas";
}

/** Explica qué criterio se está aplicando y por qué el orden cambió (o no). */
const CRITERIOS = {
  mejor: { nombre: "distancia", valor: (r) => `${formatearKm(r.distancia_total_km)} km` },
  barato: { nombre: "precio", valor: (r) => formatearPrecio(precioConPasajeros(r.costo_total_usd)) },
  rapido: { nombre: "duración", valor: (r) => formatearDuracion(r.tiempo_total_min) },
  escalas: { nombre: "escalas", valor: (r) => `${r.escalas} ${plural(r.escalas, "escala", "escalas")}` },
};

function pintarNotaOrden() {
  const nota = document.getElementById("nota-orden");
  if (!nota) return;

  const rutas = [datosActuales.dijkstra, datosActuales.bfs].filter((r) => r.encontrada);

  if (rutas.length < 2) {
    nota.hidden = true;
    nota.textContent = "";
    return;
  }

  const criterio = CRITERIOS[ordenActual] || CRITERIOS.mejor;
  const [primera, segunda] = ordenar(rutas);
  const valorPrimera = criterio.valor(primera);
  const valorSegunda = criterio.valor(segunda);

  nota.hidden = false;

  if (valorPrimera === valorSegunda) {
    nota.textContent = `Ambas rutas empatan en ${criterio.nombre} (${valorPrimera}).`;
  } else {
    nota.textContent =
      `${criterio.nombre}: ${primera.algoritmo} ${valorPrimera} · ${segunda.algoritmo} ${valorSegunda}`;
  }
}

function renderizarVuelos() {
  const contenedor = document.getElementById("lista-vuelos");
  const rutas = [datosActuales.dijkstra, datosActuales.bfs].filter((r) => r.encontrada);
  const opciones = document.getElementById("res-opciones");

  if (opciones) {
    opciones.textContent = rutas.length
      ? `${rutas.length} ${plural(rutas.length, "opción encontrada", "opciones encontradas")}`
      : "sin rutas";
  }

  if (!rutas.length) {
    contenedor.innerHTML = `<div class="comparacion">No hay ninguna ruta entre esos dos aeropuertos.</div>`;
    pintarNotaOrden();
    return;
  }

  contenedor.innerHTML = ordenar(rutas)
    .map((r) => {
      const esDijkstra = r.algoritmo === "Dijkstra";
      return tarjetaHTML(
        r,
        esDijkstra ? "dijkstra" : "bfs",
        esDijkstra ? "Mejor opción" : etiquetaBfs(datosActuales.bfs, datosActuales.dijkstra),
        esDijkstra ? "azul" : "ambar"
      );
    })
    .join("");

  pintarNotaOrden();

  // Resaltar la ruta de la tarjeta sobre la que está el cursor.
  contenedor.querySelectorAll(".vuelo").forEach((tarjeta) => {
    const clave = tarjeta.dataset.ruta;

    tarjeta.addEventListener("mouseenter", () => {
      tarjeta.classList.add("resaltado");
      resaltar(clave, true);
      resaltar(clave === "bfs" ? "dijkstra" : "bfs", false);
    });

    tarjeta.addEventListener("mouseleave", () => {
      tarjeta.classList.remove("resaltado");
      if (visiblesBfs) {
        visiblesBfs.concat(visiblesDijkstra).forEach((l) =>
          l.setStyle({ weight: 4, opacity: 0.92 })
        );
      }
    });
  });

  // Botones "Ver" -> boarding pass.
  contenedor.querySelectorAll("[data-ver]").forEach((boton) => {
    boton.addEventListener("click", (evento) => {
      evento.stopPropagation();
      abrirBoardingPass(boton.dataset.ver);
    });
  });
}

/* -------------------- 5. COMPARACIÓN Y VALIDACIÓN -------------------- */

function renderizarComparacion() {
  const contenedor = document.getElementById("panel-comparacion");
  const { bfs, dijkstra } = datosActuales;

  if (!bfs.encontrada || !dijkstra.encontrada) {
    contenedor.innerHTML = "";
    return;
  }

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
        `<strong>Empate en escalas.</strong> Las dos rutas tienen ${bfs.escalas} ${plural(
          bfs.escalas,
          "escala",
          "escalas"
        )}, pero BFS elige la primera que encuentra: <strong>${bfs.camino.join(
          " → "
        )}</strong>, con ${formatearKm(bfs.distancia_total_km)} km. ` +
        `Dijkstra minimiza distancia y llega a <strong>${dijkstra.camino.join(
          " → "
        )}</strong> con ${formatearKm(dijkstra.distancia_total_km)} km — <strong>${formatearKm(
          diferenciaKm
        )} km menos</strong>. ` +
        `BFS no mira kilómetros, solo cantidad de tramos.`;
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

  contenedor.innerHTML = `<div class="comparacion">${texto}</div>`;
}

function renderizarValidacion() {
  document.getElementById("panel-validacion").innerHTML = `
    <div class="validacion">
      <div class="validacion-cabecera">
        <span class="etiqueta-opcion violeta">Validación</span>
        <h3>Tres algoritmos, un solo grafo</h3>
      </div>
      <p>
        Bellman-Ford recorre el mismo grafo que Dijkstra y tiene que encontrar la misma
        ruta. No compite con Dijkstra: corrobora que la elección es correcta cuando los
        pesos no son negativos. Es O(V·E), así que se ejecuta solo cuando lo pedís.
      </p>
      <button class="boton-validar" id="boton-validar">Ejecutar validación</button>
    </div>`;

  document.getElementById("boton-validar").addEventListener("click", ejecutarValidacion);
}

async function ejecutarValidacion() {
  const boton = document.getElementById("boton-validar");
  if (!boton) return;

  boton.disabled = true;
  boton.textContent = "Ejecutando Bellman-Ford...";

  try {
    const respuesta = await fetch(
      `/api/ruta?origen=${encodeURIComponent(origen.iata)}&destino=${encodeURIComponent(
        destino.iata
      )}&validar=true`
    );
    const datos = await respuesta.json();

    if (!respuesta.ok || !datos.comparacion) {
      boton.disabled = false;
      boton.textContent = "No se pudo validar";
      return;
    }

    // ¿COINCIDEN DE VERDAD?
    //   Antes el panel decía "Coinciden" sin mirar los resultados. Eso es
    //   justo lo que este panel debería demostrar, así que se compara el
    //   camino y la distancia. Con pesos no negativos los dos tienen que
    //   coincidir; si no coinciden, hay un bug y la UI tiene que decirlo.
    const comparables = datos.comparacion.every((fila) => fila.encontrada);
    const { dijkstra, bellman_ford: bellman } = datos;
    const coinciden =
      comparables &&
      bellman.camino.join(">") === dijkstra.camino.join(">") &&
      Math.abs(bellman.distancia_total_km - dijkstra.distancia_total_km) < 0.01;

    let veredicto;
    if (!comparables) {
      veredicto = "No hay ruta entre esos dos aeropuertos, así que no hay nada que validar.";
    } else if (coinciden) {
      veredicto =
        "Bellman-Ford encontró la misma ruta y la misma distancia que Dijkstra. " +
        "Hizo muchas más relajaciones y necesitó varias pasadas: es el precio de ser O(V·E).";
    } else {
      veredicto =
        "Bellman-Ford y Dijkstra NO coinciden. Con pesos no negativos los dos deben " +
        "dar la misma ruta: esto sería un error de implementación, no una diferencia de criterio.";
    }

    const filas = datos.comparacion
      .map((fila) => {
        const color =
          fila.algoritmo === "BFS" ? "ambar" : fila.algoritmo === "Dijkstra" ? "azul" : "violeta";
        return `<tr>
          <td><span class="punto ${color}"></span>${fila.algoritmo}
            <span class="ruta-mini">${fila.camino.join(" → ")}</span>
          </td>
          <td>${formatearKm(fila.distancia_total_km)}</td>
          <td>${textoTrabajo(fila)}</td>
          <td>${fila.tiempo_ms}</td>
        </tr>`;
      })
      .join("");

    document.getElementById("panel-validacion").innerHTML = `
      <div class="validacion">
        <div class="validacion-cabecera">
          <span class="etiqueta-opcion violeta">Validación</span>
          <h3>Tres algoritmos, un solo grafo</h3>
          <span class="${coinciden ? "marca-ok" : "marca-no"}">${
            comparables ? (coinciden ? "Coinciden" : "No coinciden") : "Sin ruta"
          }</span>
        </div>
        <p>${veredicto}</p>
        <table class="tabla-validacion">
          <thead>
            <tr>
              <th>Algoritmo</th>
              <th>km</th>
              <th>Trabajo</th>
              <th>ms</th>
            </tr>
          </thead>
          <tbody>${filas}</tbody>
        </table>
      </div>`;
  } catch (error) {
    console.error(error);
    boton.disabled = false;
    boton.textContent = "Error de conexión";
  }
}

/* -------------------- 6. MAPA -------------------- */

let mapa = null;
let capa = null;
let visiblesBfs = [];
let visiblesDijkstra = [];
let zonasHover = [];

function granCirculo(lat1, lon1, lat2, lon2, pasos = 64) {
  const aRad = Math.PI / 180;
  const p1 = lat1 * aRad, l1 = lon1 * aRad;
  const p2 = lat2 * aRad, l2 = lon2 * aRad;

  const d = 2 * Math.asin(
    Math.sqrt(
      Math.sin((p2 - p1) / 2) ** 2 +
      Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2
    )
  );

  if (d === 0) return [[lat1, lon1]];

  const puntos = [];
  for (let i = 0; i <= pasos; i++) {
    const f = i / pasos;
    const A = Math.sin((1 - f) * d) / Math.sin(d);
    const B = Math.sin(f * d) / Math.sin(d);

    const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
    const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
    const z = A * Math.sin(p1) + B * Math.sin(p2);

    puntos.push([
      Math.atan2(z, Math.sqrt(x * x + y * y)) / aRad,
      Math.atan2(y, x) / aRad,
    ]);
  }
  return puntos;
}

function iniciarMapa() {
  if (mapa) {
    mapa.invalidateSize();
    return;
  }

  mapa = L.map("mapa", { worldCopyJump: true, zoomControl: false }).setView([-8, -62], 3);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(mapa);

  L.control.zoom({ position: "bottomright" }).addTo(mapa);

  capa = L.featureGroup().addTo(mapa);

  window.addEventListener("resize", () => mapa.invalidateSize());
}

function tooltipTramoHTML(tramo) {
  return `
    <div class="t-titulo">${tramo.de} → ${tramo.a}</div>
    <div class="t-aerolinea">${tramo.aerolinea}</div>
    <div class="t-fila"><span>Equipo</span><span>${tramo.avion}</span></div>
    <div class="t-fila"><span>${formatearKm(tramo.km)} km</span><span>${formatearDuracion(
      tramo.tiempo_min
    )}</span></div>
    <div class="t-precio">${formatearPrecio(precioConPasajeros(tramo.costo_usd))}</div>`;
}

function dibujarRuta(resultado, color, trazo) {
  const visibles = [];

  if (!resultado.encontrada || resultado.puntos.length < 2) return visibles;

  const puntos = resultado.puntos;
  const tramos = resultado.detalle_tramos || [];

  for (let i = 0; i < puntos.length - 1; i++) {
    const a = puntos[i];
    const b = puntos[i + 1];
    const arco = granCirculo(a.lat, a.lon, b.lat, b.lon, 64);

    visibles.push(
      L.polyline(arco, {
        color,
        weight: 4,
        opacity: 0.92,
        dashArray: trazo,
        lineCap: "round",
      }).addTo(capa)
    );

    const tramo = tramos[i];
    if (tramo) {
      zonasHover.push(
        L.polyline(arco, { color, weight: 18, opacity: 0, lineCap: "round" })
          .bindTooltip(tooltipTramoHTML(tramo), {
            sticky: true,
            direction: "top",
            className: "tooltip-vuelo",
            offset: [0, -8],
          })
          .addTo(capa)
      );
    }
  }

  return visibles;
}

function dibujarMarcadores() {
  const unicos = new Map();
  [datosActuales.dijkstra, datosActuales.bfs].forEach((r) => {
    (r.puntos || []).forEach((p) => unicos.set(p.iata, p));
  });

  unicos.forEach((p) => {
    const esOrigen = p.iata === datosActuales.origen.iata;
    const esDestino = p.iata === datosActuales.destino.iata;

    L.circleMarker([p.lat, p.lon], {
      radius: esOrigen || esDestino ? 7 : 5,
      color: "#fff",
      weight: 2.5,
      fillColor: esOrigen ? "#059669" : esDestino ? "#e11d48" : "#64748b",
      fillOpacity: 1,
    })
      .bindTooltip(
        `<div class="t-titulo">${p.iata}</div>
         <div class="t-fila"><span>${p.ciudad}</span><span>${p.pais}</span></div>`,
        { direction: "top", className: "tooltip-vuelo", offset: [0, -6] }
      )
      .addTo(capa);
  });
}

function dibujarTodo() {
  if (!mapa) return;

  capa.clearLayers();
  zonasHover = [];

  visiblesDijkstra = dibujarRuta(datosActuales.dijkstra, "#2563eb", null);
  visiblesBfs = dibujarRuta(datosActuales.bfs, "#d97706", "8 6");
  dibujarMarcadores();

  mapa.invalidateSize();
  const limites = capa.getBounds();
  if (limites.isValid()) {
    mapa.fitBounds(limites.pad(0.12));
    requestAnimationFrame(() => {
      mapa.invalidateSize();
      mapa.fitBounds(limites.pad(0.12));
    });
  }
}

function resaltar(clave, activo) {
  const grupo = clave === "bfs" ? visiblesBfs : visiblesDijkstra;
  if (!grupo || !grupo.length) return;

  grupo.forEach((l) => {
    l.setStyle({ weight: activo ? 7 : 4, opacity: activo ? 1 : 0.55 });
    if (activo) l.bringToFront();
  });
}

/* -------------------- 7. BOARDING PASS -------------------- */

function abrirBoardingPass(clave) {
  const resultado = clave === "dijkstra" ? datosActuales.dijkstra : datosActuales.bfs;
  if (!resultado.encontrada) return;

  const tramos = resultado.detalle_tramos || [];
  const primero = tramos[0] || {};
  const horarios = calcularHorarios(tramos);
  const salida = horarios[0] ? horarios[0].sale : { hora: "—" };
  const llegada = horarios.length ? horarios[horarios.length - 1].llega : { hora: "—" };

  const badge = document.getElementById("bp-badge");
  badge.textContent = iniciales(primero.aerolinea);
  badge.className = `badge-aerolinea ${claseBadge(primero.aerolinea)}`;

  // Una ruta puede combinar aerolíneas: mostramos todas, no solo la primera.
  const aerolineas = [...new Set(tramos.map((t) => nombreCorto(t.aerolinea)))];
  document.getElementById("bp-aerolinea").textContent = aerolineas.join(" · ");
  const equipos = [...new Set(tramos.map((t) => t.avion).filter(Boolean))];
  document.getElementById("bp-vuelo").textContent = `Equipo ${equipos.join(" · ") || "—"}`;

  const horas = document.querySelectorAll(".bp-ruta .hora");
  horas[0].textContent = salida.hora;
  horas[1].textContent = llegada.dia > 0 ? `${llegada.hora} (+${llegada.dia})` : llegada.hora;

  const iatas = document.querySelectorAll(".bp-ruta .iata");
  iatas[0].textContent = resultado.camino[0];
  iatas[1].textContent = resultado.camino[resultado.camino.length - 1];

  const ciudades = document.querySelectorAll(".bp-ruta .ciudad");
  const primeroPunto = resultado.puntos[0];
  const ultimoPunto = resultado.puntos[resultado.puntos.length - 1];
  ciudades[0].textContent = primeroPunto ? `${primeroPunto.ciudad}, ${primeroPunto.pais}` : "";
  ciudades[1].textContent = ultimoPunto ? `${ultimoPunto.ciudad}, ${ultimoPunto.pais}` : "";

  const valores = document.querySelectorAll(".bp-grid strong");
  valores[0].textContent = `${resultado.tramos} ${plural(resultado.tramos, "tramo", "tramos")}`;
  valores[1].textContent =
    resultado.escalas === 0
      ? "directo"
      : `${resultado.escalas} · ${resultado.camino.slice(1, -1).join(", ")}`;
  valores[2].textContent = formatearDuracion(resultado.tiempo_total_min);
  valores[3].textContent = `${formatearKm(resultado.distancia_total_km)} km`;

  document.querySelector(".bp-codigo").textContent = `${resultado.camino.join("")} · ${resultado.algoritmo}`;
  document.querySelector(".bp-precio-final").innerHTML =
    `${formatearPrecio(precioConPasajeros(resultado.costo_total_usd))}<small>Total estimado</small>`;

  document.getElementById("velo").classList.add("visible");
}

/* -------------------- 8. ORDENAR, INTERCAMBIAR, PASAJEROS -------------------- */

function pintarPasajeros() {
  document.getElementById("n-adultos").textContent = pasajeros.adultos;
  document.getElementById("n-ninos").textContent = pasajeros.ninos;
  document.getElementById("n-bebes").textContent = pasajeros.bebes;

  const partes = [`${pasajeros.adultos} ${plural(pasajeros.adultos, "adulto", "adultos")}`];
  if (pasajeros.ninos > 0) partes.push(`${pasajeros.ninos} ${plural(pasajeros.ninos, "niño", "niños")}`);
  if (pasajeros.bebes > 0) partes.push(`${pasajeros.bebes} ${plural(pasajeros.bebes, "bebé", "bebés")}`);

  const texto = `${partes.join(", ")} · Economía`;
  document.getElementById("resumen-pasajeros").textContent = texto;
  document.getElementById("res-pasajeros").textContent = texto;

  document.querySelectorAll("[data-paso]").forEach((boton) => {
    const campo = boton.dataset.paso;
    const delta = Number(boton.dataset.delta);
    const minimo = campo === "adultos" ? 1 : 0;
    boton.disabled = pasajeros[campo] + delta < minimo;
  });

  // Si ya hay resultados en pantalla, el precio se recalcula al instante.
  // Hay que refrescar las dos cosas: las tarjetas y el total de ida y vuelta.
  if (datosActuales) {
    renderizarVuelos();
    pintarTotales();
  }
}

/* -------------------- ARRANQUE -------------------- */

configurarBuscador("origen", "lista-origen", (a) => {
  origen = a;
  pintarAeropuertos();
});

configurarBuscador("destino", "lista-destino", (a) => {
  destino = a;
  pintarAeropuertos();
});

document.getElementById("buscar").addEventListener("click", buscar);

["origen", "destino"].forEach((id) => {
  document.getElementById(id).addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") buscar();
  });
});

document.getElementById("intercambiar").addEventListener("click", () => {
  const campoOrigen = document.getElementById("origen");
  const campoDestino = document.getElementById("destino");
  [campoOrigen.value, campoDestino.value] = [campoDestino.value, campoOrigen.value];
  [origen, destino] = [destino, origen];
  pintarAeropuertos();
});

document.getElementById("boton-modificar").addEventListener("click", () => {
  mostrarPantalla(pantallaInicio);
});

document.querySelectorAll(".orden button").forEach((boton, indice) => {
  boton.addEventListener("click", () => {
    document.querySelectorAll(".orden button").forEach((b) => b.classList.remove("activo"));
    boton.classList.add("activo");
    ordenActual = ["mejor", "barato", "rapido", "escalas"][indice] || "mejor";
    if (datosActuales) renderizarVuelos();
  });
});

document.querySelectorAll("[data-paso]").forEach((boton) => {
  boton.addEventListener("click", () => {
    const campo = boton.dataset.paso;
    pasajeros[campo] += Number(boton.dataset.delta);
    pintarPasajeros();
  });
});

document.querySelectorAll(".tipo").forEach((boton) => {
  boton.addEventListener("click", () => {
    document.querySelectorAll(".tipo").forEach((b) => b.classList.remove("activo"));
    boton.classList.add("activo");
    tipoViaje = boton.dataset.tipo;

    // La fecha de vuelta solo tiene sentido si hay vuelta.
    const campoVuelta = document.querySelector(".campo-vuelta");
    if (campoVuelta) campoVuelta.classList.toggle("inactivo", tipoViaje !== "ida-vuelta");
  });
});

const popover = document.getElementById("popover-pasajeros");
const campoPasajeros = document.getElementById("campo-pasajeros");

campoPasajeros.addEventListener("click", (evento) => {
  if (evento.target.closest(".popover")) return;
  popover.classList.toggle("visible");
});

document.getElementById("cerrar-popover").addEventListener("click", () => {
  popover.classList.remove("visible");
});

const velo = document.getElementById("velo");
document.getElementById("cerrar").addEventListener("click", () => velo.classList.remove("visible"));
velo.addEventListener("click", (evento) => {
  if (evento.target === velo) velo.classList.remove("visible");
});
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") velo.classList.remove("visible");
});

/**
 * Las fechas son solo una comodidad de la interfaz: el grafo de OpenFlights es
 * estático (no tiene horarios ni temporadas), así que no cambian el resultado.
 */
function pintarFechas() {
  const hoy = new Date();
  const vuelta = new Date(hoy.getTime() + 7 * 24 * 60 * 60 * 1000);
  const formato = { day: "2-digit", month: "short", year: "numeric" };

  fechaIdaTexto = hoy.toLocaleDateString("es-PE", formato);
  fechaVueltaTexto = vuelta.toLocaleDateString("es-PE", formato);

  document.getElementById("fecha-ida").textContent = fechaIdaTexto;
  document.getElementById("fecha-vuelta").textContent = fechaVueltaTexto;

  // En la barra de resumen solo se muestra la vuelta si el viaje la tiene.
  document.getElementById("res-fecha").textContent =
    tipoViaje === "ida-vuelta" ? `${fechaIdaTexto} — ${fechaVueltaTexto}` : fechaIdaTexto;

  // El campo de vuelta se atenúa cuando el viaje es solo de ida.
  const campoVuelta = document.querySelector(".campo-vuelta");
  if (campoVuelta) campoVuelta.classList.toggle("inactivo", tipoViaje !== "ida-vuelta");
}

pintarFechas();
pintarAeropuertos();
pintarPasajeros();
