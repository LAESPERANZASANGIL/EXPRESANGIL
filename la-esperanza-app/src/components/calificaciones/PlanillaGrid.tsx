"use client";

import { useMemo, useRef, useState, useTransition } from "react";
import * as XLSX from "xlsx";
import { guardarNota } from "@/lib/calificaciones/actions";
import type { FilaPlanilla, PlanillaData } from "@/lib/calificaciones/calculos";
import { calcularAcumulado, calcularDesempeno, colorDesempeno } from "@/lib/calificaciones/calculos";

function CeldaNota({
  estudianteId,
  actividadId,
  valorInicial,
  bloqueada,
  cellRef,
  onNavigate,
  onPasteBloque,
}: {
  estudianteId: string;
  actividadId: string;
  valorInicial: number | null;
  bloqueada: boolean;
  cellRef: (el: HTMLInputElement | null) => void;
  onNavigate: (direccion: "up" | "down" | "left" | "right" | "enter" | "tab") => void;
  onPasteBloque: (texto: string) => void;
}) {
  const [valor, setValor] = useState(valorInicial?.toString() ?? "");
  const [estado, setEstado] = useState<"idle" | "guardando" | "error" | "ok">("idle");
  const [, startTransition] = useTransition();

  function guardar(texto: string) {
    const limpio = texto.trim();
    const numero = limpio === "" ? null : Number(limpio.replace(",", "."));

    if (limpio !== "" && (Number.isNaN(numero) || numero === null)) {
      setEstado("error");
      return;
    }

    startTransition(async () => {
      setEstado("guardando");
      const resultado = await guardarNota({ estudianteId, actividadId, valor: numero });
      setEstado(resultado.ok ? "ok" : "error");
    });
  }

  return (
    <input
      ref={cellRef}
      type="text"
      inputMode="decimal"
      disabled={bloqueada}
      value={valor}
      onChange={(e) => setValor(e.target.value)}
      onBlur={(e) => guardar(e.target.value)}
      onPaste={(e) => {
        const texto = e.clipboardData.getData("text");
        if (texto.includes("\t") || texto.includes("\n")) {
          e.preventDefault();
          onPasteBloque(texto);
        }
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          guardar((e.target as HTMLInputElement).value);
          onNavigate("enter");
        } else if (e.key === "Tab") {
          e.preventDefault();
          guardar((e.target as HTMLInputElement).value);
          onNavigate(e.shiftKey ? "left" : "tab");
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          onNavigate("up");
        } else if (e.key === "ArrowDown") {
          e.preventDefault();
          onNavigate("down");
        }
      }}
      className={`w-16 rounded border px-2 py-1 text-center text-sm focus:outline-none ${
        estado === "error"
          ? "border-red-400 bg-red-50"
          : estado === "ok"
            ? "border-emerald-300"
            : "border-slate-300"
      } ${bloqueada ? "bg-slate-100 text-slate-400" : ""}`}
    />
  );
}

