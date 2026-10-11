// Avisos y descargas, compartidos por todas las pantallas del panel.
//
// Antes cada pagina repetia estas tres funciones y escribia el resultado en un
// recuadro negro fijo al pie, que ocupaba espacio y no se veia bien. Ahora el
// mensaje sale como aviso flotante y el archivo se descarga solo, sin que haya
// que buscar un boton.

function mostrarAviso(texto, tipo) {
  let contenedor = document.getElementById("avisos");
  if (!contenedor) {
    contenedor = document.createElement("div");
    contenedor.id = "avisos";
    document.body.appendChild(contenedor);
  }

  const aviso = document.createElement("div");
  aviso.className = "aviso " + (tipo || "info");

  const mensaje = document.createElement("span");
  mensaje.className = "aviso-texto";
  mensaje.textContent = texto;
  aviso.appendChild(mensaje);

  const cerrar = document.createElement("button");
  cerrar.type = "button";
  cerrar.className = "aviso-cerrar";
  cerrar.textContent = "×";
  cerrar.title = "Cerrar";
  cerrar.addEventListener("click", () => quitarAviso(aviso));
  aviso.appendChild(cerrar);

  contenedor.appendChild(aviso);
  requestAnimationFrame(() => aviso.classList.add("visible"));

  // Un error hay que poder leerlo con calma: se queda hasta que lo cierren.
  // Lo demas se va solo para no estorbar.
  if (tipo !== "error") {
    setTimeout(() => quitarAviso(aviso), 4000);
  }
  return aviso;
}

function quitarAviso(aviso) {
  if (!aviso || !aviso.isConnected) return;
  aviso.classList.remove("visible");
  setTimeout(() => aviso.remove(), 400);
}

/** El resultado de una orden. Reemplaza al recuadro negro del pie. */
function mostrarLog(texto, tipo) {
  const limpio = String(texto == null ? "" : texto).trim();
  if (!limpio || limpio === "Procesando...") return;
  mostrarAviso(limpio, tipo || "info");
}

/** Dispara la descarga de cada archivo generado, sin boton de por medio. */
function mostrarDescargas(descargas) {
  if (!descargas || !descargas.length) return;
  descargas.forEach((nombre, indice) => {
    // Un navegador bloquea varias descargas seguidas si salen en el mismo
    // instante; se separan unas decimas y pasan todas.
    setTimeout(() => {
      const enlace = document.createElement("a");
      enlace.href = "/api/descargar?archivo=" + encodeURIComponent(nombre);
      enlace.setAttribute("download", nombre);
      enlace.style.display = "none";
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
    }, indice * 400);
  });
  const cuantos = descargas.length;
  mostrarAviso(
    cuantos === 1 ? "Descargando " + descargas[0] : "Descargando " + cuantos + " archivos...",
    "exito",
  );
}
