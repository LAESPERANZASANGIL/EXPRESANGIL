const pantallaLogin = document.getElementById("pantalla-login");
const pantallaPrincipal = document.getElementById("pantalla-principal");
const pantallaIniciar = document.getElementById("pantalla-iniciar");
const nombreUsuario = document.getElementById("nombre-usuario");
const log = document.getElementById("log");

function mostrarLog(texto) {
  log.textContent = texto;
}

function mostrarAviso(texto, tipo) {
  let contenedor = document.getElementById("avisos");
  if (!contenedor) {
    contenedor = document.createElement("div");
    contenedor.id = "avisos";
    document.body.appendChild(contenedor);
  }
  const aviso = document.createElement("div");
  aviso.className = "aviso " + (tipo || "info");
  aviso.textContent = texto;
  contenedor.appendChild(aviso);
  requestAnimationFrame(() => aviso.classList.add("visible"));
  setTimeout(() => {
    aviso.classList.remove("visible");
    setTimeout(() => aviso.remove(), 400);
  }, 4000);
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

async function llamar(ruta, datos, accion) {
  const nombre = accion || "Orden";
  mostrarLog("Procesando...");
  mostrarAviso(nombre + ": ejecutando la orden...", "info");
  try {
    const respuesta = await fetch(ruta, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos || {}),
    });
    const resultado = await respuesta.json();
    mostrarLog(resultado.output || (resultado.ok ? "Listo." : "Ocurrio un error."));
    mostrarDescargas(resultado.descargas);
    if (resultado.ok) {
      mostrarAviso(nombre + ": orden ejecutada correctamente.", "exito");
    } else {
      mostrarAviso(nombre + ": termino con errores, revisa el resultado.", "error");
    }
  } catch (error) {
    mostrarLog("No se pudo conectar con el panel: " + error);
    mostrarAviso(nombre + ": no se pudo conectar con el panel.", "error");
  }
}

function mostrarPantallaPrincipal(nombre, rol) {
  nombreUsuario.textContent = nombre + (rol === "admin" ? " (administrador)" : " (operador)");
  pantallaLogin.classList.add("oculto");
  pantallaIniciar.classList.add("oculto");
  pantallaPrincipal.classList.remove("oculto");

  for (const elemento of document.querySelectorAll(".solo-admin")) {
    elemento.classList.toggle("oculto", rol !== "admin");
  }

  actualizarCampoOperadorInforme();
}

function mostrarPantallaLogin() {
  pantallaPrincipal.classList.add("oculto");
  pantallaIniciar.classList.add("oculto");
  pantallaLogin.classList.remove("oculto");
}

const MENSAJE_SOLO_ADMIN =
  "Esta pagina es solo para el administrador. Los operadores deben ingresar desde Modulo Operadores.";

async function verificarSesion() {
  try {
    const respuesta = await fetch("/api/operador/sesion", { credentials: "same-origin" });
    const resultado = await respuesta.json();
    if (respuesta.ok && resultado.ok) {
      if (resultado.rol !== "admin") {
        await fetch("/api/operador/logout", { method: "POST", credentials: "same-origin" });
        mostrarPantallaLogin();
        mostrarLog(MENSAJE_SOLO_ADMIN);
        return;
      }
      mostrarPantallaPrincipal(resultado.nombre, resultado.rol);
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
  try {
    const respuesta = await fetch("/api/operador/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario, password }),
      credentials: "same-origin",
    });
    const resultado = await respuesta.json();
    if (resultado.ok) {
      document.getElementById("login-password").value = "";
      if (resultado.rol !== "admin") {
        await fetch("/api/operador/logout", { method: "POST", credentials: "same-origin" });
        mostrarLog(MENSAJE_SOLO_ADMIN);
        return;
      }
      mostrarPantallaPrincipal(resultado.nombre, resultado.rol);
    } else {
      mostrarLog(resultado.output || "Usuario o contrasena incorrectos.");
    }
  } catch (error) {
    mostrarLog("No se pudo conectar con el panel: " + error);
  }
});

document.getElementById("btn-logout").addEventListener("click", async () => {
  await fetch("/api/operador/logout", { method: "POST", credentials: "same-origin" });
  mostrarPantallaLogin();
});

verificarSesion();

document.getElementById("btn-iniciar").addEventListener("click", () => {
  pantallaPrincipal.classList.add("oculto");
  pantallaIniciar.classList.remove("oculto");
  mostrarLog("Listo.");
  actualizarCampoOperadorInforme();
});

document.getElementById("btn-volver").addEventListener("click", () => {
  pantallaIniciar.classList.add("oculto");
  pantallaPrincipal.classList.remove("oculto");
  mostrarLog("Listo.");
});

