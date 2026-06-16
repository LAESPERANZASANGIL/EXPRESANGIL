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

function mostrarPantallaOperador(nombre) {
  nombreOperador.textContent = nombre;
  pantallaLogin.classList.add("oculto");
  pantallaOperador.classList.remove("oculto");
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
  mostrarPantallaLogin();
});

document.getElementById("btn-salidas").addEventListener("click", async () => {
  const guias = document.getElementById("salidas-guias").value;
  const resultado = await llamar("/api/operador/salidas", { guias });
  if (resultado.ok) {
    document.getElementById("salidas-guias").value = "";
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
    document.getElementById("novedad-d").value = "";
  }
});

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
  ["efectivo", "Efectivo a entregar"],
];

const CAMPOS_MONEDA = new Set(["recaudado", "bancos", "nequi", "envia", "efectivo"]);

function formatoMoneda(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
}

function mostrarResumen(resumen) {
  tablaResumenBody.innerHTML = "";
  for (const [clave, etiqueta] of FILAS_RESUMEN) {
    const fila = document.createElement("tr");
    if (clave === "efectivo") {
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
  }
  resumenCierre.classList.remove("oculto");
}

document.getElementById("btn-cierre").addEventListener("click", async () => {
  const fecha = fechaTrabajo.value.trim();
  const bancos = document.getElementById("cierre-bancos").value;
  const nequi = document.getElementById("cierre-nequi").value;
  const envia = document.getElementById("cierre-envia").value;
  const resultado = await llamar("/api/operador/cierre", { fecha, bancos, nequi, envia });
  if (resultado.ok && resultado.resumen) {
    mostrarResumen(resultado.resumen);
  }
});

verificarSesion();
