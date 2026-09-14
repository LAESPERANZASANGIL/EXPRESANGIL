import { createClient } from "@/lib/supabase/server";
import { crearActividad, desactivarActividad } from "@/lib/calificaciones/actions";

const ERRORES: Record<string, string> = {
  campos: "Completa nombre y peso porcentual (mayor a 0).",
  guardar: "No se pudo guardar la actividad.",
};

export default async function ConfigurarNotasPage({
  searchParams,
}: {
  searchParams: Promise<{ asignacion?: string; periodo?: string; error?: string }>;
}) {
  const { asignacion, periodo, error } = await searchParams;
  const supabase = await createClient();

  const { data: asignaciones } = await supabase
    .from("asignaciones_docente")
    .select("id, cursos(nombre), asignaturas(nombre), profiles:docente_id(nombre_completo)")
    .order("anio_academico", { ascending: false });

  const { data: periodos } = await supabase
    .from("periodos_academicos")
    .select("id, nombre, estado")
    .order("orden");

  const asignacionId = asignacion ?? "";
  const periodoId = periodo ?? "";

  const { data: actividades } = asignacionId && periodoId
    ? await supabase
        .from("actividades_evaluacion")
        .select("id, nombre, tipo, peso_porcentual, es_recuperacion, activa")
        .eq("asignacion_docente_id", asignacionId)
        .eq("periodo_id", periodoId)
        .eq("activa", true)
        .order("orden")
    : { data: [] };

  const pesoTotal = (actividades ?? [])
    .filter((a) => !a.es_recuperacion)
    .reduce((acc, a) => acc + a.peso_porcentual, 0);

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-800">Configurar planilla de notas</h1>
      <p className="mt-1 text-sm text-slate-500">
        Define las actividades de evaluación que verá el docente. El docente no puede crear,
        eliminar ni reordenar columnas.
      </p>

      {error && (
        <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
          {ERRORES[error] ?? "Ocurrió un error inesperado."}
        </p>
      )}

      <form className="mt-4 flex flex-wrap gap-3" method="get">
        <select name="asignacion" defaultValue={asignacionId} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="">Selecciona curso / asignatura / docente</option>
          {asignaciones?.map((a) => {
            const curso = Array.isArray(a.cursos) ? a.cursos[0] : a.cursos;
            const asig = Array.isArray(a.asignaturas) ? a.asignaturas[0] : a.asignaturas;
            const docente = Array.isArray(a.profiles) ? a.profiles[0] : a.profiles;
            return (
              <option key={a.id} value={a.id}>
                {curso?.nombre} · {asig?.nombre} · {docente?.nombre_completo}
              </option>
            );
          })}
        </select>
        <select name="periodo" defaultValue={periodoId} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="">Selecciona periodo</option>
          {periodos?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre} ({p.estado})
            </option>
          ))}
        </select>
        <button type="submit" className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
          Ver actividades
        </button>
      </form>

      {asignacionId && periodoId && (
        <>
          <div className="mt-6 overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-4 py-2">Actividad</th>
                  <th className="px-4 py-2">Tipo</th>
                  <th className="px-4 py-2">Peso</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {actividades?.map((a) => (
                  <tr key={a.id} className="border-t border-slate-100">
                    <td className="px-4 py-2">
                      {a.nombre} {a.es_recuperacion && <span className="text-xs text-amber-600">(recuperación)</span>}
                    </td>
                    <td className="px-4 py-2 text-slate-500">{a.tipo}</td>
                    <td className="px-4 py-2">{a.peso_porcentual}%</td>
                    <td className="px-4 py-2 text-right">
                      <form action={desactivarActividad}>
                        <input type="hidden" name="actividad_id" value={a.id} />
                        <input type="hidden" name="asignacion_docente_id" value={asignacionId} />
                        <input type="hidden" name="periodo_id" value={periodoId} />
                        <button type="submit" className="text-xs text-red-600 hover:underline">
                          Desactivar
                        </button>
                      </form>
                    </td>
                  </tr>
                ))}
                {(!actividades || actividades.length === 0) && (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                      Sin actividades configuradas todavía.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <p className={`mt-2 text-sm ${pesoTotal === 100 ? "text-emerald-600" : "text-amber-600"}`}>
            Peso acumulado de actividades ordinarias: {pesoTotal}% {pesoTotal !== 100 && "(debería sumar 100%)"}
          </p>

          <form action={crearActividad} className="mt-6 max-w-md space-y-3 rounded-lg border border-slate-200 bg-white p-4">
            <input type="hidden" name="asignacion_docente_id" value={asignacionId} />
            <input type="hidden" name="periodo_id" value={periodoId} />
            <h2 className="text-sm font-semibold text-slate-700">Nueva actividad</h2>
            <div>
              <label className="block text-xs font-medium text-slate-600">Nombre</label>
              <input name="nombre" required className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="block text-xs font-medium text-slate-600">Tipo</label>
                <select name="tipo" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
                  <option value="trabajo">Trabajo</option>
                  <option value="quiz">Quiz</option>
                  <option value="evaluacion">Evaluación</option>
                  <option value="proyecto">Proyecto</option>
                  <option value="laboratorio">Laboratorio</option>
                  <option value="recuperacion">Recuperación</option>
                  <option value="nivelacion">Nivelación</option>
                </select>
              </div>
              <div className="flex-1">
                <label className="block text-xs font-medium text-slate-600">Peso %</label>
                <input
                  type="number"
                  name="peso_porcentual"
                  min="1"
                  max="100"
                  step="0.5"
                  required
                  className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input type="checkbox" name="es_recuperacion" />
              Es actividad de recuperación
            </label>
            <button type="submit" className="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700">
              Agregar actividad
            </button>
          </form>
        </>
      )}
    </div>
  );
}
