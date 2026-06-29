import { createClient } from "@/lib/supabase/server";
import { obtenerBoletinEstudiante, listarEstudiantesCurso } from "@/lib/boletines/queries";
import { BotonDescargarBoletin } from "@/components/boletines/BotonDescargarBoletin";

export default async function BoletinesPage({
  searchParams,
}: {
  searchParams: Promise<{ curso?: string; anio?: string }>;
}) {
  const { curso, anio } = await searchParams;
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
    return <BoletinesConsulta rol={profile.rol} userId={user!.id} />;
  }

  const { data: cursos } = await supabase
    .from("cursos")
    .select("id, nombre, anio_academico")
    .order("anio_academico", { ascending: false })
    .order("nombre");

  const cursoId = curso ?? cursos?.[0]?.id ?? "";
  const cursoSeleccionado = cursos?.find((c) => c.id === cursoId);
  const anioAcademico = anio ? Number(anio) : cursoSeleccionado?.anio_academico ?? new Date().getFullYear();

  const estudiantes = cursoId ? await listarEstudiantesCurso(cursoId) : [];

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-800">Boletines</h1>
      <p className="mt-1 text-sm text-slate-500">
        Genera el boletín académico en PDF de cada estudiante, con el promedio por periodo,
        el promedio anual y el desempeño calculados automáticamente a partir de las notas.
      </p>

      <form className="mt-4 flex flex-wrap gap-3" method="get">
        <select name="curso" defaultValue={cursoId} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
          <option value="">Selecciona curso</option>
          {cursos?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nombre} ({c.anio_academico})
            </option>
          ))}
        </select>
        <button type="submit" className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
          Ver curso
        </button>
      </form>

      {cursoId && (
        <div className="mt-6 overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-2">Estudiante</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {estudiantes.map((estudiante) => (
                <FilaBoletin
                  key={estudiante.id}
                  estudianteId={estudiante.id}
                  nombre={estudiante.nombre_completo}
                  anioAcademico={anioAcademico}
                />
              ))}
              {estudiantes.length === 0 && (
                <tr>
                  <td colSpan={2} className="px-4 py-6 text-center text-slate-400">
                    No hay estudiantes activos en este curso.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

async function FilaBoletin({
  estudianteId,
  nombre,
  anioAcademico,
}: {
  estudianteId: string;
  nombre: string;
  anioAcademico: number;
}) {
  const boletin = await obtenerBoletinEstudiante(estudianteId, anioAcademico);

  return (
    <tr className="border-t border-slate-100">
      <td className="px-4 py-2 text-slate-700">{nombre}</td>
      <td className="px-4 py-2 text-right">
        {boletin && boletin.asignaturas.length > 0 ? (
          <BotonDescargarBoletin data={boletin} />
        ) : (
          <span className="text-xs text-slate-400">Sin notas registradas</span>
        )}
      </td>
    </tr>
  );
}

async function BoletinesConsulta({ rol, userId }: { rol: "estudiante" | "padre"; userId: string }) {
  const supabase = await createClient();

  let estudianteIds: string[] = [userId];
  if (rol === "padre") {
    const { data } = await supabase
      .from("acudientes_estudiantes")
      .select("estudiante_id")
      .eq("acudiente_id", userId);
    estudianteIds = (data ?? []).map((fila) => fila.estudiante_id);
  }

  const { data: estudiantes } = await supabase
    .from("estudiantes")
    .select("id, profiles(nombre_completo)")
    .in("id", estudianteIds);

  const anioAcademico = new Date().getFullYear();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-800">
        {rol === "padre" ? "Boletines de tus acudidos" : "Mis boletines"}
      </h1>

      <div className="mt-4 space-y-3">
        {(estudiantes ?? []).map((estudiante) => {
          const perfil = Array.isArray(estudiante.profiles) ? estudiante.profiles[0] : estudiante.profiles;
          return (
            <FilaConsulta
              key={estudiante.id}
              estudianteId={estudiante.id}
              nombre={perfil?.nombre_completo ?? "—"}
              anioAcademico={anioAcademico}
            />
          );
        })}
        {(!estudiantes || estudiantes.length === 0) && (
          <p className="text-sm text-slate-400">No hay estudiantes asociados a tu cuenta.</p>
        )}
      </div>
    </div>
  );
}

async function FilaConsulta({
  estudianteId,
  nombre,
  anioAcademico,
}: {
  estudianteId: string;
  nombre: string;
  anioAcademico: number;
}) {
  const boletin = await obtenerBoletinEstudiante(estudianteId, anioAcademico);

  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div>
        <p className="text-sm font-medium text-slate-700">{nombre}</p>
        <p className="text-xs text-slate-400">Año académico {anioAcademico}</p>
      </div>
      {boletin && boletin.asignaturas.length > 0 ? (
        <BotonDescargarBoletin data={boletin} />
      ) : (
        <span className="text-xs text-slate-400">Sin notas registradas</span>
      )}
    </div>
  );
}
