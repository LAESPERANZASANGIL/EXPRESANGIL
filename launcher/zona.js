// ----- Estado en memoria -----
let filas = [];                 // todas las guias cargadas
const marcadas = new Set();     // guias seleccionadas (por numero de guia)

const tbody = document.getElementById("tbody");
const buscar = document.getElementById("buscar");
const estado = document.getElementById("estado");
const selTodos = document.getElementById("sel-todos");

// ----- Avisos -----
function aviso(texto, tipo) {
  let cont = document.getElementById("avisos");
  if (!cont) {
    cont = document.createElement("div");
    cont.id = "avisos";
    document.body.appendChild(cont);
  }
  const el = document.createElement("div");
  el.className = "aviso " + (tipo || "info");
  el.textContent = texto;
  cont.appendChild(el);
  requestAnimationFrame(() => el.classList.add("visible"));
  setTimeout(() => {
    el.classList.remove("visible");
    setTimeout(() => el.remove(), 400);
  }, 3500);
}

// ----- Utilidades -----
function normalizarGuia(texto) {
  // Igual que normalize_guide del backend: sin guiones y sin cero inicial.
  const m = String(texto).match(/\d{6,}/g) || [];
  return m.map((g) => (g.startsWith("0") ? g.slice(1) : g));
}

function badgeEstado(valor) {
  const v = (valor || "").trim();
  const clase = v ? v.toLowerCase() : "vacio";
  const span = document.createElement("span");
  span.className = "badge " + clase;
  span.textContent = v || "-";
  return span;
}

function filasFiltradas() {
  const q = buscar.value.trim().toLowerCase();
  if (!q) return filas;
  const campos = ["guia", "destinatario", "direccion", "municipio", "operador", "estado", "causal", "planilla"];
  return filas.filter((f) => campos.some((c) => String(f[c] || "").toLowerCase().includes(q)));
}

// ----- Render -----
function celda(texto, clase) {
  const td = document.createElement("td");
  if (clase) td.className = clase;
  td.textContent = texto || "";
  td.title = texto || "";
  return td;
}

function render() {
  const visibles = filasFiltradas();
  tbody.innerHTML = "";
  const frag = document.createDocumentFragment();

  for (const f of visibles) {
    const tr = document.createElement("tr");
    tr.dataset.guia = f.guia;
    if (marcadas.has(f.guia)) tr.classList.add("marcada");

    const tdSel = document.createElement("td");
    tdSel.className = "col-sel";
    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.checked = marcadas.has(f.guia);
    chk.addEventListener("click", (e) => {
      e.stopPropagation();
      alternar(f.guia, chk.checked);
    });
    tdSel.appendChild(chk);
    tr.appendChild(tdSel);

    tr.appendChild(celda(f.planilla));
    tr.appendChild(celda(f.guia));
    tr.appendChild(celda(f.destinatario));
    tr.appendChild(celda(f.direccion));
    tr.appendChild(celda(f.municipio));
    tr.appendChild(celda(f.valor, "col-num"));
    tr.appendChild(celda(f.operador));

    const tdEstado = document.createElement("td");
    tdEstado.appendChild(badgeEstado(f.estado));
    tr.appendChild(tdEstado);

    tr.appendChild(celda(f.causal));

    tr.addEventListener("click", () => seleccionarFila(f));
    frag.appendChild(tr);
  }

  tbody.appendChild(frag);
  selTodos.checked = visibles.length > 0 && visibles.every((f) => marcadas.has(f.guia));
  actualizarEstado(visibles.length);
}

function actualizarEstado(visibles) {
  estado.innerHTML =
    `Guias visibles: <b>${visibles}</b>` +
    ` &nbsp;|&nbsp; Guardadas: <b>${filas.length}</b>` +
    ` &nbsp;|&nbsp; Marcadas: <b>${marcadas.size}</b>`;
}

function alternar(guia, marcar) {
  if (marcar) marcadas.add(guia);
  else marcadas.delete(guia);
  const tr = tbody.querySelector(`tr[data-guia="${CSS.escape(guia)}"]`);
  if (tr) tr.classList.toggle("marcada", marcar);
  actualizarEstado(filasFiltradas().length);
}

function seleccionarFila(f) {
  document.getElementById("guia-actual").value = f.guia;
  document.getElementById("in-operador").value = f.operador || "";
  document.getElementById("in-estado").value = f.estado || "";
  document.getElementById("in-causal").value = f.causal || "";
}

// ----- API -----
async function cargarGuias() {
  estado.textContent = "Cargando...";
  try {
    const r = await fetch("/api/guias");
    const data = await r.json();
    filas = data.guias || [];
    // Limpia marcadas que ya no existen.
    const existentes = new Set(filas.map((f) => f.guia));
    [...marcadas].forEach((g) => { if (!existentes.has(g)) marcadas.delete(g); });
    render();
  } catch (e) {
    estado.textContent = "No se pudo cargar la informacion.";
    aviso("No se pudo conectar con el panel.", "error");
  }
}

async function llamar(ruta, datos, nombre) {
  try {
    const r = await fetch(ruta, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos || {}),
    });
    const data = await r.json();
    aviso((nombre ? nombre + ": " : "") + (data.output || (data.ok ? "Listo." : "Error.")), data.ok ? "exito" : "error");
    return data;
  } catch (e) {
    aviso((nombre ? nombre + ": " : "") + "no se pudo conectar.", "error");
    return { ok: false };
  }
}

