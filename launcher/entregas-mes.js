const log = document.getElementById("log");
const contador = document.getElementById("contador");
const campoMes = document.getElementById("mes");
const tablaResumen = document.getElementById("tabla-resumen");
const tablaGuias = document.getElementById("tabla-guias");

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
    for (const valor of [fila["OPERADOR"], fila["GUIAS ENTREGADAS"], formatoPesos(fila["VALOR RECAUDADO"])]) {
      const td = document.createElement("td");
      td.textContent = valor;
      tr.appendChild(td);
    }
    tablaResumen.appendChild(tr);
  }

  tablaGuias.innerHTML = "";
  for (const guia of resultado.guias || []) {
    const tr = document.createElement("tr");
    const valores = [
      guia.planilla, guia.guia, guia.servicio, guia.destinatario,
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

  contador.textContent = `Guias entregadas en el mes: ${(resultado.guias || []).length}`;
}

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

// Al abrir, deja seleccionado el mes actual y consulta.
(function () {
  const hoy = new Date();
  campoMes.value = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
  consultarMes();
})();
