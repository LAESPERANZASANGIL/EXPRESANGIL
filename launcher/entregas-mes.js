const log = document.getElementById("log");
const contador = document.getElementById("contador");
const campoMes = document.getElementById("mes");
const tablaResumen = document.getElementById("tabla-resumen");
const tablaGuias = document.getElementById("tabla-guias");
const buscarGuia = document.getElementById("buscar-guia");

let guiasMes = [];

function mostrarLog(texto) {
  log.textContent = texto;
}

function formatoPesos(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
}

function formatoFecha(valor) {
  return String(valor || "").slice(0, 10);
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
  log.parentElement.insertBefore(contenedor, log);
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

function mesSeleccionado() {
  const mes = campoMes.value.trim();
  if (!mes) {
    mostrarLog("Selecciona el mes a consultar.");
    return null;
  }
  return mes;
}

async function consultarMes() {
  const mes = mesSeleccionado();
  if (!mes) return;
  const resultado = await llamar("/api/admin/entregas-mes", { mes });
  if (!resultado.ok) return;

  tablaResumen.innerHTML = "";
  for (const fila of resultado.resumen || []) {
    const tr = document.createElement("tr");
    const esTotal = fila["OPERADOR"] === "TOTAL" || fila["OPERADOR"] === "PROMEDIO POR EMPLEADO";
    if (esTotal) tr.style.fontWeight = "bold";
    for (const valor of [fila["OPERADOR"], fila["GUIAS ENTREGADAS"], fila["UNIDADES ENTREGADAS"], formatoPesos(fila["VALOR RECAUDADO"])]) {
      const td = document.createElement("td");
      td.textContent = valor;
      tr.appendChild(td);
    }
    tablaResumen.appendChild(tr);
  }

  guiasMes = resultado.guias || [];
  renderizarGuias();
}

function renderizarGuias() {
  const texto = buscarGuia.value.trim().toUpperCase();
  // Las guias se guardan con 12 digitos, pero se puede buscar sin los ceros iniciales.
  const textoSinCero = texto.replace(/^0+(?=\d)/, "");
  const filtradas = !texto
    ? guiasMes
    : guiasMes.filter((guia) => {
        const numero = String(guia.guia || "").toUpperCase();
        if (numero.includes(texto) || numero.includes(textoSinCero)) return true;
        return [guia.destinatario, guia.municipio, guia.operador, guia.planilla]
          .some((campo) => String(campo || "").toUpperCase().includes(texto));
      });

  tablaGuias.innerHTML = "";
  for (const guia of filtradas) {
    const tr = document.createElement("tr");
    const valores = [
      guia.planilla, guia.guia, guia.unid, guia.servicio, guia.destinatario,
      guia.direccion, guia.municipio, formatoPesos(guia.valor),
      guia.operador, formatoFecha(guia.entrega),
    ];
    for (const valor of valores) {
      const td = document.createElement("td");
      td.textContent = valor || "";
      tr.appendChild(td);
    }
    tablaGuias.appendChild(tr);
  }

  contador.textContent = texto
    ? `Guias visibles: ${filtradas.length} de ${guiasMes.length} entregadas en el mes`
    : `Guias entregadas en el mes: ${guiasMes.length}`;
}

buscarGuia.addEventListener("input", renderizarGuias);

document.getElementById("btn-limpiar-busqueda").addEventListener("click", () => {
  buscarGuia.value = "";
  renderizarGuias();
});

document.getElementById("btn-consultar").addEventListener("click", consultarMes);

document.getElementById("btn-informe-excel").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (!mes) return;
  await llamar("/api/admin/entregas-mes/informe", { mes, formato: "excel" });
});

document.getElementById("btn-informe-pdf").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (!mes) return;
  await llamar("/api/admin/entregas-mes/informe", { mes, formato: "pdf" });
});

document.getElementById("btn-eliminar-mes").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (!mes) return;
  if (!confirm(`¿Borrar TODAS las guias entregadas de ${mes}? Se eliminan del archivo historico y de la zona de trabajo.`)) return;
  if (!confirm("Esta accion es definitiva y no se puede deshacer desde el panel (queda un respaldo automatico de la base). ¿Confirmas?")) return;
  const resultado = await llamar("/api/admin/entregas-mes/eliminar", { mes });
  if (resultado.ok) await consultarMes();
});

const rendimientoOperador = document.getElementById("rendimiento-operador");

async function cargarOperadores() {
  try {
    const respuesta = await fetch("/api/operadores-guias", { credentials: "same-origin" });
    const resultado = await respuesta.json();
    if (!resultado.ok) return;
    rendimientoOperador.innerHTML = "";
    for (const nombre of resultado.operadores) {
      const opcion = document.createElement("option");
      opcion.value = nombre;
      opcion.textContent = nombre;
      rendimientoOperador.appendChild(opcion);
    }
  } catch (error) {
    // sin operadores disponibles, el selector queda vacio
  }
}

document.getElementById("btn-rendimiento-operador").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (!mes) return;
  const operador = rendimientoOperador.value;
  if (!operador) {
    mostrarLog("Selecciona el operador.");
    return;
  }
  await llamar("/api/admin/rendimiento-mensual", { mes, operador });
});

document.getElementById("btn-rendimiento-todos").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (!mes) return;
  await llamar("/api/admin/rendimiento-mensual", { mes });
});

// Al abrir, deja seleccionado el mes actual y consulta.
(function () {
  const hoy = new Date();
  campoMes.value = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
  consultarMes();
  cargarOperadores();
})();
