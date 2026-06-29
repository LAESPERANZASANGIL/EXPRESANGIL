"use client";

import { useState, useTransition } from "react";
import { guardarNota } from "@/lib/calificaciones/actions";
import type { FilaPlanilla, PlanillaData } from "@/lib/calificaciones/calculos";
import { calcularAcumulado } from "@/lib/calificaciones/calculos";

function CeldaNota({
  estudianteId,
  actividadId,
  valorInicial,
  bloqueada,
}: {
  estudianteId: string;
  actividadId: string;
  valorInicial: number | null;
  bloqueada: boolean;
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
      type="text"
      inputMode="decimal"
      disabled={bloqueada}
      value={valor}
      onChange={(e) => setValor(e.target.value)}
      onBlur={(e) => guardar(e.target.value)}
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

  if (actividades.length === 0) {
    return (
      <p className="mt-6 text-sm text-slate-500">
        Esta asignación no tiene actividades configuradas para este periodo.
        Pide a secretaría que las cree en &quot;Notas → Configurar&quot;.
      </p>
    );
  }

  return (
    <div className="mt-6 overflow-x-auto rounded-lg border border-slate-200 bg-white">
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
          </tr>
        </thead>
        <tbody>
          {filas.map((fila: FilaPlanilla) => (
            <tr key={fila.estudiante_id} className="border-t border-slate-100">
              <td className="sticky left-0 bg-white px-4 py-2 text-slate-700">
                {fila.nombre_completo}
              </td>
              {actividades.map((actividad) => (
                <td key={actividad.id} className="px-3 py-2 text-center">
                  <CeldaNota
                    estudianteId={fila.estudiante_id}
                    actividadId={actividad.id}
                    valorInicial={fila.notas[actividad.id]}
                    bloqueada={bloqueada}
                  />
                </td>
              ))}
              <td className="px-3 py-2 text-center font-medium text-slate-700">
                {calcularAcumulado(fila.notas, actividades) ?? "—"}
              </td>
            </tr>
          ))}
          {filas.length === 0 && (
            <tr>
              <td colSpan={actividades.length + 2} className="px-4 py-6 text-center text-slate-400">
                No hay estudiantes activos en este curso.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
