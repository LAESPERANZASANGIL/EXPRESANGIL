import type { RolUsuario } from "@/types/database";

export const ROLES: RolUsuario[] = [
  "rector",
  "administrador",
  "secretaria",
  "docente",
  "padre",
  "estudiante",
];

export const ROL_LABEL: Record<RolUsuario, string> = {
  rector: "Rector",
  administrador: "Administrador",
  secretaria: "Secretaría",
  docente: "Docente",
  padre: "Padre de familia",
  estudiante: "Estudiante",
};

interface ModuloNav {
  href: string;
  label: string;
}

// Define qué módulos ve cada rol en el menú lateral. El acceso real a los
// datos lo controla RLS en Supabase; esto solo arma la navegación.
export const MODULOS_POR_ROL: Record<RolUsuario, ModuloNav[]> = {
  rector: [
    { href: "/estudiantes", label: "Estudiantes" },
    { href: "/grados", label: "Grados y cursos" },
    { href: "/docentes", label: "Docentes" },
    { href: "/asignaturas", label: "Asignaturas" },
    { href: "/periodos", label: "Periodos académicos" },
    { href: "/notas", label: "Notas" },
    { href: "/asistencia", label: "Asistencia" },
    { href: "/mensajeria", label: "Mensajería" },
    { href: "/boletines", label: "Boletines" },
    { href: "/certificados", label: "Certificados" },
  ],
  administrador: [
    { href: "/estudiantes", label: "Estudiantes" },
    { href: "/grados", label: "Grados y cursos" },
    { href: "/docentes", label: "Docentes" },
    { href: "/asignaturas", label: "Asignaturas" },
    { href: "/periodos", label: "Periodos académicos" },
    { href: "/mensajeria", label: "Mensajería" },
    { href: "/certificados", label: "Certificados" },
  ],
  secretaria: [
    { href: "/estudiantes", label: "Estudiantes" },
    { href: "/grados", label: "Grados y cursos" },
    { href: "/mensajeria", label: "Mensajería" },
    { href: "/boletines", label: "Boletines" },
    { href: "/certificados", label: "Certificados" },
  ],
  docente: [
    { href: "/notas", label: "Notas" },
    { href: "/asistencia", label: "Asistencia" },
    { href: "/mensajeria", label: "Mensajería" },
  ],
  padre: [
    { href: "/notas", label: "Notas" },
    { href: "/asistencia", label: "Asistencia" },
    { href: "/mensajeria", label: "Mensajería" },
    { href: "/boletines", label: "Boletines" },
  ],
  estudiante: [
    { href: "/notas", label: "Mis notas" },
    { href: "/asistencia", label: "Mi asistencia" },
    { href: "/mensajeria", label: "Mensajería" },
    { href: "/boletines", label: "Mis boletines" },
  ],
};

export function rutaPanel(rol: RolUsuario): string {
  return `/${rol}`;
}
