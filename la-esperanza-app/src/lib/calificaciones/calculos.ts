export interface FilaPlanilla {
  estudiante_id: string;
  nombre_completo: string;
  notas: Record<string, number | null>; // actividad_id -> valor
}

export interface PlanillaData {
  actividades: {
    id: string;
    nombre: string;
    tipo: string;
    peso_porcentual: number;
    es_recuperacion: boolean;
  }[];
  filas: FilaPlanilla[];
  periodoEstado: string | null;
}

export function calcularAcumulado(
  notas: Record<string, number | null>,
  actividades: { id: string; peso_porcentual: number; es_recuperacion: boolean }[],
): number | null {
  const ordinarias = actividades.filter((a) => !a.es_recuperacion);
  const pesoTotal = ordinarias.reduce((acc, a) => acc + a.peso_porcentual, 0);
  if (pesoTotal === 0) return null;

  let suma = 0;
  let pesoConNota = 0;
  for (const actividad of ordinarias) {
    const valor = notas[actividad.id];
    if (valor !== null && valor !== undefined) {
      suma += valor * actividad.peso_porcentual;
      pesoConNota += actividad.peso_porcentual;
    }
  }
  if (pesoConNota === 0) return null;

  // Recuperación, si existe y tiene nota, reemplaza el acumulado ordinario
  // (regla institucional simple: la recuperación sustituye, no promedia).
  const recuperacion = actividades.find((a) => a.es_recuperacion);
  if (recuperacion) {
    const valorRecuperacion = notas[recuperacion.id];
    if (valorRecuperacion !== null && valorRecuperacion !== undefined) {
      return Math.round(valorRecuperacion * 10) / 10;
    }
  }

  return Math.round((suma / pesoTotal) * 10) / 10;
}

export type Desempeno = "Bajo" | "Básico" | "Alto" | "Superior";

// Escala institucional estándar (0.0 - 5.0) usada en Colombia.
export function calcularDesempeno(promedio: number | null): Desempeno | null {
  if (promedio === null) return null;
  if (promedio < 3.0) return "Bajo";
  if (promedio < 4.0) return "Básico";
  if (promedio < 4.6) return "Alto";
  return "Superior";
}

export function calcularPromedioAnual(promediosPorPeriodo: (number | null)[]): number | null {
  const validos = promediosPorPeriodo.filter((p): p is number => p !== null);
  if (validos.length === 0) return null;
  const suma = validos.reduce((acc, p) => acc + p, 0);
  return Math.round((suma / validos.length) * 10) / 10;
}

export function colorDesempeno(desempeno: Desempeno | null): string {
  switch (desempeno) {
    case "Bajo":
      return "bg-red-50 text-red-700";
    case "Básico":
      return "bg-amber-50 text-amber-700";
    case "Alto":
      return "bg-emerald-50 text-emerald-700";
    case "Superior":
      return "bg-blue-50 text-blue-700";
    default:
      return "bg-slate-100 text-slate-400";
  }
}
