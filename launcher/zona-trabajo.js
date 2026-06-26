const log = document.getElementById("log");
const tablaBody = document.getElementById("tabla-body");
const contador = document.getElementById("contador");
const buscar = document.getElementById("buscar");
const buscarCampo = document.getElementById("buscar-campo");
const filtroMunicipio = document.getElementById("filtro-municipio");
const filtroOperador = document.getElementById("filtro-operador");
const filtroEstado = document.getElementById("filtro-estado");
const filtroCausal = document.getElementById("filtro-causal");

const formGuia = document.getElementById("form-guia");
const formPlanilla = document.getElementById("form-planilla");
const formDestinatario = document.getElementById("form-destinatario");
const formDireccion = document.getElementById("form-direccion");
const formMunicipio = document.getElementById("form-municipio");
const formValor = document.getElementById("form-valor");
const formOperador = document.getElementById("form-operador");
const formEstado = document.getElementById("form-estado");
const formCausal = document.getElementById("form-causal");
const formFecha = document.getElementById("form-fecha");
const formEntrega = document.getElementById("form-entrega");

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

function fechaParaInput(valor) {
  // El input type="date" necesita YYYY-MM-DD; la base ya guarda las fechas
  // en ese formato (con u sin hora), asi que basta con quitar la hora.
  return formatoFecha(valor);
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
    if (respuesta.status === 401 || !resultado.ok) {
      guias = [];
      mostrarLog(
        "Sesion expirada o sin permisos de administrador. Vuelve a iniciar sesion desde el panel principal y vuelve a entrar a Zona de Trabajo."
      );
      renderizarTabla();
      return;
    }
    guias = resultado.guias || [];
    mostrarLog("Listo.");
  } catch (error) {
    mostrarLog("No se pudieron cargar las guias: " + error);
    guias = [];
  }
  poblarFiltrosColumna();
  renderizarTabla();
}

function poblarSelectFiltro(select, valores) {
  const actual = select.value;
  select.innerHTML = "";
  const opcionTodos = document.createElement("option");
  opcionTodos.value = "";
  opcionTodos.textContent = "Todos";
  select.appendChild(opcionTodos);
  for (const valor of valores) {
    const opcion = document.createElement("option");
    opcion.value = valor;
    opcion.textContent = valor;
    select.appendChild(opcion);
  }
  if (valores.includes(actual)) {
    select.value = actual;
  }
}

function valoresUnicos(campo) {
  const valores = new Set();
  for (const fila of guias) {
    const valor = String(fila[campo] || "").trim();
    if (valor) valores.add(valor);
  }
  return Array.from(valores).sort((a, b) => a.localeCompare(b));
}

function poblarFiltrosColumna() {
  poblarSelectFiltro(filtroMunicipio, valoresUnicos("municipio"));
  poblarSelectFiltro(filtroOperador, valoresUnicos("operador"));
  poblarSelectFiltro(filtroEstado, valoresUnicos("estado"));
  poblarSelectFiltro(filtroCausal, valoresUnicos("causal"));
}

function filasFiltradas() {
  const texto = buscar.value.trim().toUpperCase();
  let filas = guias;

  if (texto) {
    // Las guias se guardan siempre con 12 digitos (normalize_guide), pero el
    // usuario puede buscar sin los ceros iniciales.
    const textoSinCero = texto.replace(/^0+(?=\d)/, "");
    const camposSeleccionados = Array.from(buscarCampo.selectedOptions).map((opcion) => opcion.value);
    const campos = camposSeleccionados.length
      ? camposSeleccionados
      : ["planilla", "guia", "destinatario", "direccion", "municipio", "operador", "estado", "causal", "fecha", "ingreso"];
    filas = filas.filter((fila) =>
      campos.some((campo) => {
        const valor = String(fila[campo] || "").toUpperCase();
        if (campo === "guia") {
          return valor.includes(texto) || valor.includes(textoSinCero);
        }
        return valor.includes(texto);
      })
    );
  }

  const filtrosColumna = [
    ["municipio", filtroMunicipio.value],
    ["operador", filtroOperador.value],
    ["estado", filtroEstado.value],
    ["causal", filtroCausal.value],
  ];
  for (const [campo, valor] of filtrosColumna) {
    if (valor) {
      filas = filas.filter((fila) => String(fila[campo] || "") === valor);
    }
  }

  return filas;
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
  formFecha.value = fechaParaInput(fila.fecha);
  formEntrega.value = fechaParaInput(fila.ingreso);
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
buscarCampo.addEventListener("change", renderizarTabla);
filtroMunicipio.addEventListener("change", renderizarTabla);
filtroOperador.addEventListener("change", renderizarTabla);
filtroEstado.addEventListener("change", renderizarTabla);
filtroCausal.addEventListener("change", renderizarTabla);

document.getElementById("btn-limpiar-filtro").addEventListener("click", () => {
  buscar.value = "";
  Array.from(buscarCampo.options).forEach((opcion) => (opcion.selected = false));
  filtroMunicipio.value = "";
  filtroOperador.value = "";
  filtroEstado.value = "";
  filtroCausal.value = "";
  renderizarTabla();
});

document.getElementById("btn-marcar-visibles").addEventListener("click", () => {
  const filas = filasFiltradas();
  if (!filas.length) {
    mostrarLog("No hay guias visibles para marcar.");
    return;
  }
  marcadas = new Set(filas.map((fila) => fila.guia));
  renderizarTabla();
  mostrarLog(`Se marcaron ${marcadas.size} guia(s) visibles. Usa "Aplicar a marcadas" para hacer el cambio masivo.`);
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
    fecha: formFecha.value,
    entrega: formEntrega.value,
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
  formFecha.value = "";
  formEntrega.value = "";
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

document.getElementById("btn-limpiar-lista").addEventListener("click", () => {
  document.getElementById("bulk-text").value = "";
  mostrarLog("Lista de guias limpiada.");
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
