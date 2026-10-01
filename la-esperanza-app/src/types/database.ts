export type RolUsuario =
  | "rector"
  | "administrador"
  | "secretaria"
  | "docente"
  | "padre"
  | "estudiante";

export interface Profile {
  id: string;
  rol: RolUsuario;
  nombre_completo: string;
  documento: string | null;
  telefono: string | null;
  avatar_url: string | null;
  activo: boolean;
  created_at: string;
  updated_at: string;
}

export interface Grado {
  id: string;
  nombre: string;
  nivel: string;
  orden: number;
}

export type EstadoPeriodo = "planeado" | "abierto" | "cerrado";

export interface PeriodoAcademico {
  id: string;
  nombre: string;
  anio_academico: number;
  fecha_inicio: string;
  fecha_fin: string;
  orden: number;
  estado: EstadoPeriodo;
}

export interface Curso {
  id: string;
  grado_id: string;
  nombre: string;
  anio_academico: number;
  director_docente_id: string | null;
}

export interface Asignatura {
  id: string;
  nombre: string;
  area: string | null;
}

export interface Docente {
  id: string;
  especialidad: string | null;
}

export interface AsignacionDocente {
  id: string;
  docente_id: string;
  asignatura_id: string;
  curso_id: string;
  anio_academico: number;
}

export interface Estudiante {
  id: string;
  curso_id: string | null;
  documento: string;
  fecha_nacimiento: string | null;
  fecha_matricula: string;
  activo: boolean;
}

export interface AcudienteEstudiante {
  acudiente_id: string;
  estudiante_id: string;
  parentesco: string | null;
}

export type TipoActividad =
  | "trabajo"
  | "quiz"
  | "evaluacion"
  | "proyecto"
  | "laboratorio"
  | "recuperacion"
  | "nivelacion";

export interface ActividadEvaluacion {
  id: string;
  asignacion_docente_id: string;
  periodo_id: string;
  nombre: string;
  tipo: TipoActividad;
  peso_porcentual: number;
  orden: number;
  es_recuperacion: boolean;
  activa: boolean;
  created_at: string;
  created_by: string | null;
}

export interface Nota {
  id: string;
  estudiante_id: string;
  asignatura_id: string;
  periodo_id: string;
  docente_id: string | null;
  actividad_id: string;
  valor: number;
  tipo: string;
  observacion: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditoriaNota {
  id: string;
  nota_id: string;
  estudiante_id: string;
  actividad_id: string;
  usuario_id: string | null;
  rol: string | null;
  valor_anterior: number | null;
  valor_nuevo: number | null;
  motivo: string | null;
  created_at: string;
}

export interface AuditoriaPeriodo {
  id: string;
  periodo_id: string;
  usuario_id: string | null;
  rol: string | null;
  estado_anterior: string | null;
  estado_nuevo: string | null;
  created_at: string;
}

export type EstadoAsistencia =
  | "presente"
  | "tarde"
  | "falla_justificada"
  | "falla_injustificada";

export interface Asistencia {
  id: string;
  estudiante_id: string;
  curso_id: string;
  fecha: string;
  estado: EstadoAsistencia;
  observacion: string | null;
  registrado_por: string | null;
  created_at: string;
}

export interface Mensaje {
  id: string;
  remitente_id: string;
  destinatario_id: string;
  asunto: string;
  contenido: string;
  leido: boolean;
  created_at: string;
}

export interface Boletin {
  id: string;
  estudiante_id: string;
  periodo_id: string;
  url_pdf: string | null;
  generado_en: string;
  generado_por: string | null;
}

export interface Certificado {
  id: string;
  estudiante_id: string;
  tipo: string;
  url_pdf: string | null;
  generado_en: string;
  generado_por: string | null;
}