export function PlanillaGrid({
  data,
  soloLectura,
}: {
  data: PlanillaData;
  soloLectura: boolean;
}) {
  const { actividades, filas } = data;
  const bloqueada = soloLectura || data.periodoEstado !== "abierto";
  const celdasRef = useRef<Record<string, HTMLInputElement | null>>({});
  const [mensajeImportacion, setMensajeImportacion] = useState<string | null>(null);
  const [importando, setImportando] = useState(false);

  const acumulados = useMemo(
    () =>
      filas.map((fila) => calcularAcumulado(fila.notas, actividades)),
    [filas, actividades],
  );

  if (actividades.length === 0) {
    return (
      <p className="mt-6 text-sm text-slate-500">
        Esta asignación no tiene actividades configuradas para este periodo.
        Pide a secretaría que las cree en &quot;Notas → Configurar&quot;.
      </p>
    );
  }

  function clave(filaIdx: number, colIdx: number) {
    return `${filaIdx}-${colIdx}`;
  }

  function enfocar(filaIdx: number, colIdx: number) {
    const el = celdasRef.current[clave(filaIdx, colIdx)];
    el?.focus();
    el?.select();
  }

  function navegar(filaIdx: number, colIdx: number, direccion: string) {
    const totalCols = actividades.length;
    if (direccion === "tab" || direccion === "enter" || direccion === "down") {
      if (filaIdx + 1 < filas.length) enfocar(filaIdx + 1, colIdx);
    } else if (direccion === "up") {
      if (filaIdx - 1 >= 0) enfocar(filaIdx - 1, colIdx);
    } else if (direccion === "left") {
      if (colIdx - 1 >= 0) enfocar(filaIdx, colIdx - 1);
      else if (filaIdx - 1 >= 0) enfocar(filaIdx - 1, totalCols - 1);
    } else if (direccion === "right") {
      if (colIdx + 1 < totalCols) enfocar(filaIdx, colIdx + 1);
    }
  }

  function pegarBloque(filaIdx: number, colIdx: number, texto: string) {
    const filasTexto = texto.replace(/\r/g, "").split("\n").filter((l) => l.length > 0 || true);
    filasTexto.forEach((linea, dFila) => {
      const valores = linea.split("\t");
      valores.forEach((valor, dCol) => {
        const destinoFila = filaIdx + dFila;
        const destinoCol = colIdx + dCol;
        if (destinoFila >= filas.length || destinoCol >= actividades.length) return;
        const el = celdasRef.current[clave(destinoFila, destinoCol)];
        if (el && !el.disabled) {
          el.value = valor.trim();
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.blur();
        }
      });
    });
  }

  function exportarExcel() {
    const encabezado = ["Estudiante", ...actividades.map((a) => `${a.nombre} (${a.peso_porcentual}%)`), "Acumulado", "Desempeño"];
    const filasExcel = filas.map((fila, i) => {
      const acumulado = acumulados[i];
      return [
        fila.nombre_completo,
        ...actividades.map((a) => fila.notas[a.id] ?? ""),
        acumulado ?? "",
        calcularDesempeno(acumulado) ?? "",
      ];
    });
    const hoja = XLSX.utils.aoa_to_sheet([encabezado, ...filasExcel]);
    const libro = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(libro, hoja, "Planilla");
    XLSX.writeFile(libro, "planilla_notas.xlsx");
  }

  async function importarExcel(file: File) {
    setImportando(true);
    setMensajeImportacion(null);
    try {
      const buffer = await file.arrayBuffer();
      const libro = XLSX.read(buffer);
      const hoja = libro.Sheets[libro.SheetNames[0]];
      const filasArchivo = XLSX.utils.sheet_to_json<Record<string, unknown>>(hoja);

      const nombreAColumna = actividades.map((a) => `${a.nombre} (${a.peso_porcentual}%)`);
      let aplicadas = 0;
      let omitidas = 0;
      const errores: string[] = [];

      for (const filaArchivo of filasArchivo) {
        const nombreEstudiante = String(filaArchivo["Estudiante"] ?? "").trim();
        const fila = filas.find((f) => f.nombre_completo === nombreEstudiante);
        if (!fila) {
          errores.push(`Estudiante no encontrado: "${nombreEstudiante}"`);
          omitidas++;
          continue;
        }
        for (let i = 0; i < actividades.length; i++) {
          const crudo = filaArchivo[nombreAColumna[i]];
          if (crudo === undefined || crudo === "") continue;
          const numero = Number(String(crudo).replace(",", "."));
          if (Number.isNaN(numero) || numero < 0 || numero > 5) {
            errores.push(`Valor inválido para ${fila.nombre_completo} / ${actividades[i].nombre}: "${crudo}"`);
            omitidas++;
            continue;
          }
          const resultado = await guardarNota({
            estudianteId: fila.estudiante_id,
            actividadId: actividades[i].id,
            valor: numero,
          });
          if (resultado.ok) aplicadas++;
          else {
            errores.push(`No se pudo guardar ${fila.nombre_completo} / ${actividades[i].nombre}: ${resultado.error}`);
            omitidas++;
          }
        }
      }

      const resumen = `Importación completa: ${aplicadas} notas aplicadas, ${omitidas} omitidas.`;
      setMensajeImportacion(
        errores.length > 0 ? `${resumen} Detalle:\n${errores.slice(0, 10).join("\n")}` : resumen,
      );
      if (aplicadas > 0) {
        setTimeout(() => window.location.reload(), 1500);
      }
    } finally {
      setImportando(false);
    }
  }

  return (
    <div>
      {mensajeImportacion && (
        <pre className="mt-4 whitespace-pre-wrap rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
          {mensajeImportacion}
        </pre>
      )}

      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <label className="cursor-pointer rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50">
          {importando ? "Importando..." : "Importar desde Excel"}
          <input
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            disabled={bloqueada || importando}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importarExcel(file);
              e.target.value = "";
            }}
          />
        </label>
        <button
          type="button"
          onClick={exportarExcel}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          Exportar a Excel
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          Imprimir
        </button>
      </div>

      <div className="mt-2 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="sticky left-0 bg-slate-50 px-4 py-2">Estudiante</th>
              {actividades.map((actividad) => (
                <th key={actividad.id} className="px-3 py-2 text-center">
                  {actividad.nombre}
                  <div className="text-xs font-normal text-slate-400">
                    {actividad.peso_porcentual}%
                  </div>
                </th>
              ))}
              <th className="px-3 py-2 text-center">Acumulado</th>
              <th className="px-3 py-2 text-center">Desempeño</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila: FilaPlanilla, filaIdx) => {
              const acumulado = acumulados[filaIdx];
              const desempeno = calcularDesempeno(acumulado);
              return (
                <tr key={fila.estudiante_id} className="border-t border-slate-100">
                  <td className="sticky left-0 bg-white px-4 py-2 text-slate-700">
                    {fila.nombre_completo}
                  </td>
                  {actividades.map((actividad, colIdx) => (
                    <td key={actividad.id} className="px-3 py-2 text-center">
                      <CeldaNota
                        estudianteId={fila.estudiante_id}
                        actividadId={actividad.id}
                        valorInicial={fila.notas[actividad.id]}
                        bloqueada={bloqueada}
                        cellRef={(el) => {
                          celdasRef.current[clave(filaIdx, colIdx)] = el;
                        }}
                        onNavigate={(direccion) => navegar(filaIdx, colIdx, direccion)}
                        onPasteBloque={(texto) => pegarBloque(filaIdx, colIdx, texto)}
                      />
                    </td>
                  ))}
                  <td className="px-3 py-2 text-center font-medium text-slate-700">
                    {acumulado ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${colorDesempeno(desempeno)}`}>
                      {desempeno ?? "—"}
                    </span>
                  </td>
                </tr>
              );
            })}
            {filas.length === 0 && (
              <tr>
                <td colSpan={actividades.length + 3} className="px-4 py-6 text-center text-slate-400">
                  No hay estudiantes activos en este curso.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Tip: puedes pegar un bloque de notas copiado desde Excel (filas y columnas) pegando sobre
        cualquier celda, y navegar con Tab / Enter / flechas arriba-abajo.
      </p>
    </div>
  );
}