function guiasMarcadas() {
  return [...marcadas];
}

function valoresEdicion() {
  return {
    operador: document.getElementById("in-operador").value.trim(),
    estado: document.getElementById("in-estado").value.trim(),
    causal: document.getElementById("in-causal").value.trim(),
  };
}

// ----- Acciones: edicion / borrado de seleccionadas -----
document.getElementById("btn-aplicar-sel").addEventListener("click", async () => {
  const guias = guiasMarcadas();
  if (!guias.length) return aviso("Marca al menos una guia.", "error");
  const data = await llamar("/api/guias/actualizar", { guias, ...valoresEdicion() }, "Aplicar");
  if (data.ok) { marcadas.clear(); await cargarGuias(); }
});

document.getElementById("btn-eliminar-sel").addEventListener("click", async () => {
  const guias = guiasMarcadas();
  if (!guias.length) return aviso("Marca al menos una guia.", "error");
  if (!confirm(`Se eliminaran ${guias.length} guia(s). ¿Continuar?`)) return;
  const data = await llamar("/api/guias/eliminar", { guias }, "Eliminar");
  if (data.ok) { marcadas.clear(); await cargarGuias(); }
});

// ----- Acciones: lista masiva -----
function guiasDeLista() {
  return normalizarGuia(document.getElementById("lista-guias").value);
}

document.getElementById("btn-seleccionar-lista").addEventListener("click", () => {
  const lista = new Set(guiasDeLista());
  if (!lista.size) return aviso("Pega una lista de guias.", "error");
  const existentes = new Set(filas.map((f) => f.guia));
  let encontradas = 0;
  lista.forEach((g) => { if (existentes.has(g)) { marcadas.add(g); encontradas++; } });
  render();
  aviso(`Seleccionadas ${encontradas} de ${lista.size} guia(s).`, "exito");
});

document.getElementById("btn-aplicar-lista").addEventListener("click", async () => {
  const guias = guiasDeLista();
  if (!guias.length) return aviso("Pega una lista de guias.", "error");
  const data = await llamar("/api/guias/actualizar", { guias, ...valoresEdicion() }, "Aplicar a lista");
  if (data.ok) { document.getElementById("lista-guias").value = ""; await cargarGuias(); }
});

document.getElementById("btn-eliminar-lista").addEventListener("click", async () => {
  const guias = guiasDeLista();
  if (!guias.length) return aviso("Pega una lista de guias.", "error");
  if (!confirm(`Se eliminaran ${guias.length} guia(s) de la lista. ¿Continuar?`)) return;
  const data = await llamar("/api/guias/eliminar", { guias }, "Eliminar lista");
  if (data.ok) { document.getElementById("lista-guias").value = ""; await cargarGuias(); }
});

document.getElementById("btn-limpiar-lista").addEventListener("click", () => {
  document.getElementById("lista-guias").value = "";
});

// ----- Acciones: eliminar por criterio -----
async function eliminarPor(ruta, datos, nombre) {
  if (!confirm("Esta accion elimina guias de forma permanente. ¿Continuar?")) return;
  const data = await llamar(ruta, datos, nombre);
  if (data.ok) await cargarGuias();
}

document.getElementById("btn-del-fecha").addEventListener("click", () => {
  const fecha = document.getElementById("del-fecha").value.trim();
  if (!fecha) return aviso("Escribe una fecha.", "error");
  eliminarPor("/api/guias/eliminar-fecha", { fecha }, "Eliminar por fecha");
});

document.getElementById("btn-del-estado").addEventListener("click", () => {
  const estadoVal = document.getElementById("del-estado").value.trim();
  if (!estadoVal) return aviso("Escribe un estado.", "error");
  eliminarPor("/api/guias/eliminar-estado", { estado: estadoVal }, "Eliminar por estado");
});

document.getElementById("btn-del-operador").addEventListener("click", () => {
  const operador = document.getElementById("del-operador").value.trim();
  if (!operador) return aviso("Escribe un operador.", "error");
  eliminarPor("/api/guias/eliminar-operador", { operador }, "Eliminar por operador");
});

// ----- Informes -----
document.querySelectorAll("[data-informe]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tipo = btn.dataset.informe;
    const fecha = document.getElementById("informe-fecha").value.trim();
    llamar("/api/informe", { tipo, fecha }, btn.textContent.trim());
  });
});

// ----- Controles de tabla -----
buscar.addEventListener("input", render);
document.getElementById("btn-limpiar-filtro").addEventListener("click", () => {
  buscar.value = "";
  render();
});
document.getElementById("btn-actualizar").addEventListener("click", cargarGuias);

selTodos.addEventListener("click", () => {
  const visibles = filasFiltradas();
  const marcarTodo = selTodos.checked;
  visibles.forEach((f) => { if (marcarTodo) marcadas.add(f.guia); else marcadas.delete(f.guia); });
  render();
});

// Fecha de hoy por defecto en informes.
document.getElementById("informe-fecha").value = new Date().toISOString().slice(0, 10);

cargarGuias();
