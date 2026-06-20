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
