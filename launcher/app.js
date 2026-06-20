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
}

function mostrarPantallaLogin() {
  pantallaPrincipal.classList.add("oculto");
  pantallaIniciar.classList.add("oculto");
  pantallaLogin.classList.remove("oculto");
}

async function verificarSesion() {
  try {
    const respuesta = await fetch("/api/operador/sesion", { credentials: "same-origin" });
    const resultado = await respuesta.json();
    if (respuesta.ok && resultado.ok) {
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

document.getElementById("btn-informe").addEventListener("click", () => {
  const tipo = document.getElementById("informe-tipo").value;
  const fecha = document.getElementById("informe-fecha").value.trim();
  const nombre = document.getElementById("informe-tipo").selectedOptions[0].textContent;
  llamar("/api/informe", { tipo, fecha }, nombre);
});
