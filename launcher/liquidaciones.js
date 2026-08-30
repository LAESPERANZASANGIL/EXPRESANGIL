const log = document.getElementById("log");
const campoSemana = document.getElementById("semana-fecha");
const rangoSemana = document.getElementById("rango-semana");
const tablaSemana = document.getElementById("tabla-semana");
const tablaLaboral = document.getElementById("tabla-laboral");
const liqEmpleado = document.getElementById("liq-empleado");

let empleadosNomina = [];

function mostrarLog(texto) {
  log.textContent = texto;
}

function pesos(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
}

function numero(valor) {
  return Number(String(valor || "0").replace(/[^0-9.-]/g, "")) || 0;
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

function crearEntrada(valor, ancho) {
  const input = document.createElement("input");
  input.type = "text";
  input.value = valor;
  input.className = "entrada-nomina";
  if (ancho) input.style.width = ancho;
  return input;
}

// ------------------------- Semanal de servicios -------------------------

async function cargarSemana() {
  const fecha = campoSemana.value.trim() || hoy();
  const resultado = await llamar("/api/liquidaciones/semana", { fecha });
  if (!resultado.ok) return;

  rangoSemana.textContent =
    `Semana del ${resultado.semana_inicio} al ${resultado.semana_fin} | ` +
    `Contratistas de servicios: ${(resultado.empleados || []).length}`;

  tablaSemana.innerHTML = "";
  if (!(resultado.empleados || []).length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 9;
    td.textContent = 'No hay empleados con contrato de SERVICIOS. Configuralos en el Modulo Usuarios.';
    td.style.textAlign = "center";
    tr.appendChild(td);
    tablaSemana.appendChild(tr);
    return;
  }

  for (const empleado of resultado.empleados) {
    const tr = document.createElement("tr");
    tr.dataset.empleado = empleado.nombre;

    const celdaNombre = document.createElement("td");
    celdaNombre.textContent = `${empleado.nombre} ${empleado.apellidos || ""}`.trim();
    tr.appendChild(celdaNombre);

    const campos = {
      entregas: crearEntrada(empleado.entregas, "70px"),
      valor: crearEntrada(empleado.valor_encomienda, "110px"),
      prestamos: crearEntrada(empleado.descuento_prestamos, "110px"),
      otros: crearEntrada(empleado.otros_descuentos, "110px"),
      forma: crearEntrada(empleado.forma_pago, "120px"),
    };
    campos.forma.style.textAlign = "left";

    for (const clave of ["entregas", "valor"]) {
      const td = document.createElement("td");
      td.appendChild(campos[clave]);
      tr.appendChild(td);
    }

    const celdaSubtotal = document.createElement("td");
    tr.appendChild(celdaSubtotal);

    for (const clave of ["prestamos", "otros"]) {
      const td = document.createElement("td");
      td.appendChild(campos[clave]);
      tr.appendChild(td);
    }

    const celdaNeto = document.createElement("td");
    celdaNeto.className = "celda-neto";
    tr.appendChild(celdaNeto);

    const celdaForma = document.createElement("td");
    celdaForma.appendChild(campos.forma);
    tr.appendChild(celdaForma);

    function refrescar() {
      const subtotal = numero(campos.entregas.value) * numero(campos.valor.value);
      celdaSubtotal.textContent = pesos(subtotal);
      celdaNeto.textContent = pesos(subtotal - numero(campos.prestamos.value) - numero(campos.otros.value));
    }
    for (const campo of Object.values(campos)) campo.addEventListener("input", refrescar);
    refrescar();

    // Aviso si el conteo se edito a mano y ya no coincide con las guias.
    if (empleado.liquidada && empleado.entregas !== empleado.entregas_reales) {
      celdaNombre.title =
        `Guardado con ${empleado.entregas} entregas; hoy las guias del sistema suman ${empleado.entregas_reales}.`;
      celdaNombre.textContent += " *";
    }

    const acciones = document.createElement("td");
    const boton = document.createElement("button");
    boton.className = "boton-mini";
    boton.textContent = empleado.liquidada ? "Actualizar" : "Liquidar";
    boton.addEventListener("click", async () => {
      const respuesta = await guardarSemana(empleado.nombre, campos, fecha);
      if (respuesta.ok) await cargarSemana();
    });
    acciones.appendChild(boton);
    tr.appendChild(acciones);

    if (empleado.liquidada) tr.classList.add("fila-liquidada");
    tablaSemana.appendChild(tr);
  }
}

async function guardarSemana(nombre, campos, fecha, silencioso) {
  return llamar(
    "/api/liquidaciones/semana/guardar",
    {
      fecha,
      empleado: nombre,
      entregas: campos.entregas.value,
      valor_encomienda: campos.valor.value,
      descuento_prestamos: campos.prestamos.value,
      otros_descuentos: campos.otros.value,
      forma_pago: campos.forma.value,
    },
    silencioso
  );
}

document.getElementById("btn-cargar-semana").addEventListener("click", cargarSemana);

document.getElementById("btn-informe-semana").addEventListener("click", async () => {
  await llamar("/api/liquidaciones/semana/informe", { fecha: campoSemana.value.trim() || hoy() });
});

// ----------------------- Liquidacion laboral ----------------------------

function datosLiquidacion() {
  return {
    empleado: liqEmpleado.value,
    fecha_ingreso: document.getElementById("liq-ingreso").value,
    fecha_retiro: document.getElementById("liq-retiro").value,
    salario_base: document.getElementById("liq-salario").value,
    auxilio_transporte: document.getElementById("liq-auxilio").value,
    dias_prima: document.getElementById("liq-dias-prima").value,
    dias_vacaciones: document.getElementById("liq-dias-vacaciones").value,
    indemnizacion: document.getElementById("liq-indemnizacion").value,
    otros_descuentos: document.getElementById("liq-otros").value,
    observaciones: document.getElementById("liq-observaciones").value,
  };
}

function mostrarCalculo(liquidacion) {
  const cuerpo = document.getElementById("cuerpo-calculo");
  cuerpo.innerHTML = "";
  const filas = [
    ["Dias trabajados", liquidacion.dias_trabajados],
    ["Cesantias", pesos(liquidacion.cesantias)],
    ["Intereses de cesantias (12%)", pesos(liquidacion.intereses_cesantias)],
    ["Prima de servicios", pesos(liquidacion.prima)],
    ["Vacaciones", pesos(liquidacion.vacaciones)],
    ["Indemnizacion", pesos(liquidacion.indemnizacion)],
    ["(-) Otros descuentos", pesos(liquidacion.otros_descuentos)],
    ["TOTAL A PAGAR", pesos(liquidacion.total_pagar)],
  ];
  for (const [etiqueta, valor] of filas) {
    const tr = document.createElement("tr");
    const tdEtiqueta = document.createElement("td");
    tdEtiqueta.textContent = etiqueta;
    const tdValor = document.createElement("td");
    tdValor.textContent = valor;
    tdValor.style.textAlign = "right";
    if (etiqueta.startsWith("TOTAL")) {
      tdEtiqueta.style.fontWeight = "bold";
      tdValor.style.fontWeight = "bold";
    }
    tr.appendChild(tdEtiqueta);
    tr.appendChild(tdValor);
    cuerpo.appendChild(tr);
  }
  document.getElementById("tabla-calculo").style.display = "";
}

document.getElementById("btn-calcular-liq").addEventListener("click", async () => {
  const resultado = await llamar("/api/liquidaciones/laboral/calcular", datosLiquidacion());
  if (resultado.ok) mostrarCalculo(resultado.liquidacion);
});

document.getElementById("btn-guardar-liq").addEventListener("click", async () => {
  const datos = datosLiquidacion();
  if (!confirm(`¿Guardar la liquidacion definitiva de ${datos.empleado}? Queda como soporte del pago.`)) return;
  const resultado = await llamar("/api/liquidaciones/laboral/guardar", datos);
  if (resultado.ok) {
    mostrarCalculo(resultado.liquidacion);
    await cargarLaborales();
  }
});

document.getElementById("btn-informe-laboral").addEventListener("click", async () => {
  await llamar("/api/liquidaciones/laboral/informe", {});
});

async function cargarLaborales() {
  const resultado = await llamar("/api/liquidaciones/laboral", {}, true);
  if (!resultado.ok) return;

  empleadosNomina = resultado.empleados || [];
  const seleccionado = liqEmpleado.value;
  liqEmpleado.innerHTML = "";
  for (const empleado of empleadosNomina) {
    const opcion = document.createElement("option");
    opcion.value = empleado.nombre;
    opcion.textContent = `${empleado.nombre} ${empleado.apellidos || ""} (${empleado.tipo_contrato})`.trim();
    liqEmpleado.appendChild(opcion);
  }
  if (seleccionado) liqEmpleado.value = seleccionado;
  cargarDatosEmpleado();

  tablaLaboral.innerHTML = "";
  for (const registro of resultado.liquidaciones || []) {
    const tr = document.createElement("tr");
    const valores = [
      registro.empleado, registro.fecha_ingreso, registro.fecha_retiro,
      registro.dias_trabajados, pesos(registro.cesantias), pesos(registro.intereses_cesantias),
      pesos(registro.prima), pesos(registro.vacaciones), pesos(registro.indemnizacion),
      pesos(registro.total_pagar),
    ];
    for (const valor of valores) {
      const td = document.createElement("td");
      td.textContent = valor;
      tr.appendChild(td);
    }
    tablaLaboral.appendChild(tr);
  }
}

function cargarDatosEmpleado() {
  const empleado = empleadosNomina.find((e) => e.nombre === liqEmpleado.value);
  if (!empleado) return;
  document.getElementById("liq-ingreso").value = empleado.fecha_ingreso || "";
  document.getElementById("liq-retiro").value = empleado.fecha_retiro || hoy();
  document.getElementById("liq-salario").value = empleado.salario_base || 0;
  document.getElementById("liq-auxilio").value = empleado.auxilio_transporte || 0;
}

liqEmpleado.addEventListener("change", cargarDatosEmpleado);

(function () {
  campoSemana.value = hoy();
  cargarSemana();
  cargarLaborales();
})();
