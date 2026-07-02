const pantallaLogin = document.getElementById("pantalla-login");
const pantallaOperador = document.getElementById("pantalla-operador");
const log = document.getElementById("log");
const nombreOperador = document.getElementById("nombre-operador");
const fechaTrabajo = document.getElementById("fecha-trabajo");
const resumenCierre = document.getElementById("resumen-cierre");
const tablaResumenBody = document.getElementById("tabla-resumen-body");

function mostrarLog(texto) {
  log.textContent = texto;
}

function hoy() {
  const ahora = new Date();
  const mes = String(ahora.getMonth() + 1).padStart(2, "0");
  const dia = String(ahora.getDate()).padStart(2, "0");
  return `${ahora.getFullYear()}-${mes}-${dia}`;
}

fechaTrabajo.value = hoy();

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
    return resultado;
  } catch (error) {
    mostrarLog("No se pudo conectar con el panel: " + error);
    return { ok: false };
  }
}

function limpiarCamposCierre() {
  document.getElementById("cierre-bancos").value = "";
  document.getElementById("cierre-nequi").value = "";
  document.getElementById("cierre-envia").value = "";
  document.getElementById("cierre-gastos").value = "";
  document.getElementById("cierre-adelanto").value = "";
  document.getElementById("btn-cierre").disabled = true;
}

function mostrarPantallaOperador(nombre) {
  nombreOperador.textContent = nombre;
  pantallaLogin.classList.add("oculto");
  pantallaOperador.classList.remove("oculto");
  limpiarCamposCierre();
}

function mostrarPantallaLogin() {
  pantallaOperador.classList.add("oculto");
  pantallaLogin.classList.remove("oculto");
  resumenCierre.classList.add("oculto");
}

async function verificarSesion() {
  try {
    const respuesta = await fetch("/api/operador/sesion", { credentials: "same-origin" });
    const resultado = await respuesta.json();
    if (respuesta.ok && resultado.ok) {
      mostrarPantallaOperador(resultado.nombre);
      return;
    }
  } catch (error) {
    // sin sesion activa, se muestra el login
  }
  mostrarPantallaLogin();
}

document.getElementById("btn-login").addEventListener("click", async () => {
  const usuario = document.getElementById("login-usuario").value.trim();
  const password = document.getElementById("login-password").value;
  if (!usuario || !password) {
    mostrarLog("Escribe usuario y contrasena.");
    return;
  }
  const resultado = await llamar("/api/operador/login", { usuario, password });
  if (resultado.ok) {
    document.getElementById("login-password").value = "";
    mostrarPantallaOperador(resultado.nombre);
  }
});

document.getElementById("btn-logout").addEventListener("click", async () => {
  await llamar("/api/operador/logout");
  limpiarCamposCierre();
  mostrarPantallaLogin();
});

const salidasGuias = document.getElementById("salidas-guias");
const salidasContador = document.getElementById("salidas-contador");

function actualizarContadorSalidas() {
  const coincidencias = salidasGuias.value.match(/\d{6,}/g) || [];
  salidasContador.textContent = String(coincidencias.length);
}

salidasGuias.addEventListener("input", actualizarContadorSalidas);

document.getElementById("btn-salidas").addEventListener("click", async () => {
  const guias = salidasGuias.value;
  const resultado = await llamar("/api/operador/salidas", { guias });
  if (resultado.ok) {
    salidasGuias.value = "";
    actualizarContadorSalidas();
  }
});

document.getElementById("btn-novedades").addEventListener("click", async () => {
  const ro = document.getElementById("novedad-ro").value;
  const n = document.getElementById("novedad-n").value;
  const d = document.getElementById("novedad-d").value;
  const fecha = fechaTrabajo.value.trim();
  const resultado = await llamar("/api/operador/novedades", { ro, n, d, fecha });
  if (resultado.ok) {
    document.getElementById("novedad-ro").value = "";
    document.getElementById("novedad-n").value = "";
    if (!resultado.errores_d || resultado.errores_d.length === 0) {
      document.getElementById("novedad-d").value = "";
    }
  }
});

document.getElementById("btn-informe-salidas").addEventListener("click", async () => {
  const fecha = fechaTrabajo.value.trim();
  const resultado = await llamar("/api/operador/informe-salidas", { fecha });
  if (resultado.ok && resultado.archivo) {
    window.open(`/api/operador/descargar?archivo=${encodeURIComponent(resultado.archivo)}`, "_blank");
  }
});

const DENOMINACIONES = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50];
const tablaDenominacionesBody = document.getElementById("tabla-denominaciones-body");
const subtotalContado = document.getElementById("subtotal-contado");

function construirTablaDenominaciones() {
  tablaDenominacionesBody.innerHTML = "";
  for (const denominacion of DENOMINACIONES) {
    const fila = document.createElement("tr");

    const tdDenominacion = document.createElement("td");
    tdDenominacion.textContent = formatoMoneda(denominacion);

    const tdCantidad = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.placeholder = "0";
    input.dataset.denominacion = String(denominacion);
    input.addEventListener("input", actualizarSubtotalContado);
    tdCantidad.appendChild(input);

    const tdSubtotal = document.createElement("td");
    tdSubtotal.dataset.subtotalDe = String(denominacion);
    tdSubtotal.textContent = formatoMoneda(0);

    fila.appendChild(tdDenominacion);
    fila.appendChild(tdCantidad);
    fila.appendChild(tdSubtotal);
    tablaDenominacionesBody.appendChild(fila);
  }
}

function obtenerDenominaciones() {
  const denominaciones = {};
  for (const input of tablaDenominacionesBody.querySelectorAll("input")) {
    const cantidad = Number(input.value) || 0;
    if (cantidad > 0) denominaciones[input.dataset.denominacion] = cantidad;
  }
  return denominaciones;
}

