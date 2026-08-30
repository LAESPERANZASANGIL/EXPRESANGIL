const log = document.getElementById("log");
const contador = document.getElementById("contador");
const campoMes = document.getElementById("mes");
const tablaPrestamos = document.getElementById("tabla-prestamos");
const panelAbono = document.getElementById("panel-abono");
const abonoDetalle = document.getElementById("abono-detalle");

let prestamoSeleccionado = null;

function mostrarLog(texto) {
  log.textContent = texto;
}

function pesos(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
}

function hoy() {
  const ahora = new Date();
  const mes = String(ahora.getMonth() + 1).padStart(2, "0");
  const dia = String(ahora.getDate()).padStart(2, "0");
  return `${ahora.getFullYear()}-${mes}-${dia}`;
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
    mostrarDescargas(resultado.descargas);
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

async function consultar() {
  const mes = mesSeleccionado();
  if (!mes) return;
  const resultado = await llamar("/api/prestamos", {
    mes,
    empleado: document.getElementById("filtro-empleado").value.trim(),
  });
  if (!resultado.ok) return;

  const lista = document.getElementById("lista-empleados");
  lista.innerHTML = "";
  for (const empleado of resultado.empleados || []) {
    const opcion = document.createElement("option");
    opcion.value = empleado.nombre;
    lista.appendChild(opcion);
  }

  tablaPrestamos.innerHTML = "";
  let totalSaldo = 0;
  for (const prestamo of resultado.prestamos || []) {
    totalSaldo += Number(prestamo.saldo_total || 0);
    const tr = document.createElement("tr");
    const celdas = [
      prestamo.empleado,
      prestamo.tipo === "PRESTAMO" ? "Prestamo" : "Adelanto",
      String(prestamo.fecha || "").slice(0, 10),
      pesos(prestamo.monto),
      prestamo.cuotas,
      pesos(prestamo.abonado),
      pesos(prestamo.saldo_capital),
      pesos(prestamo.interes_del_mes),
      pesos(prestamo.saldo_total),
      pesos(prestamo.cuota_sugerida),
      prestamo.estado,
    ];
    for (const valor of celdas) {
      const td = document.createElement("td");
      td.textContent = valor;
      tr.appendChild(td);
    }
    if (prestamo.saldo_total <= 0) tr.classList.add("fila-pagada");

    const acciones = document.createElement("td");
    const btnAbonar = document.createElement("button");
    btnAbonar.className = "boton-mini";
    btnAbonar.textContent = "Abonar";
    btnAbonar.addEventListener("click", () => seleccionarParaAbono(prestamo));
    acciones.appendChild(btnAbonar);

    const btnAnular = document.createElement("button");
    btnAnular.className = "boton-mini boton-mini-peligro";
    btnAnular.textContent = "Anular";
    btnAnular.addEventListener("click", async () => {
      if (!confirm(`¿Anular el registro de ${prestamo.empleado} por ${pesos(prestamo.monto)}?`)) return;
      const respuesta = await llamar("/api/prestamos/anular", { prestamo_id: prestamo.id });
      if (respuesta.ok) await consultar();
    });
    acciones.appendChild(btnAnular);
    tr.appendChild(acciones);

    tablaPrestamos.appendChild(tr);
  }

  const cantidad = (resultado.prestamos || []).length;
  contador.textContent = `Registros: ${cantidad} | Saldo total pendiente: ${pesos(totalSaldo)}`;
}

function seleccionarParaAbono(prestamo) {
  prestamoSeleccionado = prestamo;
  abonoDetalle.textContent =
    `Abonando a ${prestamo.empleado} — ${prestamo.tipo === "PRESTAMO" ? "Prestamo" : "Adelanto"} ` +
    `del ${String(prestamo.fecha).slice(0, 10)}. Saldo total: ${pesos(prestamo.saldo_total)} ` +
    `(capital ${pesos(prestamo.saldo_capital)} + intereses ${pesos(prestamo.interes_pendiente)}).`;
  document.getElementById("abono-monto").value = prestamo.cuota_sugerida || "";
  document.getElementById("abono-fecha").value = hoy();
  panelAbono.scrollIntoView({ behavior: "smooth", block: "center" });
}

document.getElementById("btn-crear").addEventListener("click", async () => {
  const resultado = await llamar("/api/prestamos/crear", {
    empleado: document.getElementById("nuevo-empleado").value.trim(),
    tipo: document.getElementById("nuevo-tipo").value,
    monto: document.getElementById("nuevo-monto").value,
    fecha: document.getElementById("nuevo-fecha").value,
    forma_pago: document.getElementById("nuevo-forma-pago").value,
    cuotas: document.getElementById("nuevo-cuotas").value,
    observaciones: document.getElementById("nuevo-observaciones").value,
  });
  if (resultado.ok) {
    document.getElementById("nuevo-monto").value = "";
    document.getElementById("nuevo-observaciones").value = "";
    await consultar();
  }
});

document.getElementById("btn-abonar").addEventListener("click", async () => {
  if (!prestamoSeleccionado) {
    mostrarLog('Primero elige un registro con el boton "Abonar" de la tabla.');
    return;
  }
  const resultado = await llamar("/api/prestamos/abonar", {
    prestamo_id: prestamoSeleccionado.id,
    monto: document.getElementById("abono-monto").value,
    fecha: document.getElementById("abono-fecha").value,
    concepto: document.getElementById("abono-concepto").value,
  });
  if (resultado.ok) {
    prestamoSeleccionado = null;
    abonoDetalle.textContent = 'Selecciona "Abonar" en la tabla para registrar un pago.';
    document.getElementById("abono-monto").value = "";
    document.getElementById("abono-concepto").value = "";
    await consultar();
  }
});

document.getElementById("btn-cancelar-abono").addEventListener("click", () => {
  prestamoSeleccionado = null;
  abonoDetalle.textContent = 'Selecciona "Abonar" en la tabla para registrar un pago.';
  document.getElementById("abono-monto").value = "";
  document.getElementById("abono-concepto").value = "";
  mostrarLog("Abono cancelado.");
});

document.getElementById("btn-consultar").addEventListener("click", consultar);

document.getElementById("btn-informe").addEventListener("click", async () => {
  const mes = mesSeleccionado();
  if (!mes) return;
  await llamar("/api/prestamos/informe", { mes });
});

(function () {
  const ahora = new Date();
  campoMes.value = `${ahora.getFullYear()}-${String(ahora.getMonth() + 1).padStart(2, "0")}`;
  document.getElementById("nuevo-fecha").value = hoy();
  document.getElementById("abono-fecha").value = hoy();
  consultar();
})();
