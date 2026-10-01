-- Institución Educativa La Esperanza
-- Esquema inicial: roles, perfiles, estructura académica, notas, asistencia,
-- mensajería, boletines y certificados.

create extension if not exists "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Roles y perfiles
-- ---------------------------------------------------------------------------

create type rol_usuario as enum (
  'rector',
  'administrador',
  'secretaria',
  'docente',
  'padre',
  'estudiante'
);

create table profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  rol rol_usuario not null,
  nombre_completo text not null,
  documento text,
  telefono text,
  avatar_url text,
  activo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Estructura académica: grados, cursos, periodos, asignaturas
-- ---------------------------------------------------------------------------

create table grados (
  id uuid primary key default uuid_generate_v4(),
  nombre text not null unique, -- ej. "Sexto", "Décimo"
  nivel text not null,         -- preescolar | primaria | secundaria | media
  orden int not null default 0
);

create table periodos_academicos (
  id uuid primary key default uuid_generate_v4(),
  nombre text not null,        -- ej. "Periodo 1"
  anio_academico int not null,
  fecha_inicio date not null,
  fecha_fin date not null,
  orden int not null default 0,
  unique (anio_academico, orden)
);

create table cursos (
  id uuid primary key default uuid_generate_v4(),
  grado_id uuid not null references grados (id) on delete restrict,
  nombre text not null,         -- ej. "6-A"
  anio_academico int not null,
  director_docente_id uuid references profiles (id) on delete set null,
  unique (nombre, anio_academico)
);

create table asignaturas (
  id uuid primary key default uuid_generate_v4(),
  nombre text not null unique,
  area text
);

create table docentes (
  id uuid primary key references profiles (id) on delete cascade,
  especialidad text
);

create table asignaciones_docente (
  id uuid primary key default uuid_generate_v4(),
  docente_id uuid not null references docentes (id) on delete cascade,
  asignatura_id uuid not null references asignaturas (id) on delete cascade,
  curso_id uuid not null references cursos (id) on delete cascade,
  anio_academico int not null,
  unique (docente_id, asignatura_id, curso_id, anio_academico)
);

-- ---------------------------------------------------------------------------
-- Estudiantes y acudientes
-- ---------------------------------------------------------------------------

create table estudiantes (
  id uuid primary key references profiles (id) on delete cascade,
  curso_id uuid references cursos (id) on delete set null,
  documento text not null unique,
  fecha_nacimiento date,
  fecha_matricula date not null default current_date,
  activo boolean not null default true
);

create table acudientes_estudiantes (
  acudiente_id uuid not null references profiles (id) on delete cascade,
  estudiante_id uuid not null references estudiantes (id) on delete cascade,
  parentesco text,
  primary key (acudiente_id, estudiante_id)
);

-- ---------------------------------------------------------------------------
-- Notas
-- ---------------------------------------------------------------------------

create table notas (
  id uuid primary key default uuid_generate_v4(),
  estudiante_id uuid not null references estudiantes (id) on delete cascade,
  asignatura_id uuid not null references asignaturas (id) on delete cascade,
  periodo_id uuid not null references periodos_academicos (id) on delete cascade,
  docente_id uuid references docentes (id) on delete set null,
  valor numeric(3, 1) not null check (valor >= 0 and valor <= 5),
  tipo text not null default 'periodo', -- periodo | recuperacion | final
  observacion text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (estudiante_id, asignatura_id, periodo_id, tipo)
);

-- ---------------------------------------------------------------------------
-- Asistencia / fallas
-- ---------------------------------------------------------------------------

create type estado_asistencia as enum ('presente', 'tarde', 'falla_justificada', 'falla_injustificada');

create table asistencia (
  id uuid primary key default uuid_generate_v4(),
  estudiante_id uuid not null references estudiantes (id) on delete cascade,
  curso_id uuid not null references cursos (id) on delete cascade,
  fecha date not null,
  estado estado_asistencia not null default 'presente',
  observacion text,
  registrado_por uuid references profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  unique (estudiante_id, fecha)
);

-- ---------------------------------------------------------------------------
-- Mensajería
-- ---------------------------------------------------------------------------

create table mensajes (
  id uuid primary key default uuid_generate_v4(),
  remitente_id uuid not null references profiles (id) on delete cascade,
  destinatario_id uuid not null references profiles (id) on delete cascade,
  asunto text not null,
  contenido text not null,
  leido boolean not null default false,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Boletines y certificados
-- ---------------------------------------------------------------------------

create table boletines (
  id uuid primary key default uuid_generate_v4(),
  estudiante_id uuid not null references estudiantes (id) on delete cascade,
  periodo_id uuid not null references periodos_academicos (id) on delete cascade,
  url_pdf text,
  generado_en timestamptz not null default now(),
  generado_por uuid references profiles (id) on delete set null,
  unique (estudiante_id, periodo_id)
);

create table certificados (
  id uuid primary key default uuid_generate_v4(),
  estudiante_id uuid not null references estudiantes (id) on delete cascade,
  tipo text not null, -- estudio | conducta | notas | desempeño
  url_pdf text,
  generado_en timestamptz not null default now(),
  generado_por uuid references profiles (id) on delete set null
);

-- ---------------------------------------------------------------------------
-- RLS: habilitado en todas las tablas. Políticas detalladas se agregan
-- en una migración posterior, una vez definida la lógica de cada módulo.
-- ---------------------------------------------------------------------------

alter table profiles enable row level security;
alter table grados enable row level security;
alter table periodos_academicos enable row level security;
alter table cursos enable row level security;
alter table asignaturas enable row level security;
alter table docentes enable row level security;
alter table asignaciones_docente enable row level security;
alter table estudiantes enable row level security;
alter table acudientes_estudiantes enable row level security;
alter table notas enable row level security;
alter table asistencia enable row level security;
alter table mensajes enable row level security;
alter table boletines enable row level security;
alter table certificados enable row level security;

create policy "usuarios ven su propio perfil" on profiles
  for select using (auth.uid() = id);

create policy "usuarios actualizan su propio perfil" on profiles
  for update using (auth.uid() = id);
