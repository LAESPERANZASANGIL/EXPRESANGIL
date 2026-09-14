import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { listarAsignacionesDocente, obtenerPlanilla } from "@/lib/calificaciones/queries";
import { PlanillaGrid } from "@/components/calificaciones/PlanillaGrid";

export default async function NotasPage({
  searchParams,
}: {
  searchParams: Promise<{ asignacion?: string; periodo?: string }>;
}) {
  const { asignacion, periodo } = await searchParams;
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const { data: profile } = await supabase
    .from("profiles")
    .select("rol")
    .eq("id", user?.id ?? "")
    .single();

  if (!profile) {
    return <p>No se pudo cargar tu perfil.</p>;
  }

  if (profile.rol === "estudiante" || profile.rol === "padre") {
    return <NotasConsulta rol={profile.rol} userId={user!.id} />;
  }

  if (profile.rol !== "docente") {
    return (
      <div>
        <h1 className="text-2xl font-semibold text-slate-800">Notas</h1>
        <p className="mt-2 text-sm text-slate-500">
          La planilla de notas la diligencia el docente asignado. Desde aquí puedes{" "}
          <Link href="/notas/configurar" className="text-emerald-700 underline">
            configurar las actividades de evaluación
          </Link>
          .
        </p>
      </div>
    );
  }

  const asignaciones = await listarAsignacionesDocente(user!.id);
  const { data: periodos } = await supabase
    .from("periodos_academicos")
    .select("id, nombre, estado")
    .order("orden");

  const asignacionSeleccionada = asignacion ?? asignaciones[0]?.id ?? "";
  const periodoSeleccionado = periodo ?? periodos?.[0]?.id ?? "";

  const planilla =
    asignacionSeleccionada && periodoSeleccionado
      ? await obtenerPlanilla(asignacionSeleccionada, periodoSeleccionado)
      : null;

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-800">Notas</h1>

      <form className="mt-4 flex flex-wrap gap-3" method="get">
        <select
          name="asignacion"
          defaultValue={asignacionSeleccionada}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          {asignaciones.map((a) => (
            <option key={a.id} value={a.id}>
              {a.curso_nombre} · {a.asignatura_nombre}
            </option>
          ))}
        </select>
        <select
          name="periodo"
          defaultValue={periodoSeleccionado}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          {periodos?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre} ({p.estado})
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          Ver planilla
        </button>
      </form>

      {planilla && planilla.periodoEstado !== "abierto" && (
        <p className="mt-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-700">
          Este periodo está {planilla.periodoEstado === "cerrado" ? "cerrado" : "sin abrir"}: la
          planilla se muestra en modo lectura.
        </p>
      )}

      {planilla ? (
        <PlanillaGrid data={planilla} soloLectura={false} />
      ) : (
        <p className="mt-6 text-sm text-slate-500">
          No tienes asignaciones de curso/asignatura registradas.
        </p>
      )}
    </div>
  );
}

async function NotasConsulta({ rol, userId }: { rol: "estudiante" | "padre"; userId: string }) {
  const supabase = await createClient();

  let estudianteIds: string[] = [userId];
  if (rol === "padre") {
    const { data } = await supabase
      .from("acudientes_estudiantes")
      .select("estudiante_id")
      .eq("acudiente_id", userId);
    estudianteIds = (data ?? []).map((fila) => fila.estudiante_id);
  }

  const { data: notas } = await supabase
    .from("notas")
    .select(
      "valor, actividades_evaluacion(nombre, peso_porcentual, periodos_academicos(nombre), asignaciones_docente(asignaturas(nombre)))",
    )
    .in("estudiante_id", estudianteIds);

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-800">
        {rol === "padre" ? "Notas de tus acudidos" : "Mis notas"}
      </h1>
      <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-2">Asignatura</th>
              <th className="px-4 py-2">Periodo</th>
              <th className="px-4 py-2">Actividad</th>
              <th className="px-4 py-2">Nota</th>
            </tr>
          </thead>
          <tbody>
            {notas?.map((nota, i) => {
              const actividad = Array.isArray(nota.actividades_evaluacion)
                ? nota.actividades_evaluacion[0]
                : nota.actividades_evaluacion;
              const asignacionDocente = Array.isArray(actividad?.asignaciones_docente)
                ? actividad?.asignaciones_docente[0]
                : actividad?.asignaciones_docente;
              const asignatura = Array.isArray(asignacionDocente?.asignaturas)
                ? asignacionDocente?.asignaturas[0]
                : asignacionDocente?.asignaturas;
              const periodoInfo = Array.isArray(actividad?.periodos_academicos)
                ? actividad?.periodos_academicos[0]
                : actividad?.periodos_academicos;
              return (
                <tr key={i} className="border-t border-slate-100">
                  <td className="px-4 py-2">{asignatura?.nombre ?? "—"}</td>
                  <td className="px-4 py-2">{periodoInfo?.nombre ?? "—"}</td>
                  <td className="px-4 py-2">{actividad?.nombre ?? "—"}</td>
                  <td className="px-4 py-2 font-medium">{nota.valor}</td>
                </tr>
              );
            })}
            {(!notas || notas.length === 0) && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                  Aún no hay notas registradas.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