function actualizarSubtotalContado() {
  let total = 0;
  for (const input of tablaDenominacionesBody.querySelectorAll("input")) {
    const cantidad = Number(input.value) || 0;
    const denominacion = Number(input.dataset.denominacion);
    const subtotal = cantidad * denominacion;
    total += subtotal;
    const celdaSubtotal = tablaDenominacionesBody.querySelector(`[data-subtotal-de="${denominacion}"]`);
    celdaSubtotal.textContent = formatoMoneda(subtotal);
  }
  subtotalContado.textContent = formatoMoneda(total);
}

construirTablaDenominaciones();

const FILAS_RESUMEN = [
  ["gestionadas", "Guias gestionadas (salidas del dia)"],
  ["ro", "Reclama oficina (RO)"],
  ["n", "Novedades operativas (N)"],
  ["d", "Devoluciones (D)"],
  ["e", "Entregadas y recaudadas (E)"],
  ["recaudado", "Dinero recaudado"],
  ["bancos", "Dinero en bancos"],
  ["nequi", "Dinero en Nequi"],
  ["envia", "Dinero en link Envia"],
  ["gastos", "Gastos"],
  ["adelanto_salario", "Adelanto de salario"],
  ["efectivo", "Efectivo a entregar"],
  ["efectivo_contado", "Efectivo contado en caja"],
  ["diferencia", "Diferencia"],
  ["nota", "Anotacion"],
];

const CAMPOS_MONEDA = new Set([
  "recaudado", "bancos", "nequi", "envia", "gastos", "adelanto_salario",
  "efectivo", "efectivo_contado", "diferencia",
]);

function formatoMoneda(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
}

const tituloResumenCierre = document.getElementById("titulo-resumen-cierre");
const btnCierre = document.getElementById("btn-cierre");

function mostrarResumen(resumen, simulado, denominaciones) {
  tituloResumenCierre.textContent = simulado ? "Resumen del dia (simulacion, aun no se ha guardado)" : "Resumen del dia";
  tablaResumenBody.innerHTML = "";
  for (const [clave, etiqueta] of FILAS_RESUMEN) {
    if (clave === "nota" && !resumen[clave]) continue;

    const fila = document.createElement("tr");
    if (clave === "efectivo" || clave === "nota") {
      fila.classList.add("fila-efectivo");
    }

    const celdaEtiqueta = document.createElement("td");
    celdaEtiqueta.textContent = etiqueta;

    const celdaValor = document.createElement("td");
    const valor = resumen[clave];
    celdaValor.textContent = CAMPOS_MONEDA.has(clave) ? formatoMoneda(valor) : valor;

    fila.appendChild(celdaEtiqueta);
    fila.appendChild(celdaValor);
    tablaResumenBody.appendChild(fila);

    if (clave === "efectivo_contado" && denominaciones) {
      agregarDesgloseDenominaciones(denominaciones);
    }
  }
  resumenCierre.classList.remove("oculto");
}

function agregarDesgloseDenominaciones(denominaciones) {
  const entradas = DENOMINACIONES
    .map((denominacion) => [denominacion, Number(denominaciones[denominacion]) || 0])
    .filter(([, cantidad]) => cantidad > 0);
  if (!entradas.length) return;

  for (const [denominacion, cantidad] of entradas) {
    const fila = document.createElement("tr");
    fila.classList.add("fila-denominacion");

    const celdaEtiqueta = document.createElement("td");
    celdaEtiqueta.textContent = `  ${formatoMoneda(denominacion)} x ${cantidad}`;

    const celdaValor = document.createElement("td");
    celdaValor.textContent = formatoMoneda(denominacion * cantidad);

    fila.appendChild(celdaEtiqueta);
    fila.appendChild(celdaValor);
    tablaResumenBody.appendChild(fila);
  }
}

function sumarValores(texto) {
  const numeros = String(texto || "").match(/-?\d+(\.\d+)?/g) || [];
  return numeros.reduce((total, numero) => total + Number(numero), 0);
}

function datosCierre() {
  const fecha = fechaTrabajo.value.trim();
  const bancos = sumarValores(document.getElementById("cierre-bancos").value);
  const nequi = sumarValores(document.getElementById("cierre-nequi").value);
  const envia = sumarValores(document.getElementById("cierre-envia").value);
  const gastos = sumarValores(document.getElementById("cierre-gastos").value);
  const adelanto_salario = sumarValores(document.getElementById("cierre-adelanto").value);
  const denominaciones = obtenerDenominaciones();
  return { fecha, bancos, nequi, envia, gastos, adelanto_salario, denominaciones };
}

document.getElementById("btn-simular-cierre").addEventListener("click", async () => {
  const datos = datosCierre();
  const resultado = await llamar("/api/operador/cierre", { ...datos, simular: true });
  if (resultado.ok && resultado.resumen) {
    mostrarResumen(resultado.resumen, true, datos.denominaciones);
    btnCierre.disabled = false;
  }
});

btnCierre.addEventListener("click", async () => {
  if (!confirm("¿Confirmas que quieres generar el cierre del dia? Esta accion no se puede deshacer.")) return;
  const datos = datosCierre();
  const resultado = await llamar("/api/operador/cierre", { ...datos, simular: false });
  if (resultado.ok && resultado.resumen) {
    mostrarResumen(resultado.resumen, false, datos.denominaciones);
    construirTablaDenominaciones();
    limpiarCamposCierre();
    btnCierre.disabled = true;
    if (resultado.archivo_entregas) {
      window.open(`/api/operador/descargar?archivo=${encodeURIComponent(resultado.archivo_entregas)}`, "_blank");
    }
  }
});

verificarSesion();
