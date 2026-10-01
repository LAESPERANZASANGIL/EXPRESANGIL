-- Módulo de calificaciones: configuración académica controlada por
-- rector/administrador/secretaría, planilla de actividades por docente,
-- bloqueo de periodos y auditoría de cambios de notas.

-- ---------------------------------------------------------------------------
-- Periodos: estado de apertura/cierre
-- ---------------------------------------------------------------------------

alter table periodos_academicos
  add column estado text not null default 'planeado'
    check (estado in ('planeado', 'abierto', 'cerrado'));

-- ---------------------------------------------------------------------------
-- Actividades de evaluación: la columna real de la planilla.
-- La crea/edita Rector, Administrador o Secretaría; el docente solo
-- diligencia notas sobre actividades ya configuradas.
-- ---------------------------------------------------------------------------

create table actividades_evaluacion (
  id uuid primary key default uuid_generate_v4(),
  asignacion_docente_id uuid not null references asignaciones_docente (id) on delete cascade,
  periodo_id uuid not null references periodos_academicos (id) on delete cascade,
  nombre text not null,
  tipo text not null default 'trabajo',
  -- trabajo | quiz | evaluacion | proyecto | laboratorio | recuperacion | nivelacion
  peso_porcentual numeric(5, 2) not null check (peso_porcentual > 0 and peso_porcentual <= 100),
  orden int not null default 0,
  es_recuperacion boolean not null default false,
  activa boolean not null default true,
  created_at timestamptz not null default now(),
  created_by uuid references profiles (id) on delete set null
);

create index idx_actividades_evaluacion_asignacion_periodo
  on actividades_evaluacion (asignacion_docente_id, periodo_id);

-- ---------------------------------------------------------------------------
-- Notas: ahora cuelgan de una actividad concreta, no de un "tipo" fijo.
-- Se preserva la tabla; se agrega actividad_id y se relaja la unicidad
-- anterior (estudiante+asignatura+periodo+tipo) por una nueva
-- (estudiante+actividad).
-- ---------------------------------------------------------------------------

alter table notas
  add column actividad_id uuid references actividades_evaluacion (id) on delete cascade;

do $$
declare
  v_constraint text;
begin
  select conname into v_constraint
  from pg_constraint
  where conrelid = 'notas'::regclass
    and contype = 'u'
    and conname like 'notas_estudiante_id_asignatura_id_periodo_id%';

  if v_constraint is not null then
    execute format('alter table notas drop constraint %I', v_constraint);
  end if;
end $$;

alter table notas
  add constraint notas_estudiante_actividad_unique unique (estudiante_id, actividad_id);

-- ---------------------------------------------------------------------------
-- Bloqueo de edición: una nota no se puede insertar/actualizar si el
-- periodo de su actividad no está "abierto", ni si el estudiante está
-- retirado. Defensa en profundidad junto con las policies de RLS y la
-- capa de servidor.
-- ---------------------------------------------------------------------------

create or replace function fn_validar_nota() returns trigger as $$
declare
  v_estado_periodo text;
  v_estudiante_activo boolean;
begin
  select p.estado into v_estado_periodo
  from actividades_evaluacion a
  join periodos_academicos p on p.id = a.periodo_id
  where a.id = new.actividad_id;

  if v_estado_periodo is distinct from 'abierto' then
    raise exception 'El periodo de esta actividad no está abierto para edición.';
  end if;

  select activo into v_estudiante_activo
  from estudiantes
  where id = new.estudiante_id;

  if v_estudiante_activo is distinct from true then
    raise exception 'No se pueden registrar notas para un estudiante que no está activo.';
  end if;

  new.updated_at := now();
  return new;
end;
$$ language plpgsql;

create trigger trg_validar_nota
  before insert or update on notas
  for each row execute function fn_validar_nota();

-- ---------------------------------------------------------------------------
-- Auditoría de notas: nunca se elimina, registra quién cambió qué.
-- ---------------------------------------------------------------------------

