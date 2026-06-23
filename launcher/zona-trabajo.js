const log = document.getElementById("log");
const tablaBody = document.getElementById("tabla-body");
const contador = document.getElementById("contador");
const buscar = document.getElementById("buscar");

const formGuia = document.getElementById("form-guia");
const formPlanilla = document.getElementById("form-planilla");
const formDestinatario = document.getElementById("form-destinatario");
const formDireccion = document.getElementById("form-direccion");
const formMunicipio = document.getElementById("form-municipio");
const formValor = document.getElementById("form-valor");
const formOperador = document.getElementById("form-operador");
const formEstado = document.getElementById("form-estado");
const formCausal = document.getElementById("form-causal");

let guias = [];
let marcadas = new Set();
let seleccionada = null;

function mostrarLog(texto) {
  log.textContent = texto;
}

function mostrarDescargas(descargas) {
  const anterior = document.getElementById("descargas");
  if (anterior) anterior.remove();
  if (!descargas || !descargas.length) return;

  const contenedor = document.createElement("div");
  contenedor.id = "descargas";
  for (const nombre of descargas) {
    const enlace = document.createElement("a");
    enlace.className = "boton boton-accion";
    enlace.href = "/api/descargar?archivo=" + encodeURIComponent(nombre);
    enlace.textContent = "Descargar " + nombre;
    enlace.setAttribute("download", nombre);
    contenedor.appendChild(enlace);
  }
  log.insertAdjacentElement("afterend", contenedor);
}

async function llamar(ruta, datos) {
  mostrarLog("Procesando...");
  try {
    const respuesta = await fetch(ruta, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos || {}),
      credentials: "same-origin",
    });
    const resultado = await respuesta.json();
    mostrarLog(resultado.output || (resultado.ok ? "Listo." : "Ocurrio un error."));
    mostrarDescargas(resultado.descargas);
    return resultado;
  } catch (error) {
    mostrarLog("No se pudo conectar con el panel: " + error);
    return { ok: false };
  }
}

function formatoFecha(valor) {
  return String(valor || "").split(" ")[0];
}

function formatoPesos(valor) {
  const numero = Number(String(valor || "0").replace(/[^0-9.-]/g, "")) || 0;
  return "$ " + numero.toLocaleString("es-CO");
}

async function cargarGuias() {
  mostrarLog("Cargando guias...");
  try {
    const respuesta = await fetch("/api/guias", { credentials: "same-origin" });
    const resultado = await respuesta.json();
    guias = resultado.guias || [];
    mostrarLog("Listo.");
  } catch (error) {
    mostrarLog("No se pudieron cargar las guias: " + error);
    guias = [];
  }
  renderizarTabla();
}

function filasFiltradas() {
  const texto = buscar.value.trim().toUpperCase();
  if (!texto) {
    return guias;
  }
  // Las guias se guardan sin el cero inicial (normalize_guide), pero el
  // usuario puede pegar el numero tal como viene en la planilla, con cero.
  const textoSinCero = texto.replace(/^0+(?=\d)/, "");
  const campos = ["planilla", "guia", "destinatario", "direccion", "municipio", "operador", "estado", "causal"];
  return guias.filter((fila) =>
    campos.some((campo) => {
      const valor = String(fila[campo] || "").toUpperCase();
      if (campo === "guia") {
        return valor.includes(texto) || valor.includes(textoSinCero);
      }
      return valor.includes(texto);
    })
  );
}

function renderizarTabla() {
  const filas = filasFiltradas();
  tablaBody.innerHTML = "";

  for (const fila of filas) {
    const tr = document.createElement("tr");
    tr.dataset.guia = fila.guia;
    if (marcadas.has(fila.guia)) tr.classList.add("marcada");
    if (fila.guia === seleccionada) tr.classList.add("seleccionada");

    const tdCheck = document.createElement("td");
    tdCheck.textContent = marcadas.has(fila.guia) ? "[x]" : "[ ]";
    tdCheck.addEventListener("click", (evento) => {
      evento.stopPropagation();
      if (marcadas.has(fila.guia)) {
        marcadas.delete(fila.guia);
      } else {
        marcadas.add(fila.guia);
      }
      renderizarTabla();
    });
    tr.appendChild(tdCheck);

    for (const campo of ["planilla", "guia", "destinatario", "direccion", "municipio"]) {
      const td = document.createElement("td");
      td.textContent = fila[campo] || "";
      tr.appendChild(td);
    }

    const tdValor = document.createElement("td");
    tdValor.textContent = formatoPesos(fila.valor);
    tr.appendChild(tdValor);

    for (const campo of ["operador", "estado", "causal"]) {
      const td = document.createElement("td");
      td.textContent = fila[campo] || "";
      tr.appendChild(td);
    }

    for (const campo of ["fecha", "ingreso"]) {
      const td = document.createElement("td");
      td.textContent = formatoFecha(fila[campo]);
      tr.appendChild(td);
    }

    tr.addEventListener("click", () => seleccionarFila(fila));
    tablaBody.appendChild(tr);
  }

  contador.textContent =
    `Guias visibles: ${filas.length} | Guias totales: ${guias.length} | Guias marcadas: ${marcadas.size}`;
}

