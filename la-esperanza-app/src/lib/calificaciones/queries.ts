import { createClient } from "@/lib/supabase/server";
import type { FilaPlanilla, PlanillaData } from "@/lib/calificaciones/calculos";

export type { FilaPlanilla, PlanillaData };

export interface OpcionAsignacion {
  id: string;
  curso_id: string;
  curso_nombre: string;
  asignatura_id: string;
  asignatura_nombre: string;
  anio_academico: number;
}

export async function listarAsignacionesDocente(docenteId: string): Promise<OpcionAsignacion[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("asignaciones_docente")
    .select("id, anio_academico, cursos(id, nombre), asignaturas(id, nombre)")
    .eq("docente_id", docenteId)
    .order("anio_academico", { ascending: false });

  return (data ?? []).map((fila) => {
    const curso = Array.isArray(fila.cursos) ? fila.cursos[0] : fila.cursos;
    const asignatura = Array.isArray(fila.asignaturas) ? fila.asignaturas[0] : fila.asignaturas;
    return {
      id: fila.id,
      curso_id: curso?.id ?? "",
      curso_nombre: curso?.nombre ?? "",
      asignatura_id: asignatura?.id ?? "",
      asignatura_nombre: asignatura?.nombre ?? "",
      anio_academico: fila.anio_academico,
    };
  });
}

export async function obtenerPlanilla(
  asignacionDocenteId: string,
  periodoId: string,
): Promise<PlanillaData> {
  const supabase = await createClient();

  const { data: asignacion } = await supabase
    .from("asignaciones_docente")
    .select("curso_id")
    .eq("id", asignacionDocenteId)
    .single();

  const { data: periodo } = await supabase
    .from("periodos_academicos")
    .select("estado")
    .eq("id", periodoId)
    .maybeSingle();

  const { data: actividades } = await supabase
    .from("actividades_evaluacion")
    .select("id, nombre, tipo, peso_porcentual, es_recuperacion")
    .eq("asignacion_docente_id", asignacionDocenteId)
    .eq("periodo_id", periodoId)
    .eq("activa", true)
    .order("orden");

  if (!asignacion?.curso_id || !actividades?.length) {
    return { actividades: actividades ?? [], filas: [], periodoEstado: periodo?.estado ?? null };
  }

  const { data: estudiantes } = await supabase
    .from("estudiantes")
    .select("id, profiles(nombre_completo)")
    .eq("curso_id", asignacion.curso_id)
    .eq("activo", true);

  const actividadIds = actividades.map((a) => a.id);
  const { data: notas } = await supabase
    .from("notas")
    .select("estudiante_id, actividad_id, valor")
    .in("actividad_id", actividadIds);

  const filas: FilaPlanilla[] = (estudiantes ?? [])
    .map((estudiante) => {
      const perfil = Array.isArray(estudiante.profiles)
        ? estudiante.profiles[0]
        : estudiante.profiles;
      const notasEstudiante: Record<string, number | null> = {};
      for (const actividad of actividades) {
        const nota = notas?.find(
          (n) => n.estudiante_id === estudiante.id && n.actividad_id === actividad.id,
        );
        notasEstudiante[actividad.id] = nota?.valor ?? null;
      }
      return {
        estudiante_id: estudiante.id,
        nombre_completo: perfil?.nombre_completo ?? "—",
        notas: notasEstudiante,
      };
    })
    .sort((a, b) => a.nombre_completo.localeCompare(b.nombre_completo));

  return { actividades, filas, periodoEstado: periodo?.estado ?? null };
}
