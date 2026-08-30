const log = document.getElementById("log");
const contador = document.getElementById("contador");
const campoMes = document.getElementById("mes");
const tablaNomina = document.getElementById("tabla-nomina");
const configUsuario = document.getElementById("config-usuario");

let empleados = [];

function mostrarLog(texto) {
  log.textContent = texto;
}

function pesos(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
}

function numero(valor) {
  return Number(String(valor || "0").replace(/[^0-9.-]/g, "")) || 0;
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

async function llamar(ruta, datos, silencioso) {
  if (!silencioso) mostrarLog("Procesando...");
  try {
    const respuesta = await fetch(ruta, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos || {}),
      credentials: "same-origin",
    });
    const resultado = await respuesta.json();
    if (!silencioso) {
      mostrarLog(resultado.output || (resultado.ok ? "Listo." : "Ocurrio un error."));
      mostrarDescargas(resultado.descargas);
    }
    return resultado;
  } catch (error) {
    mostrarLog("No se pudo conectar con el panel: " + error);
    return { ok: false };
  }
}

function mesSeleccionado() {
  const mes = campoMes.value.trim();
  if (!mes) {
    mostrarLog("Selecciona el mes.");
    return null;
  }
  return mes;
}

// Calculo en el navegador para previsualizar el neto mientras se escribe.
// El calculo definitivo lo hace el servidor al liquidar.
function calcularNeto(fila) {
  const dias = Math.max(0, Math.min(numero(fila.dias.value), 30));
  const salario = Math.round((numero(fila.salario.value) * dias) / 30);
  const auxilio = Math.round((numero(fila.auxilio.value) * dias) / 30);
  const devengado = salario + auxilio + numero(fila.bonificaciones.value);
  const descuentos =
    Math.round(salario * 0.04) * 2 + numero(fila.prestamos.value) + numero(fila.otros.value);
  return devengado - descuentos;
}

function crearEntrada(valor, ancho) {
  const input = document.createElement("input");
  input.type = "text";
  input.value = valor;
  input.className = "entrada-nomina";
  if (ancho) input.style.width = ancho;
  return input;
}

async function consultar() {
  const mes = mesSeleccionado();
  if (!mes) return;
  const resultado = await llamar("/api/nomina", { mes });
  if (!resultado.ok) return;

  empleados = resultado.empleados || [];
  configUsuario.innerHTML = "";
  for (const empleado of empleados) {
    const opcion = document.createElement("option");
    opcion.value = empleado.usuario;
    opcion.textContent = `${empleado.nombre} (${empleado.usuario})`;
    configUsuario.appendChild(opcion);
  }
  cargarDatosEmpleado();

  tablaNomina.innerHTML = "";
  let totalNeto = 0;
  let liquidados = 0;

  for (const empleado of empleados) {
    const tr = document.createElement("tr");
    tr.dataset.empleado = empleado.nombre;
    const celdaNombre = document.createElement("td");
    celdaNombre.textContent = empleado.nombre;
    tr.appendChild(celdaNombre);

    const campos = {
      salario: crearEntrada(empleado.salario_base, "110px"),
      dias: crearEntrada(empleado.dias_trabajados, "55px"),
      auxilio: crearEntrada(empleado.auxilio_transporte, "110px"),
      bonificaciones: crearEntrada(empleado.bonificaciones, "110px"),
      otros: crearEntrada(empleado.otros_descuentos, "110px"),
      prestamos: crearEntrada(empleado.descuento_prestamos, "110px"),
    };

    for (const clave of ["salario", "dias", "auxilio", "bonificaciones", "otros", "prestamos"]) {
      const td = document.createElement("td");
      td.appendChild(campos[clave]);
      tr.appendChild(td);
    }

    const celdaSalud = document.createElement("td");
    const celdaPension = document.createElement("td");
    const celdaNeto = document.createElement("td");
    celdaNeto.className = "celda-neto";
    tr.appendChild(celdaSalud);
    tr.appendChild(celdaPension);
    tr.appendChild(celdaNeto);

    function refrescar() {
      const dias = Math.max(0, Math.min(numero(campos.dias.value), 30));
      const salario = Math.round((numero(campos.salario.value) * dias) / 30);
      const aporte = Math.round(salario * 0.04);
      celdaSalud.textContent = pesos(aporte);
      celdaPension.textContent = pesos(aporte);
      celdaNeto.textContent = pesos(calcularNeto(campos));
    }
    for (const campo of Object.values(campos)) campo.addEventListener("input", refrescar);
    refrescar();

    const acciones = document.createElement("td");
    const btn = document.createElement("button");
    btn.className = "boton-mini";
    btn.textContent = empleado.liquidado ? "Actualizar" : "Liquidar";
    btn.addEventListener("click", async () => {
      const respuesta = await liquidar(empleado.nombre, campos, mes);
      if (respuesta.ok) await consultar();
    });
    acciones.appendChild(btn);
    tr.appendChild(acciones);

    if (empleado.liquidado) {
      tr.classList.add("fila-liquidada");
      liquidados += 1;
      totalNeto += Number(empleado.total_pagar || 0);
    }
    tablaNomina.appendChild(tr);
  }

  contador.textContent =
    `Empleados: ${empleados.length} | Liquidados: ${liquidados} | Total neto liquidado: ${pesos(totalNeto)}`;
}