function seleccionarFila(fila) {
  seleccionada = fila.guia;
  formGuia.value = fila.guia;
  formPlanilla.value = fila.planilla || "";
  formDestinatario.value = fila.destinatario || "";
  formDireccion.value = fila.direccion || "";
  formMunicipio.value = fila.municipio || "";
  formValor.value = fila.valor || "";
  formOperador.value = fila.operador || "";
  formEstado.value = fila.estado || "";
  formCausal.value = fila.causal || "";
  renderizarTabla();
}

function guiasDeTexto(texto) {
  const coincidencias = texto.match(/\d{6,}/g) || [];
  return coincidencias;
}

function guiasObjetivo() {
  if (marcadas.size) return Array.from(marcadas);
  if (seleccionada) return [seleccionada];
  return [];
}

buscar.addEventListener("input", renderizarTabla);

document.getElementById("btn-limpiar-filtro").addEventListener("click", () => {
  buscar.value = "";
  renderizarTabla();
});

document.getElementById("btn-actualizar").addEventListener("click", cargarGuias);

document.getElementById("btn-guardar-una").addEventListener("click", async () => {
  const guia = formGuia.value.trim() || seleccionada;
  if (!guia) {
    mostrarLog("Escribe o selecciona una guia en la tabla.");
    return;
  }
  const resultado = await llamar("/api/guias/guardar", {
    guia,
    planilla: formPlanilla.value,
    destinatario: formDestinatario.value,
    direccion: formDireccion.value,
    municipio: formMunicipio.value,
    valor: formValor.value,
    operador: formOperador.value,
    estado: formEstado.value,
    causal: formCausal.value,
  });
  if (resultado.ok) await cargarGuias();
});

document.getElementById("btn-limpiar-campos").addEventListener("click", () => {
  seleccionada = null;
  formGuia.value = "";
  formPlanilla.value = "";
  formDestinatario.value = "";
  formDireccion.value = "";
  formMunicipio.value = "";
  formValor.value = "";
  formOperador.value = "";
  formEstado.value = "";
  formCausal.value = "";
  renderizarTabla();
});

document.getElementById("btn-aplicar-marcadas").addEventListener("click", async () => {
  const objetivo = guiasObjetivo();
  if (!objetivo.length) {
    mostrarLog("Marca o selecciona una o varias guias.");
    return;
  }
  const resultado = await llamar("/api/guias/guardar-muchas", {
    guias: objetivo,
    operador: formOperador.value,
    estado: formEstado.value,
    causal: formCausal.value,
  });
  if (resultado.ok) {
    marcadas.clear();
    await cargarGuias();
  }
});

document.getElementById("btn-eliminar-marcadas").addEventListener("click", async () => {
  const objetivo = guiasObjetivo();
  if (!objetivo.length) {
    mostrarLog("Marca o selecciona una o varias guias.");
    return;
  }
  if (!confirm(`Se eliminaran ${objetivo.length} guia(s). ¿Continuar?`)) return;
  const resultado = await llamar("/api/guias/eliminar", { guias: objetivo });
  if (resultado.ok) {
    marcadas.clear();
    seleccionada = null;
    await cargarGuias();
  }
});

document.getElementById("btn-marcar-lista").addEventListener("click", () => {
  const lista = guiasDeTexto(document.getElementById("bulk-text").value);
  if (!lista.length) {
    mostrarLog("Pega o escribe una lista de guias.");
    return;
  }
  marcadas = new Set(lista);
  renderizarTabla();
  mostrarLog(`Guias marcadas: ${marcadas.size}`);
});

