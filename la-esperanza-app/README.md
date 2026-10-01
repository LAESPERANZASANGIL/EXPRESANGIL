# La Esperanza — Sistema académico

Aplicación web académica de la Institución Educativa La Esperanza. Next.js
(App Router) + TypeScript + Tailwind CSS + Supabase (Auth y Postgres).

## Estado actual

Arquitectura base: autenticación, layout por rol, navegación, esquema de
base de datos inicial y pantallas placeholder por módulo. La lógica
detallada de cada módulo (CRUD, reportes, PDFs) se construye en etapas
siguientes.

## Roles

`rector`, `administrador`, `secretaria`, `docente`, `padre`, `estudiante`.
Cada rol tiene su panel (`/[rol]`) y ve un subconjunto de módulos definido
en `src/lib/auth/roles.ts`.

## Estructura

```
src/
  app/
    (auth)/login          login con Supabase Auth (email + contraseña)
    (dashboard)/<rol>      panel principal de cada rol
    (dashboard)/<modulo>   estudiantes, grados, docentes, asignaturas,
                           periodos, notas, asistencia, mensajeria,
                           boletines, certificados
  components/
    layout/                Sidebar, layout de módulos en construcción
  lib/
    auth/                  roles, navegación por rol, server actions de login/logout
    supabase/               clientes de Supabase (browser, server, middleware)
  types/
    database.ts             tipos que reflejan el esquema de Postgres
supabase/
  migrations/0001_init.sql   esquema inicial (perfiles, estructura académica,
                              notas, asistencia, mensajería, boletines, certificados)
```

## Configuración

1. Crear un proyecto en [Supabase](https://supabase.com).
2. Copiar `.env.example` a `.env.local` y completar:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
3. Aplicar la migración `supabase/migrations/0001_init.sql` en el proyecto
   de Supabase (SQL editor o `supabase db push`).
4. Crear usuarios en Supabase Auth y su fila correspondiente en `profiles`
   con el `rol` adecuado.

## Desarrollo

```bash
npm install
npm run dev
```

Abrir [http://localhost:3000](http://localhost:3000).
