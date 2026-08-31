import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

interface FilaEstudiante {
  id: string;
  documento: string;
  fecha_matricula: string;
  activo: boolean;
  profiles: { nombre_completo: string } | null;
  cursos: { nombre: string; grados: { nombre: string } | null } | null;
}

export default async function EstudiantesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const supabase = await createClient();

  let query = supabase
    .from("estudiantes")
    .select(
      "id, documento, fecha_matricula, activo, profiles(nombre_completo), cursos(nombre, grados(nombre))",
    )
    .order("fecha_matricula", { ascending: false });

  if (q) {
    query = query.or(`documento.ilike.%${q}%`);
  }

  const { data, error } = await query.returns<FilaEstudiante[]>();

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-800">Estudiantes</h1>
        <Link
          href="/estudiantes/nuevo"
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          Matricular estudiante
        </Link>
      </div>

      <form className="mt-4" method="get">
        <input
          type="text"
          name="q"
          defaultValue={q}
          placeholder="Buscar por documento..."
          className="w-full max-w-xs rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
        />
      </form>

      {error && (
        <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
          No se pudo cargar el listado: {error.message}
        </p>
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-2">Nombre</th>
              <th className="px-4 py-2">Documento</th>
              <th className="px-4 py-2">Curso</th>
              <th className="px-4 py-2">Matrícula</th>
              <th className="px-4 py-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((estudiante) => (
              <tr key={estudiante.id} className="border-t border-slate-100">
                <td className="px-4 py-2 text-slate-700">
                  {estudiante.profiles?.nombre_completo ?? "—"}
                </td>
                <td className="px-4 py-2 text-slate-600">{estudiante.documento}</td>
                <td className="px-4 py-2 text-slate-600">
                  {estudiante.cursos
                    ? `${estudiante.cursos.grados?.nombre ?? ""} ${estudiante.cursos.nombre}`
                    : "Sin curso"}
                </td>
                <td className="px-4 py-2 text-slate-600">{estudiante.fecha_matricula}</td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      estudiante.activo
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {estudiante.activo ? "Activo" : "Inactivo"}
                  </span>
                </td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                  No hay estudiantes registrados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