document.getElementById("btn-aplicar-lista").addEventListener("click", async () => {
  const lista = guiasDeTexto(document.getElementById("bulk-text").value);
  if (!lista.length) {
    mostrarLog("Pega o escribe una lista de guias.");
    return;
  }
  const resultado = await llamar("/api/guias/guardar-muchas", {
    guias: lista,
    operador: formOperador.value,
    estado: formEstado.value,
    causal: formCausal.value,
  });
  if (resultado.ok) {
    document.getElementById("bulk-text").value = "";
    await cargarGuias();
  }
});

document.getElementById("btn-eliminar-lista").addEventListener("click", async () => {
  const lista = guiasDeTexto(document.getElementById("bulk-text").value);
  if (!lista.length) {
    mostrarLog("Pega o escribe una lista de guias.");
    return;
  }
  if (!confirm(`Se eliminaran ${lista.length} guia(s) de la lista. ¿Continuar?`)) return;
  const resultado = await llamar("/api/guias/eliminar", { guias: lista });
  if (resultado.ok) {
    document.getElementById("bulk-text").value = "";
    await cargarGuias();
  }
});

document.getElementById("btn-eliminar-fecha").addEventListener("click", async () => {
  const fecha = document.getElementById("del-fecha").value.trim();
  if (!fecha) {
    mostrarLog("Escribe una fecha en formato YYYY-MM-DD.");
    return;
  }
  if (!confirm(`Se eliminaran todas las guias con fecha ${fecha}. ¿Continuar?`)) return;
  const resultado = await llamar("/api/guias/eliminar-fecha", { fecha });
  if (resultado.ok) {
    document.getElementById("del-fecha").value = "";
    await cargarGuias();
  }
});

document.getElementById("btn-eliminar-estado").addEventListener("click", async () => {
  const estado = document.getElementById("del-estado").value.trim();
  if (!estado) {
    mostrarLog("Escribe un estado.");
    return;
  }
  if (!confirm(`Se eliminaran todas las guias con estado '${estado}'. ¿Continuar?`)) return;
  const resultado = await llamar("/api/guias/eliminar-estado", { estado });
  if (resultado.ok) {
    document.getElementById("del-estado").value = "";
    await cargarGuias();
  }
});

document.getElementById("btn-eliminar-operador").addEventListener("click", async () => {
  const operador = document.getElementById("del-operador").value.trim();
  if (!operador) {
    mostrarLog("Escribe un operador.");
    return;
  }
  if (!confirm(`Se eliminaran todas las guias del operador '${operador}'. ¿Continuar?`)) return;
  const resultado = await llamar("/api/guias/eliminar-operador", { operador });
  if (resultado.ok) {
    document.getElementById("del-operador").value = "";
    await cargarGuias();
  }
});

const informeTipo = document.getElementById("informe-tipo");
const informeOperadorCampo = document.getElementById("informe-operador-campo");
const informeOperador = document.getElementById("informe-operador");

async function cargarOperadoresInforme() {
  try {
    const respuesta = await fetch("/api/operadores-guias", { credentials: "same-origin" });
    const resultado = await respuesta.json();
    if (!resultado.ok) return;
    informeOperador.innerHTML = "";
    const opcionTodos = document.createElement("option");
    opcionTodos.value = "";
    opcionTodos.textContent = "Todos los operadores";
    informeOperador.appendChild(opcionTodos);
    for (const nombre of resultado.operadores) {
      const opcion = document.createElement("option");
      opcion.value = nombre;
      opcion.textContent = nombre;
      informeOperador.appendChild(opcion);
    }
  } catch (error) {
    // sin operadores disponibles, el selector queda vacio
  }
}

function actualizarCampoOperadorInforme() {
  const esOperador = informeTipo.value === "operador";
  informeOperadorCampo.classList.toggle("oculto", !esOperador);
  if (esOperador) {
    cargarOperadoresInforme();
  }
}

informeTipo.addEventListener("change", actualizarCampoOperadorInforme);
actualizarCampoOperadorInforme();

document.getElementById("btn-informe").addEventListener("click", async () => {
  const tipo = informeTipo.value;
  const fecha = document.getElementById("informe-fecha").value.trim();
  const datos = { tipo, fecha };
  if (tipo === "operador") {
    datos.operador = informeOperador.value;
  }
  await llamar("/api/informe", datos);
});

cargarGuias();