async function liquidar(nombre, campos, mes, silencioso) {
  return llamar(
    "/api/nomina/liquidar",
    {
      mes,
      empleado: nombre,
      salario_base: campos.salario.value,
      dias_trabajados: campos.dias.value,
      auxilio_transporte: campos.auxilio.value,
      bonificaciones: campos.bonificaciones.value,
      otros_descuentos: campos.otros.value,
      descuento_prestamos: campos.prestamos.value,
    },
    silencioso
  );
}

function cargarDatosEmpleado() {
  const empleado = empleados.find((e) => e.usuario === configUsuario.value);
  if (!empleado) return;
  document.getElementById("config-cedula").value = empleado.cedula || "";
  document.getElementById("config-cargo").value = empleado.cargo || "";
  document.getElementById("config-salario").value = empleado.salario_base || 0;
  document.getElementById("config-auxilio").value = empleado.auxilio_transporte || 0;
}

configUsuario.addEventListener("change", cargarDatosEmpleado);

document.getElementById("btn-guardar-empleado").addEventListener("click", async () => {
  const resultado = await llamar("/api/nomina/empleado", {
    usuario: configUsuario.value,
    cedula: document.getElementById("config-cedula").value,
    cargo: document.getElementById("config-cargo").value,
    salario_base: document.getElementById("config-salario").value,
    auxilio_transporte: document.getElementById("config-auxilio").value,
  });
  if (resultado.ok) await consultar();
});

document.getElementById("btn-liquidar-todos").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (!mes) return;
  if (!confirm(`¿Liquidar la nomina de los ${empleados.length} empleados para ${mes}?`)) return;
  let procesados = 0;
  for (const fila of tablaNomina.querySelectorAll("tr")) {
    const entradas = fila.querySelectorAll("input");
    if (entradas.length < 6 || !fila.dataset.empleado) continue;
    const campos = {
      salario: entradas[0], dias: entradas[1], auxilio: entradas[2],
      bonificaciones: entradas[3], otros: entradas[4], prestamos: entradas[5],
    };
    const respuesta = await liquidar(fila.dataset.empleado, campos, mes, true);
    if (respuesta.ok) procesados += 1;
  }
  mostrarLog(`Se liquidaron ${procesados} empleado(s) para ${mes}.`);
  await consultar();
});

document.getElementById("btn-consultar").addEventListener("click", consultar);

document.getElementById("btn-informe-excel").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (mes) await llamar("/api/nomina/informe", { mes, formato: "excel" });
});

document.getElementById("btn-informe-pdf").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (mes) await llamar("/api/nomina/informe", { mes, formato: "pdf" });
});

(function () {
  const ahora = new Date();
  campoMes.value = `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}`;
  consultar();
})();
