const log = document.getElementById("log");
const dashFecha = document.getElementById("dash-fecha");

function mostrarLog(texto) {
  log.textContent = texto;
}

function hoy() {
  const ahora = new Date();
  const mes = String(ahora.getMonth() + 1).padStart(2, "0");
  const dia = String(ahora.getDate()).padStart(2, "0");
  return `${ahora.getFullYear()}-${mes}-${dia}`;
}

function formatoPesos(valor) {
  const numero = Number(valor) || 0;
  return "$ " + numero.toLocaleString("es-CO");
}

function renderizarEstados(estados) {
  const cuerpo = document.getElementById("dash-estados-body");
  cuerpo.innerHTML = "";
  for (const fila of estados) {
    const tr = document.createElement("tr");
    const tdEstado = document.createElement("td");
    tdEstado.textContent = fila.estado || "SIN ESTADO";
    const tdCantidad = document.createElement("td");
    tdCantidad.textContent = fila.cantidad;
    tr.appendChild(tdEstado);
    tr.appendChild(tdCantidad);
    cuerpo.appendChild(tr);
  }
}

function renderizarReparto(operadores) {
  const cuerpo = document.getElementById("dash-reparto-body");
  cuerpo.innerHTML = "";
  let total = 0;
  for (const fila of operadores) {
    total += fila.cantidad;
    const tr = document.createElement("tr");
    const tdOperador = document.createElement("td");
    tdOperador.textContent = fila.operador || "SIN OPERADOR";
    const tdCantidad = document.createElement("td");
    tdCantidad.textContent = fila.cantidad;
    tr.appendChild(tdOperador);
    tr.appendChild(tdCantidad);
    cuerpo.appendChild(tr);
  }
  document.getElementById("dash-total-reparto").textContent = total;
}

function renderizarFinanciero(resumen) {
  const cuerpo = document.getElementById("dash-financiero-body");
  cuerpo.innerHTML = "";
  const filas = [
    ["Recaudado (entregadas)", resumen.recaudado],
    ["Bancos", resumen.bancos],
    ["Nequi", resumen.nequi],
    ["Envia", resumen.envia],
    ["Gastos", resumen.gastos],
    ["Adelanto de salario", resumen.adelanto_salario],
    ["Efectivo recaudado (cierres del dia)", resumen.efectivo],
    ["Valor en guias todavia en reparto (R)", resumen.valor_en_reparto],
    ["Efectivo esperado del dia (recaudado + en reparto)", resumen.efectivo_esperado],
  ];
  for (const [etiqueta, valor] of filas) {
    const tr = document.createElement("tr");
    const tdEtiqueta = document.createElement("td");
    tdEtiqueta.textContent = etiqueta;
    const tdValor = document.createElement("td");
    tdValor.textContent = formatoPesos(valor);
    tr.appendChild(tdEtiqueta);
    tr.appendChild(tdValor);
    cuerpo.appendChild(tr);
  }
  document.getElementById("dash-efectivo-esperado").textContent = formatoPesos(resumen.efectivo_esperado);
}

async function cargarDashboard() {
  mostrarLog("Cargando dashboard...");
  try {
    const fecha = dashFecha.value || hoy();
    const respuesta = await fetch("/api/dashboard?fecha=" + encodeURIComponent(fecha), {
      credentials: "same-origin",
    });
    const resultado = await respuesta.json();
    if (respuesta.status === 401 || !resultado.ok) {
      mostrarLog(
        resultado.output ||
          "Sesion expirada o sin permisos de administrador. Vuelve a iniciar sesion desde el panel principal."
      );
      return;
    }
    document.getElementById("dash-total-guias").textContent = resultado.total_guias;
    renderizarEstados(resultado.estados || []);
    renderizarReparto(resultado.operadores_en_reparto || []);
    renderizarFinanciero(resultado.resumen_financiero || {});
    mostrarLog("Listo.");
  } catch (error) {
    mostrarLog("No se pudo cargar el dashboard: " + error);
  }
}

dashFecha.value = hoy();
document.getElementById("btn-dash-actualizar").addEventListener("click", cargarDashboard);

cargarDashboard();
