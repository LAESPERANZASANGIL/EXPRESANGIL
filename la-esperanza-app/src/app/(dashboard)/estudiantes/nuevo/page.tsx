import { createClient } from "@/lib/supabase/server";
import { matricularEstudiante } from "@/lib/estudiantes/actions";

const ERRORES: Record<string, string> = {
  campos: "Completa nombre, documento y correo.",
  usuario: "No se pudo crear el usuario (¿el correo ya existe?).",
  perfil: "No se pudo crear el perfil del estudiante.",
  estudiante: "No se pudo registrar la matrícula.",
};

export default async function NuevoEstudiantePage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  const supabase = await createClient();
  const { data: cursos } = await supabase
    .from("cursos")
    .select("id, nombre, grados(nombre)")
    .order("nombre");

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-semibold text-slate-800">Matricular estudiante</h1>
      <p className="mt-1 text-sm text-slate-500">
        Crea el usuario de acceso y la ficha del estudiante.
      </p>

      {error && (
        <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
          {ERRORES[error] ?? "Ocurrió un error inesperado."}
        </p>
      )}

      <form action={matricularEstudiante} className="mt-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700">Nombre completo</label>
          <input
            name="nombre_completo"
            required
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700">Documento</label>
          <input
            name="documento"
            required
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700">Correo</label>
          <input
            type="email"
            name="email"
            required
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700">Fecha de nacimiento</label>
          <input
            type="date"
            name="fecha_nacimiento"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700">Curso</label>
          <select
            name="curso_id"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
          >
            <option value="">Sin asignar</option>
            {cursos?.map((curso) => (
              <option key={curso.id} value={curso.id}>
                {curso.grados?.[0]?.nombre} {curso.nombre}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          className="w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          Matricular
        </button>
      </form>
    </div>
  );
}
