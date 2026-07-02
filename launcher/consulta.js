const input = document.getElementById("guia");
const boton = document.getElementById("btn-consultar");
const resultado = document.getElementById("resultado");
const titulo = document.getElementById("resultado-titulo");
const mensaje = document.getElementById("resultado-mensaje");

async function consultar() {
  const guia = input.value.trim();
  if (!guia) {
    return;
  }

  boton.disabled = true;
  try {
    const respuesta = await fetch("/api/consultar-guia?guia=" + encodeURIComponent(guia));
    const datos = await respuesta.json();

    resultado.classList.remove("oculto", "encontrada", "no-encontrada");

    if (!datos.ok) {
      titulo.textContent = "Aviso";
      mensaje.textContent = datos.mensaje || datos.output || "No se pudo consultar la guia.";
      resultado.classList.add("no-encontrada");
      return;
    }

    if (datos.encontrada) {
      titulo.textContent = "Guia " + datos.guia;
      resultado.classList.add("encontrada");
    } else {
      titulo.textContent = "Guia " + guia;
      resultado.classList.add("no-encontrada");
    }
    mensaje.textContent = datos.mensaje;
  } catch (error) {
    resultado.classList.remove("oculto");
    titulo.textContent = "Aviso";
    mensaje.textContent = "No se pudo conectar con el servidor. Intenta de nuevo.";
  } finally {
    boton.disabled = false;
  }
}

boton.addEventListener("click", consultar);
input.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter") {
    consultar();
  }
});

const btnIngresarPanel = document.getElementById("btn-ingresar-panel");
const panelAcceso = document.getElementById("panel-acceso");
const panelUsuario = document.getElementById("panel-usuario");
const panelPassword = document.getElementById("panel-password");
const btnPanelIngresar = document.getElementById("btn-panel-ingresar");
const panelError = document.getElementById("panel-error");

btnIngresarPanel.addEventListener("click", () => {
  panelAcceso.classList.toggle("oculto");
  if (!panelAcceso.classList.contains("oculto")) {
    panelUsuario.focus();
  }
});

function mostrarErrorPanel(texto) {
  panelError.textContent = texto;
  panelError.classList.remove("oculto");
}

async function ingresarPanel() {
  const usuario = panelUsuario.value.trim();
  const password = panelPassword.value;
  if (!usuario || !password) {
    mostrarErrorPanel("Escribe usuario y contrasena.");
    return;
  }

  panelError.classList.add("oculto");
  btnPanelIngresar.disabled = true;
  try {
    const respuesta = await fetch("/api/operador/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usuario, password }),
      credentials: "same-origin",
    });
    const resultado = await respuesta.json();
    panelPassword.value = "";

    if (!resultado.ok) {
      mostrarErrorPanel(resultado.output || "Usuario o contrasena incorrectos.");
      return;
    }
    if (resultado.rol !== "admin") {
      await fetch("/api/operador/logout", { method: "POST", credentials: "same-origin" });
      mostrarErrorPanel("Esta opcion es solo para el administrador.");
      return;
    }
    window.location.href = "/panel";
  } catch (error) {
    mostrarErrorPanel("No se pudo conectar con el servidor. Intenta de nuevo.");
  } finally {
    btnPanelIngresar.disabled = false;
  }
}

btnPanelIngresar.addEventListener("click", ingresarPanel);
panelPassword.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter") {
    ingresarPanel();
  }
});