create table auditoria_notas (
  id uuid primary key default uuid_generate_v4(),
  nota_id uuid not null,
  estudiante_id uuid not null references estudiantes (id) on delete cascade,
  actividad_id uuid not null references actividades_evaluacion (id) on delete cascade,
  usuario_id uuid references profiles (id) on delete set null,
  rol text,
  valor_anterior numeric(3, 1),
  valor_nuevo numeric(3, 1),
  motivo text,
  created_at timestamptz not null default now()
);

create index idx_auditoria_notas_nota on auditoria_notas (nota_id);

-- ---------------------------------------------------------------------------
-- Auditoría de bloqueo/desbloqueo de periodos.
-- ---------------------------------------------------------------------------

create table auditoria_periodos (
  id uuid primary key default uuid_generate_v4(),
  periodo_id uuid not null references periodos_academicos (id) on delete cascade,
  usuario_id uuid references profiles (id) on delete set null,
  rol text,
  estado_anterior text,
  estado_nuevo text,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------

alter table actividades_evaluacion enable row level security;
alter table auditoria_notas enable row level security;
alter table auditoria_periodos enable row level security;

-- Estructura académica (actividades): solo rector/administrador/secretaría
-- la crean o modifican; docentes y directivos pueden verla.
create policy "ver actividades del propio rol" on actividades_evaluacion
  for select using (
    exists (
      select 1 from profiles
      where profiles.id = auth.uid()
        and profiles.rol in ('rector', 'administrador', 'secretaria')
    )
    or exists (
      select 1 from asignaciones_docente ad
      where ad.id = actividades_evaluacion.asignacion_docente_id
        and ad.docente_id = auth.uid()
    )
  );

create policy "gestionar actividades: rector admin secretaria" on actividades_evaluacion
  for all using (
    exists (
      select 1 from profiles
      where profiles.id = auth.uid()
        and profiles.rol in ('rector', 'administrador', 'secretaria')
    )
  );

-- Notas: el docente asignado a esa actividad puede insertar/editar mientras
-- el periodo esté abierto (lo valida también el trigger); estudiante y
-- acudiente solo leen lo propio; directivos leen todo.
create policy "docente gestiona notas de sus actividades" on notas
  for all using (
    exists (
      select 1 from actividades_evaluacion a
      join asignaciones_docente ad on ad.id = a.asignacion_docente_id
      where a.id = notas.actividad_id
        and ad.docente_id = auth.uid()
    )
  );

create policy "directivos leen todas las notas" on notas
  for select using (
    exists (
      select 1 from profiles
      where profiles.id = auth.uid()
        and profiles.rol in ('rector', 'administrador', 'secretaria')
    )
  );

create policy "estudiante lee sus propias notas" on notas
  for select using (estudiante_id = auth.uid());

create policy "acudiente lee notas de sus acudidos" on notas
  for select using (
    exists (
      select 1 from acudientes_estudiantes ae
      where ae.estudiante_id = notas.estudiante_id
        and ae.acudiente_id = auth.uid()
    )
  );

-- Auditoría: solo lectura para directivos; inserción la hace la capa de
-- servidor (service role) junto con cada cambio de nota o periodo.
create policy "directivos leen auditoria de notas" on auditoria_notas
  for select using (
    exists (
      select 1 from profiles
      where profiles.id = auth.uid()
        and profiles.rol in ('rector', 'administrador', 'secretaria')
    )
  );

create policy "directivos leen auditoria de periodos" on auditoria_periodos
  for select using (
    exists (
      select 1 from profiles
      where profiles.id = auth.uid()
        and profiles.rol in ('rector', 'administrador', 'secretaria')
    )
  );

-- Apertura/cierre de periodos: solo rector y administrador desbloquean un
-- periodo cerrado; secretaría puede abrir/cerrar en el flujo normal.
create policy "rector admin secretaria cambian estado de periodo" on periodos_academicos
  for update using (
    exists (
      select 1 from profiles
      where profiles.id = auth.uid()
        and profiles.rol in ('rector', 'administrador', 'secretaria')
    )
  );
