import { createClient } from "@/lib/supabase/server";
import { calcularAcumulado, calcularDesempeno, calcularPromedioAnual } from "@/lib/calificaciones/calculos";

export interface AsignaturaBoletin {
  asignatura_id: string;
  asignatura_nombre: string;
  porPeriodo: Record<string, number | null>; // periodo_id -> acumulado
  promedioAnual: number | null;
  desempenoAnual: string | null;
}

export interface BoletinData {
  estudiante: { id: string; nombre_completo: string };
  curso: { id: string; nombre: string } | null;
  anioAcademico: number;
  periodos: { id: string; nombre: string }[];
  asignaturas: AsignaturaBoletin[];
}

export async function obtenerBoletinEstudiante(
  estudianteId: string,
  anioAcademico: number,
): Promise<BoletinData | null> {
  const supabase = await createClient();

  const { data: estudiante } = await supabase
    .from("estudiantes")
    .select("id, curso_id, profiles(nombre_completo), cursos(id, nombre)")
    .eq("id", estudianteId)
    .single();

  if (!estudiante) return null;

  const perfil = Array.isArray(estudiante.profiles) ? estudiante.profiles[0] : estudiante.profiles;
  const curso = Array.isArray(estudiante.cursos) ? estudiante.cursos[0] : estudiante.cursos;

  const { data: periodos } = await supabase
    .from("periodos_academicos")
    .select("id, nombre")
    .eq("anio_academico", anioAcademico)
    .order("orden");

  if (!estudiante.curso_id || !periodos?.length) {
    return {
      estudiante: { id: estudiante.id, nombre_completo: perfil?.nombre_completo ?? "—" },
      curso: curso ? { id: curso.id, nombre: curso.nombre } : null,
      anioAcademico,
      periodos: periodos ?? [],
      asignaturas: [],
    };
  }

  const { data: asignaciones } = await supabase
    .from("asignaciones_docente")
    .select("id, asignaturas(id, nombre)")
    .eq("curso_id", estudiante.curso_id)
    .eq("anio_academico", anioAcademico);

  const asignaturas: AsignaturaBoletin[] = [];

  for (const asignacion of asignaciones ?? []) {
    const asignatura = Array.isArray(asignacion.asignaturas)
      ? asignacion.asignaturas[0]
      : asignacion.asignaturas;
    if (!asignatura) continue;

    const { data: actividades } = await supabase
      .from("actividades_evaluacion")
      .select("id, peso_porcentual, es_recuperacion, periodo_id")
      .eq("asignacion_docente_id", asignacion.id)
      .eq("activa", true);

    const { data: notas } = await supabase
      .from("notas")
      .select("actividad_id, valor")
      .eq("estudiante_id", estudianteId)
      .in("actividad_id", (actividades ?? []).map((a) => a.id));

    const notasPorActividad: Record<string, number | null> = {};
    for (const nota of notas ?? []) {
      notasPorActividad[nota.actividad_id] = nota.valor;
    }

    const porPeriodo: Record<string, number | null> = {};
    for (const periodo of periodos) {
      const actividadesPeriodo = (actividades ?? []).filter((a) => a.periodo_id === periodo.id);
      porPeriodo[periodo.id] = calcularAcumulado(notasPorActividad, actividadesPeriodo);
    }

    const promedioAnual = calcularPromedioAnual(Object.values(porPeriodo));

    asignaturas.push({
      asignatura_id: asignatura.id,
      asignatura_nombre: asignatura.nombre,
      porPeriodo,
      promedioAnual,
      desempenoAnual: calcularDesempeno(promedioAnual),
    });
  }

  asignaturas.sort((a, b) => a.asignatura_nombre.localeCompare(b.asignatura_nombre));

  return {
    estudiante: { id: estudiante.id, nombre_completo: perfil?.nombre_completo ?? "—" },
    curso: curso ? { id: curso.id, nombre: curso.nombre } : null,
    anioAcademico,
    periodos,
    asignaturas,
  };
}

export async function listarEstudiantesCurso(
  cursoId: string,
): Promise<{ id: string; nombre_completo: string }[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("estudiantes")
    .select("id, profiles(nombre_completo)")
    .eq("curso_id", cursoId)
    .eq("activo", true);

  return (data ?? [])
    .map((fila) => {
      const perfil = Array.isArray(fila.profiles) ? fila.profiles[0] : fila.profiles;
      return { id: fila.id, nombre_completo: perfil?.nombre_completo ?? "—" };
    })
    .sort((a, b) => a.nombre_completo.localeCompare(b.nombre_completo));
}
