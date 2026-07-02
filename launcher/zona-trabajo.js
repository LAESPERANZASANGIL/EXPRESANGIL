const log = document.getElementById("log");
const tablaBody = document.getElementById("tabla-body");
const contador = document.getElementById("contador");
const buscar = document.getElementById("buscar");
const buscarCampo = document.getElementById("buscar-campo");

// Filtros estilo Excel: campo -> Set de valores seleccionados, o null si no hay filtro activo (se muestran todos).
const filtrosExcel = {};
const CAMPOS_FILTRO_EXCEL = ["planilla", "guia", "servicio", "municipio", "operador", "estado", "causal"];
let panelFiltroActual = null;

// Orden de columna: null = sin orden; "asc"/"desc" segun la ultima columna clickeada.
let ordenColumna = null;
let ordenDireccion = null;
let ordenTipo = null;

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
const formServicio = document.getElementById("form-servicio");

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
  actualizarIconosFiltro();
  renderizarTabla();
}

function valoresUnicos(campo) {
  const valores = new Set();
  for (const fila of guias) {
    const valor = String(fila[campo] || "").trim();
    if (valor) valores.add(valor);
  }
  return Array.from(valores).sort((a, b) => a.localeCompare(b));
}

function cerrarPanelFiltroExcel() {
  if (panelFiltroActual) {
    panelFiltroActual.remove();
    panelFiltroActual = null;
    document.removeEventListener("mousedown", cerrarPanelFiltroExcelFuera);
  }
}

function cerrarPanelFiltroExcelFuera(evento) {
  if (panelFiltroActual && !panelFiltroActual.contains(evento.target)) {
    cerrarPanelFiltroExcel();
  }
}

function actualizarIconosFiltro() {
  for (const campo of CAMPOS_FILTRO_EXCEL) {
    const boton = document.querySelector(`.btn-filtro-excel[data-campo="${campo}"]`);
    if (boton) boton.classList.toggle("activo", Boolean(filtrosExcel[campo]));
  }
}

function abrirFiltroExcel(campo, boton) {
  const yaAbiertoParaEsteCampo = panelFiltroActual && panelFiltroActual.dataset.campo === campo;
  cerrarPanelFiltroExcel();
  if (yaAbiertoParaEsteCampo) return;

  const valores = valoresUnicos(campo);
  const seleccionActual = new Set(filtrosExcel[campo] || valores);

  const panel = document.createElement("div");
  panel.className = "panel-filtro-excel";
  panel.dataset.campo = campo;

  const buscarInput = document.createElement("input");
  buscarInput.type = "text";
  buscarInput.placeholder = "Buscar";
  buscarInput.className = "filtro-excel-buscar";
  panel.appendChild(buscarInput);

  const listaDiv = document.createElement("div");
  listaDiv.className = "filtro-excel-lista";
  panel.appendChild(listaDiv);

  function renderLista(textoFiltro) {
    listaDiv.innerHTML = "";
    const texto = (textoFiltro || "").trim().toUpperCase();
    const visibles = texto ? valores.filter((valor) => valor.toUpperCase().includes(texto)) : valores;

    const labelTodo = document.createElement("label");
    labelTodo.className = "filtro-excel-item filtro-excel-item-todo";
    const checkTodo = document.createElement("input");
    checkTodo.type = "checkbox";
    checkTodo.checked = visibles.length > 0 && visibles.every((valor) => seleccionActual.has(valor));
    checkTodo.addEventListener("change", () => {
      for (const valor of visibles) {
        if (checkTodo.checked) seleccionActual.add(valor);
        else seleccionActual.delete(valor);
      }
      renderLista(buscarInput.value);
    });
    labelTodo.appendChild(checkTodo);
    labelTodo.appendChild(document.createTextNode("(Seleccionar todo)"));
    listaDiv.appendChild(labelTodo);

    for (const valor of visibles) {
      const label = document.createElement("label");
      label.className = "filtro-excel-item";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = seleccionActual.has(valor);
      check.addEventListener("change", () => {
        if (check.checked) seleccionActual.add(valor);
        else seleccionActual.delete(valor);
        checkTodo.checked = visibles.every((v) => seleccionActual.has(v));
      });
      label.appendChild(check);
      label.appendChild(document.createTextNode(valor));
      listaDiv.appendChild(label);
    }
  }
  renderLista("");

  buscarInput.addEventListener("input", () => renderLista(buscarInput.value));

  const filaBotones = document.createElement("div");
  filaBotones.className = "filtro-excel-botones";

  const btnAceptar = document.createElement("button");
  btnAceptar.type = "button";
  btnAceptar.className = "filtro-excel-aceptar";
  btnAceptar.textContent = "Aceptar";
  btnAceptar.addEventListener("click", () => {
    filtrosExcel[campo] = seleccionActual.size === valores.length ? null : new Set(seleccionActual);
    actualizarIconosFiltro();
    cerrarPanelFiltroExcel();
    renderizarTabla();
  });

  const btnCancelar = document.createElement("button");
  btnCancelar.type = "button";
  btnCancelar.textContent = "Cancelar";
  btnCancelar.addEventListener("click", cerrarPanelFiltroExcel);

  filaBotones.appendChild(btnAceptar);
  filaBotones.appendChild(btnCancelar);
  panel.appendChild(filaBotones);

  document.body.appendChild(panel);
  const rect = boton.getBoundingClientRect();
  const maxLeft = window.innerWidth - panel.offsetWidth - 10;
  panel.style.position = "fixed";
  panel.style.top = `${rect.bottom + 4}px`;
  panel.style.left = `${Math.min(rect.left, Math.max(maxLeft, 10))}px`;

  panelFiltroActual = panel;
  setTimeout(() => document.addEventListener("mousedown", cerrarPanelFiltroExcelFuera), 0);
}

