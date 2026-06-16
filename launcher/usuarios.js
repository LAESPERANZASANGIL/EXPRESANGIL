const pantallaBootstrap = document.getElementById("pantalla-bootstrap");
const pantallaLogin = document.getElementById("pantalla-login");
const pantallaAdmin = document.getElementById("pantalla-admin");
const log = document.getElementById("log");
const nombreAdmin = document.getElementById("nombre-admin");
const tablaUsuariosBody = document.getElementById("tabla-usuarios-body");

let usuarioActual = "";

function mostrarLog(texto) {
  log.textContent = texto;
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
    return resultado;
  } catch (error) {
    mostrarLog("No se pudo conectar con el panel: " + error);
    return { ok: false };
  }
}

function mostrarPantalla(pantalla) {
  for (const seccion of [pantallaBootstrap, pantallaLogin, pantallaAdmin]) {
    seccion.classList.toggle("oculto", seccion !== pantalla);
  }
}

async function cargarUsuarios() {
  try {
    const respuesta = await fetch("/api/usuarios", { credentials: "same-origin" });
    const resultado = await respuesta.json();
    if (!respuesta.ok || !resultado.ok) {
      return;
    }
    tablaUsuariosBody.innerHTML = "";
    for (const usuario of resultado.usuarios) {
      const fila = document.createElement("tr");

      const celdaUsuario = document.createElement("td");
      celdaUsuario.textContent = usuario.usuario;

      const celdaNombre = document.createElement("td");
      celdaNombre.textContent = usuario.nombre;

      const celdaRol = document.createElement("td");
      celdaRol.textContent = usuario.rol === "admin" ? "Administrador" : "Operador";
      if (usuario.rol === "admin") {
        celdaRol.classList.add("rol-admin");
      }

      const celdaAcciones = document.createElement("td");
      if (usuario.usuario !== usuarioActual) {
        const botonEliminar = document.createElement("button");
        botonEliminar.textContent = "Eliminar";
        botonEliminar.className = "boton-eliminar";
        botonEliminar.addEventListener("click", async () => {
          if (!confirm(`¿Eliminar el usuario '${usuario.usuario}'?`)) {
            return;
          }
          const resultado = await llamar("/api/usuarios/eliminar", { usuario: usuario.usuario });
          if (resultado.ok) {
            await cargarUsuarios();
          }
        });
        celdaAcciones.appendChild(botonEliminar);
      }

      fila.appendChild(celdaUsuario);
      fila.appendChild(celdaNombre);
      fila.appendChild(celdaRol);
      fila.appendChild(celdaAcciones);
      tablaUsuariosBody.appendChild(fila);
    }
  } catch (error) {
    mostrarLog("No se pudo cargar la lista de usuarios: " + error);
  }
}

async function mostrarPantallaAdmin(nombre) {
  nombreAdmin.textContent = nombre;
  mostrarPantalla(pantallaAdmin);
  await cargarUsuarios();
}

async function iniciar() {
  try {
    const estado = await fetch("/api/usuarios/estado", { credentials: "same-origin" });
    const resultadoEstado = await estado.json();
    if (!resultadoEstado.hay_admin) {
      mostrarPantalla(pantallaBootstrap);
      return;
    }

    const sesion = await fetch("/api/operador/sesion", { credentials: "same-origin" });
    const resultadoSesion = await sesion.json();
    if (sesion.ok && resultadoSesion.ok && resultadoSesion.rol === "admin") {
      usuarioActual = resultadoSesion.usuario;
      await mostrarPantallaAdmin(resultadoSesion.nombre);
      return;
    }
  } catch (error) {
    // sin conexion o sin sesion: se muestra el login
  }
  mostrarPantalla(pantallaLogin);
}

document.getElementById("btn-bootstrap").addEventListener("click", async () => {
  const usuario = document.getElementById("boot-usuario").value.trim();
  const password = document.getElementById("boot-password").value;
  const nombre = document.getElementById("boot-nombre").value.trim();
  if (!usuario || !password || !nombre) {
    mostrarLog("Completa usuario, contrasena y nombre.");
    return;
  }
  const resultado = await llamar("/api/usuarios/crear", {
    usuario,
    password,
    nombre,
    rol: "admin",
  });
  if (resultado.ok) {
    mostrarLog("Administrador creado. Ahora inicia sesion.");
    document.getElementById("login-usuario").value = usuario;
    mostrarPantalla(pantallaLogin);
  }
});

document.getElementById("btn-login").addEventListener("click", async () => {
  const usuario = document.getElementById("login-usuario").value.trim();
  const password = document.getElementById("login-password").value;
  if (!usuario || !password) {
    mostrarLog("Escribe usuario y contrasena.");
    return;
  }
  const resultado = await llamar("/api/operador/login", { usuario, password });
  if (!resultado.ok) {
    return;
  }
  if (resultado.rol !== "admin") {
    await llamar("/api/operador/logout");
    mostrarLog("Este modulo es solo para administradores.");
    return;
  }
  document.getElementById("login-password").value = "";
  usuarioActual = usuario;
  await mostrarPantallaAdmin(resultado.nombre);
});

document.getElementById("btn-logout").addEventListener("click", async () => {
  await llamar("/api/operador/logout");
  usuarioActual = "";
  mostrarPantalla(pantallaLogin);
});

document.getElementById("btn-crear").addEventListener("click", async () => {
  const usuario = document.getElementById("nuevo-usuario").value.trim();
  const password = document.getElementById("nuevo-password").value;
  const nombre = document.getElementById("nuevo-nombre").value.trim();
  const rol = document.getElementById("nuevo-rol").value;
  if (!usuario || !password || !nombre) {
    mostrarLog("Completa usuario, contrasena y nombre.");
    return;
  }
  const resultado = await llamar("/api/usuarios/crear", { usuario, password, nombre, rol });
  if (resultado.ok) {
    document.getElementById("nuevo-usuario").value = "";
    document.getElementById("nuevo-password").value = "";
    document.getElementById("nuevo-nombre").value = "";
    document.getElementById("nuevo-rol").value = "operador";
    await cargarUsuarios();
  }
});

iniciar();