async function subirArchivo(archivo) {
  const formData = new FormData();
  formData.append("archivo", archivo, archivo.name);
  const respuesta = await fetch("/api/subir-archivo", {
    method: "POST",
    body: formData,
  });
  const resultado = await respuesta.json();
  if (!resultado.ok) {
    throw new Error(resultado.output || "No se pudo subir el archivo " + archivo.name);
  }
  return resultado.rutas || [];
}

document.getElementById("btn-importar").addEventListener("click", async () => {
  const archivos = document.getElementById("importar-archivo").files;
  const fecha = document.getElementById("importar-fecha").value.trim();
  if (!archivos.length) {
    mostrarLog("Selecciona uno o varios archivos a importar.");
    return;
  }

  mostrarLog("Subiendo archivos...");
  mostrarAviso("Importar: subiendo archivos...", "info");
  let rutas = [];
  try {
    for (const archivo of archivos) {
      const subidas = await subirArchivo(archivo);
      rutas = rutas.concat(subidas);
    }
  } catch (error) {
    mostrarLog("No se pudieron subir los archivos: " + error);
    mostrarAviso("Importar: no se pudieron subir los archivos.", "error");
    return;
  }

  llamar("/api/importar", { archivos: rutas, fecha }, "Importar");
});

document.getElementById("btn-exportar").addEventListener("click", () => {
  const fecha = document.getElementById("exportar-fecha").value.trim();
  llamar("/api/exportar", { fecha }, "Exportar");
});

const informeTipo = document.getElementById("informe-tipo");
const informeOperadorCampo = document.getElementById("informe-operador-campo");
const informeOperador = document.getElementById("informe-operador");

async function cargarOperadoresInforme(tipo) {
  const incluirTodos = tipo === "operador";
  const ruta = incluirTodos ? "/api/operadores-guias" : "/api/usuarios";
  try {
    const respuesta = await fetch(ruta, { credentials: "same-origin" });
    const resultado = await respuesta.json();
    if (!resultado.ok) return;
    const nombres = incluirTodos ? resultado.operadores : resultado.usuarios.map((u) => u.nombre);
    informeOperador.innerHTML = "";
    if (incluirTodos) {
      const opcionTodos = document.createElement("option");
      opcionTodos.value = "";
      opcionTodos.textContent = "Todos los operadores";
      informeOperador.appendChild(opcionTodos);
    }
    for (const nombre of nombres) {
      const opcion = document.createElement("option");
      opcion.value = nombre;
      opcion.textContent = nombre;
      informeOperador.appendChild(opcion);
    }
  } catch (error) {
    // sin operadores disponibles, el selector queda vacio
  }
}

const informeFechaCampo = document.getElementById("informe-fecha-campo");
const informeMesCampo = document.getElementById("informe-mes-campo");

function actualizarCampoOperadorInforme() {
  const esSalidas = informeTipo.value === "salidas";
  const esOperador = informeTipo.value === "operador";
  const esMensual = informeTipo.value === "mensual";
  informeOperadorCampo.classList.toggle("oculto", !esSalidas && !esOperador);
  informeFechaCampo.classList.toggle("oculto", esMensual);
  informeMesCampo.classList.toggle("oculto", !esMensual);
  if (esSalidas) {
    cargarOperadoresInforme("salidas");
  } else if (esOperador) {
    cargarOperadoresInforme("operador");
  }
}

informeTipo.addEventListener("change", actualizarCampoOperadorInforme);
actualizarCampoOperadorInforme();

document.getElementById("btn-informe").addEventListener("click", () => {
  const tipo = informeTipo.value;
  const fecha = document.getElementById("informe-fecha").value.trim();
  const nombre = informeTipo.selectedOptions[0].textContent;
  if (tipo === "salidas") {
    const operador = informeOperador.value;
    if (!operador) {
      mostrarLog("Selecciona un operador para el informe de salidas.");
      return;
    }
    llamar("/api/informe", { tipo, fecha, operador }, nombre);
    return;
  }
  if (tipo === "operador") {
    const operador = informeOperador.value;
    llamar("/api/informe", { tipo, fecha, operador }, nombre);
    return;
  }
  if (tipo === "mensual") {
    const mes = document.getElementById("informe-mes").value.trim();
    if (!mes) {
      mostrarLog("Selecciona el mes para el informe mensual.");
      return;
    }
    llamar("/api/informe", { tipo, mes }, nombre);
    return;
  }
  llamar("/api/informe", { tipo, fecha }, nombre);
});