document.querySelectorAll(".btn-filtro-excel").forEach((boton) => {
  boton.addEventListener("click", (evento) => {
    evento.stopPropagation();
    abrirFiltroExcel(boton.dataset.campo, boton);
  });
});

document.querySelectorAll(".btn-orden").forEach((boton) => {
  boton.addEventListener("click", (evento) => {
    evento.stopPropagation();
    const campo = boton.dataset.campo;
    const tipo = boton.dataset.tipo;
    if (ordenColumna === campo) {
      ordenDireccion = ordenDireccion === "asc" ? "desc" : ordenDireccion === "desc" ? null : "asc";
      if (!ordenDireccion) ordenColumna = null;
    } else {
      ordenColumna = campo;
      ordenDireccion = "asc";
      ordenTipo = tipo;
    }
    document.querySelectorAll(".btn-orden").forEach((b) => {
      b.classList.toggle("activo", b === boton && Boolean(ordenDireccion));
      b.innerHTML = b === boton && ordenDireccion === "asc" ? "&#8593;" : b === boton && ordenDireccion === "desc" ? "&#8595;" : "&#8645;";
    });
    renderizarTabla();
  });
});

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
      : ["planilla", "guia", "servicio", "destinatario", "direccion", "municipio", "operador", "estado", "causal", "fecha", "ingreso"];
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

  for (const campo of CAMPOS_FILTRO_EXCEL) {
    const seleccion = filtrosExcel[campo];
    if (seleccion) {
      filas = filas.filter((fila) => seleccion.has(String(fila[campo] || "")));
    }
  }

  if (ordenColumna && ordenDireccion) {
    const valorOrden = (fila) =>
      ordenTipo === "numero"
        ? Number(String(fila[ordenColumna] || "0").replace(/[^0-9.-]/g, "")) || 0
        : String(fila[ordenColumna] || "");
    filas = [...filas].sort((a, b) => {
      const va = valorOrden(a);
      const vb = valorOrden(b);
      const comparacion = ordenTipo === "numero" ? va - vb : va.localeCompare(vb);
      return ordenDireccion === "asc" ? comparacion : -comparacion;
    });
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

    for (const campo of ["planilla", "guia", "servicio", "destinatario", "direccion", "municipio"]) {
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
  formServicio.value = fila.servicio || "";
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

document.getElementById("btn-limpiar-filtro").addEventListener("click", () => {
  buscar.value = "";
  Array.from(buscarCampo.options).forEach((opcion) => (opcion.selected = false));
  for (const campo of CAMPOS_FILTRO_EXCEL) {
    filtrosExcel[campo] = null;
  }
  ordenColumna = null;
  ordenDireccion = null;
  ordenTipo = null;
  document.querySelectorAll(".btn-orden").forEach((b) => {
    b.classList.remove("activo");
    b.innerHTML = "&#8645;";
  });
  actualizarIconosFiltro();
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

document.getElementById("btn-desmarcar-todas").addEventListener("click", () => {
  if (!marcadas.size) {
    mostrarLog("No hay guias marcadas.");
    return;
  }
  const cantidad = marcadas.size;
  marcadas = new Set();
  renderizarTabla();
  mostrarLog(`Se desmarcaron ${cantidad} guia(s).`);
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
    servicio: formServicio.value,
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

document.getElementById("btn-exportar-marcadas").addEventListener("click", async () => {
  const objetivo = guiasObjetivo();
  if (!objetivo.length) {
    mostrarLog("Marca o selecciona una o varias guias.");
    return;
  }
  const resultado = await llamar("/api/guias/exportar-marcadas", { guias: objetivo });
  if (resultado.ok && resultado.archivo) {
    window.open(`/api/descargar?archivo=${encodeURIComponent(resultado.archivo)}`, "_blank");
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

document.getElementById("btn-admin-revertir-dia").addEventListener("click", async () => {
  const fecha = document.getElementById("cierre-admin-fecha").value.trim();
  if (!fecha) {
    mostrarLog("Selecciona la fecha.");
    return;
  }
  if (!confirm(`¿Revertir TODOS los cierres del ${fecha}? Las guias de todos los operadores volveran a estado R y se eliminaran todos los registros de cierre de ese dia.`)) return;
  const resultado = await llamar("/api/admin/cierre/revertir-dia", { fecha });
  if (resultado.ok) await cargarGuias();
});

document.getElementById("btn-admin-revertir-cierre").addEventListener("click", async () => {
  const operador = document.getElementById("cierre-admin-operador").value.trim();
  const fecha = document.getElementById("cierre-admin-fecha").value.trim();
  if (!operador || !fecha) {
    mostrarLog("Escribe el operador y la fecha.");
    return;
  }
  if (!confirm(`¿Revertir el cierre de '${operador}' del ${fecha}? Sus guias volveran a estado R y se eliminara el registro de cierre.`)) return;
  const resultado = await llamar("/api/admin/cierre/revertir", { operador, fecha });
  if (resultado.ok) await cargarGuias();
});

document.getElementById("btn-admin-regenerar-cierre").addEventListener("click", async () => {
  const operador = document.getElementById("cierre-admin-operador").value.trim();
  const fecha = document.getElementById("cierre-admin-fecha").value.trim();
  if (!operador || !fecha) {
    mostrarLog("Escribe el operador y la fecha.");
    return;
  }
  if (!confirm(`¿Regenerar el cierre de '${operador}' del ${fecha}? Esto cerrara el dia y sobreescribira el cierre anterior si existe.`)) return;
  const bancos = document.getElementById("cierre-admin-bancos").value;
  const nequi = document.getElementById("cierre-admin-nequi").value;
  const envia = document.getElementById("cierre-admin-envia").value;
  const gastos = document.getElementById("cierre-admin-gastos").value;
  const adelanto_salario = document.getElementById("cierre-admin-adelanto").value;
  const resultado = await llamar("/api/admin/cierre/regenerar", { operador, fecha, bancos, nequi, envia, gastos, adelanto_salario });
  if (resultado.ok) {
    if (resultado.archivo_entregas) {
      window.open(`/api/descargar?archivo=${encodeURIComponent(resultado.archivo_entregas)}`, "_blank");
    }
    await cargarGuias();
  }
});

document.getElementById("btn-archivar-entregadas").addEventListener("click", async () => {
  if (!confirm("¿Cerrar el dia? TODAS las guias en estado E saldran de la zona de trabajo y pasaran al archivo del mes (consultables en Entregas del Mes).")) return;
  const resultado = await llamar("/api/admin/archivar-entregadas", {});
  if (resultado.ok) await cargarGuias();
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
