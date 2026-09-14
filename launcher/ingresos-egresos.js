// Libro de caja de la oficina. Los movimientos se digitan aqui; la nomina y
// los gastos de los repartidores llegan del servidor marcados como
// automaticos y no se pueden borrar desde esta pantalla, porque su fuente de
// verdad es la nomina y el cierre de cada operador.

const log = document.getElementById("log");
const contador = document.getElementById("contador");
const mes = document.getElementById("mes");
const tabla = document.getElementById("tabla-movimientos");
const tablaResumen = document.getElementById("tabla-resumen-body");
const listaCategorias = document.getElementById("lista-categorias");

function mostrarLog(texto) {
  log.textContent = texto;
}

function pesos(valor) {
  return "$ " + Number(valor || 0).toLocaleString("es-CO");
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

function celda(fila, texto, clase) {
  const td = document.createElement("td");
  td.textContent = texto;
  if (clase) td.className = clase;
  fila.appendChild(td);
  return td;
}

function pintarResumen(datos) {
  tablaResumen.innerHTML = "";
  const filas = [
    ["TOTAL INGRESOS", pesos(datos.ingresos)],
    ["TOTAL EGRESOS", pesos(datos.egresos)],
    ["SALDO DEL MES", pesos(datos.saldo)],
  ];
  for (const [etiqueta, valor] of filas) {
    const fila = document.createElement("tr");
    celda(fila, etiqueta);
    const td = celda(fila, valor);
    if (etiqueta === "SALDO DEL MES") {
      td.className = datos.saldo < 0 ? "saldo-negativo" : "saldo-positivo";
      fila.classList.add("fila-saldo");
    }
    tablaResumen.appendChild(fila);
  }

  // Desglose por categoria, que es lo que se mira para recortar gastos.
  const categorias = Object.entries(datos.por_categoria || {}).sort();
  for (const [nombre, totales] of categorias) {
    const fila = document.createElement("tr");
    celda(fila, "   " + nombre, "fila-categoria");
    const partes = [];
    if (totales.INGRESO) partes.push("entra " + pesos(totales.INGRESO));
    if (totales.EGRESO) partes.push("sale " + pesos(totales.EGRESO));
    celda(fila, partes.join("  ·  "), "fila-categoria");
    tablaResumen.appendChild(fila);
  }
}

function pintarMovimientos(movimientos) {
  tabla.innerHTML = "";
  const categorias = new Set();

  for (const movimiento of movimientos) {
    const fila = document.createElement("tr");
    fila.classList.add(movimiento.tipo === "INGRESO" ? "fila-ingreso" : "fila-egreso");

    celda(fila, movimiento.fecha || "");
    celda(fila, movimiento.tipo);
    celda(fila, movimiento.categoria || "");
    celda(fila, movimiento.descripcion || "");
    celda(fila, movimiento.forma_pago || "");
    celda(fila, pesos(movimiento.valor), "celda-valor");

    const acciones = document.createElement("td");
    if (movimiento.automatico) {
      // No se borra desde aqui: se corrige en la nomina o en el cierre.
      const nota = document.createElement("span");
      nota.className = "nota-automatico";
      nota.textContent = "automatico";
      acciones.appendChild(nota);
    } else {
      categorias.add(movimiento.categoria || "");
      const borrar = document.createElement("button");
      borrar.textContent = "Eliminar";
      borrar.className = "boton-mini boton-mini-peligro";
      borrar.addEventListener("click", async () => {
        if (!confirm(`¿Eliminar el movimiento de ${pesos(movimiento.valor)}?`)) return;
        const resultado = await llamar("/api/movimientos/eliminar", { id: movimiento.id });
        if (resultado.ok) await consultar();
      });
      acciones.appendChild(borrar);
    }
    fila.appendChild(acciones);
    tabla.appendChild(fila);
  }

  listaCategorias.innerHTML = "";
  for (const categoria of [...categorias].filter(Boolean).sort()) {
    const opcion = document.createElement("option");
    opcion.value = categoria;
    listaCategorias.appendChild(opcion);
  }
}

async function consultar() {
  const resultado = await llamar("/api/movimientos", { mes: mes.value });
  if (!resultado.ok) return;
  pintarResumen(resultado);
  pintarMovimientos(resultado.movimientos || []);
  contador.textContent = `${(resultado.movimientos || []).length} movimiento(s) en el mes.`;
}

document.getElementById("btn-consultar").addEventListener("click", consultar);

document.getElementById("btn-crear").addEventListener("click", async () => {
  const resultado = await llamar("/api/movimientos/crear", {
    tipo: document.getElementById("nuevo-tipo").value,
    fecha: document.getElementById("nuevo-fecha").value,
    categoria: document.getElementById("nuevo-categoria").value,
    descripcion: document.getElementById("nuevo-descripcion").value,
    valor: document.getElementById("nuevo-valor").value,
    forma_pago: document.getElementById("nuevo-forma-pago").value,
  });
  if (resultado.ok) {
    document.getElementById("nuevo-valor").value = "";
    document.getElementById("nuevo-descripcion").value = "";
    await consultar();
  }
});

// Arranca en el mes en curso, que es lo que se consulta el 99% de las veces.
const hoy = new Date();
mes.value = `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
document.getElementById("nuevo-fecha").value = hoy.toISOString().slice(0, 10);
consultar();