const DENOMINACIONES = [100000, 50000, 20000, 10000, 5000, 2000, 1000, 500, 200, 100, 50];
const tablaCierreGeneralBody = document.getElementById("tabla-cierre-general-body");
const cierreGeneralSubtotal = document.getElementById("cierre-general-subtotal");
const resumenCierreGeneral = document.getElementById("resumen-cierre-general");
const tablaResumenCierreGeneralBody = document.getElementById("tabla-resumen-cierre-general-body");

function formatoMonedaCierreGeneral(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
}

function construirTablaCierreGeneral() {
  tablaCierreGeneralBody.innerHTML = "";
  for (const denominacion of DENOMINACIONES) {
    const fila = document.createElement("tr");

    const tdDenominacion = document.createElement("td");
    tdDenominacion.textContent = formatoMonedaCierreGeneral(denominacion);

    const tdCantidad = document.createElement("td");
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.placeholder = "0";
    input.dataset.denominacion = String(denominacion);
    input.addEventListener("input", actualizarSubtotalCierreGeneral);
    tdCantidad.appendChild(input);

    const tdSubtotal = document.createElement("td");
    tdSubtotal.dataset.subtotalDe = String(denominacion);
    tdSubtotal.textContent = formatoMonedaCierreGeneral(0);

    fila.appendChild(tdDenominacion);
    fila.appendChild(tdCantidad);
    fila.appendChild(tdSubtotal);
    tablaCierreGeneralBody.appendChild(fila);
  }
}

function obtenerDenominacionesCierreGeneral() {
  const denominaciones = {};
  for (const input of tablaCierreGeneralBody.querySelectorAll("input")) {
    const cantidad = Number(input.value) || 0;
    if (cantidad > 0) denominaciones[input.dataset.denominacion] = cantidad;
  }
  return denominaciones;
}

function actualizarSubtotalCierreGeneral() {
  let total = 0;
  for (const input of tablaCierreGeneralBody.querySelectorAll("input")) {
    const cantidad = Number(input.value) || 0;
    const denominacion = Number(input.dataset.denominacion);
    const subtotal = cantidad * denominacion;
    total += subtotal;
    const celdaSubtotal = tablaCierreGeneralBody.querySelector(`[data-subtotal-de="${denominacion}"]`);
    celdaSubtotal.textContent = formatoMonedaCierreGeneral(subtotal);
  }
  cierreGeneralSubtotal.textContent = formatoMonedaCierreGeneral(total);
}

construirTablaCierreGeneral();

function mostrarResumenCierreGeneral(resumen) {
  const filas = [
    ["Efectivo esperado (todos los operadores)", resumen.efectivo_esperado],
    ["Efectivo contado en caja", resumen.efectivo_contado],
    ["Diferencia", resumen.diferencia],
  ];
  tablaResumenCierreGeneralBody.innerHTML = "";
  for (const [etiqueta, valor] of filas) {
    const fila = document.createElement("tr");
    fila.classList.add("fila-efectivo");

    const celdaEtiqueta = document.createElement("td");
    celdaEtiqueta.textContent = etiqueta;
    const celdaValor = document.createElement("td");
    celdaValor.textContent = formatoMonedaCierreGeneral(valor);

    fila.appendChild(celdaEtiqueta);
    fila.appendChild(celdaValor);
    tablaResumenCierreGeneralBody.appendChild(fila);
  }
  if (resumen.nota) {
    const filaNota = document.createElement("tr");
    filaNota.classList.add("fila-efectivo");
    const celdaEtiqueta = document.createElement("td");
    celdaEtiqueta.textContent = "Anotacion";
    const celdaValor = document.createElement("td");
    celdaValor.textContent = resumen.nota;
    filaNota.appendChild(celdaEtiqueta);
    filaNota.appendChild(celdaValor);
    tablaResumenCierreGeneralBody.appendChild(filaNota);
  }
  resumenCierreGeneral.classList.remove("oculto");
}

document.getElementById("btn-cierre-general").addEventListener("click", async () => {
  const fecha = document.getElementById("cierre-general-fecha").value.trim();
  const denominaciones = obtenerDenominacionesCierreGeneral();
  mostrarLog("Procesando...");
  try {
    const respuesta = await fetch("/api/cierre-general", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fecha, denominaciones }),
    });
    const resultado = await respuesta.json();
    mostrarLog(resultado.output || (resultado.ok ? "Listo." : "Ocurrio un error."));
    if (resultado.ok && resultado.resumen) {
      mostrarResumenCierreGeneral(resultado.resumen);
    }
  } catch (error) {
    mostrarLog("No se pudo conectar con el panel: " + error);
  }
});
