import { createClient } from "@/lib/supabase/server";
import { cambiarEstadoPeriodo } from "@/lib/calificaciones/actions";

const ETIQUETA_ESTADO: Record<string, string> = {
  planeado: "Planeado",
  abierto: "Abierto",
  cerrado: "Cerrado",
};

export default async function PeriodosPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const { data: profile } = await supabase
    .from("profiles")
    .select("rol")
    .eq("id", user?.id ?? "")
    .single();

  const puedeGestionar =
    profile?.rol === "rector" || profile?.rol === "administrador" || profile?.rol === "secretaria";
  const puedeDesbloquear = profile?.rol === "rector" || profile?.rol === "administrador";

  const { data: periodos } = await supabase
    .from("periodos_academicos")
    .select("id, nombre, anio_academico, fecha_inicio, fecha_fin, estado")
    .order("anio_academico", { ascending: false })
    .order("orden");

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-800">Periodos académicos</h1>
      <p className="mt-1 text-sm text-slate-500">
        Al cerrar un periodo, todos los docentes quedan en modo lectura. Solo rector o
        administrador pueden desbloquear un periodo ya cerrado.
      </p>

      <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-2">Periodo</th>
              <th className="px-4 py-2">Año</th>
              <th className="px-4 py-2">Fechas</th>
              <th className="px-4 py-2">Estado</th>
              {puedeGestionar && <th className="px-4 py-2"></th>}
            </tr>
          </thead>
          <tbody>
            {periodos?.map((p) => (
              <tr key={p.id} className="border-t border-slate-100">
                <td className="px-4 py-2 text-slate-700">{p.nombre}</td>
                <td className="px-4 py-2 text-slate-600">{p.anio_academico}</td>
                <td className="px-4 py-2 text-slate-600">
                  {p.fecha_inicio} → {p.fecha_fin}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      p.estado === "abierto"
                        ? "bg-emerald-50 text-emerald-700"
                        : p.estado === "cerrado"
                          ? "bg-slate-100 text-slate-500"
                          : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {ETIQUETA_ESTADO[p.estado]}
                  </span>
                </td>
                {puedeGestionar && (
                  <td className="px-4 py-2 text-right">
                    {p.estado === "planeado" && (
                      <AccionEstado periodoId={p.id} nuevoEstado="abierto" etiqueta="Abrir" />
                    )}
                    {p.estado === "abierto" && (
                      <AccionEstado periodoId={p.id} nuevoEstado="cerrado" etiqueta="Cerrar" />
                    )}
                    {p.estado === "cerrado" && puedeDesbloquear && (
                      <AccionEstado periodoId={p.id} nuevoEstado="abierto" etiqueta="Desbloquear" />
                    )}
                  </td>
                )}
              </tr>
            ))}
            {(!periodos || periodos.length === 0) && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                  No hay periodos creados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AccionEstado({
  periodoId,
  nuevoEstado,
  etiqueta,
}: {
  periodoId: string;
  nuevoEstado: string;
  etiqueta: string;
}) {
  return (
    <form action={cambiarEstadoPeriodo}>
      <input type="hidden" name="periodo_id" value={periodoId} />
      <input type="hidden" name="nuevo_estado" value={nuevoEstado} />
      <button type="submit" className="text-xs text-emerald-700 hover:underline">
        {etiqueta}
      </button>
    </form>
  );
}
