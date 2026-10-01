# MASTER PLAN — ERP Educativo Institución Educativa La Esperanza

Estado: **propuesta de arquitectura, pendiente de aprobación**. No se ha escrito
código de aplicación a partir de este documento. El módulo de Estudiantes y la
base de autenticación/roles que ya existen en `la-esperanza-app/` se tratan
como el cimiento sobre el que crece este plan, no como algo a rehacer.

Objetivo de escala: >5.000 estudiantes activos, multi-año académico, operación
continua durante años, con migraciones y crecimiento de módulos sin reescrituras.

---

## 1. Arquitectura general del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                         Next.js (App Router)                    │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │ Server         │  │ Route         │  │ Client Components    │ │
│  │ Components     │  │ Handlers      │  │ (interactividad,     │ │
│  │ (lectura,      │  │ (/api/*,      │  │  formularios,        │ │
│  │  SSR)          │  │  webhooks,    │  │  tablas, gráficos)   │ │
│  │               │  │  PDFs, jobs)  │  │                      │ │
│  └──────┬────────┘  └──────┬────────┘  └──────────┬───────────┘ │
└─────────┼──────────────────┼──────────────────────┼─────────────┘
          │                  │                      │
          ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Capa de dominio (server-only)                │
│   src/server/<modulo>/{queries,mutations,validators,policies}   │
│   - Toda regla de negocio vive aquí, no en componentes ni en    │
│     route handlers (que solo orquestan).                       │
└──────────────────────────┬────────────────────────────────────-─┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Supabase                                │
│  ┌───────────┐ ┌───────────────┐ ┌───────────┐ ┌──────────────┐ │
│  │ Postgres   │ │ Auth          │ │ Storage   │ │ Edge          │ │
│  │ + RLS      │ │ (JWT, roles)  │ │ (PDFs,    │ │ Functions     │ │
│  │            │ │               │ │  fotos)   │ │ (jobs pesados,│ │
│  │            │ │               │ │           │ │  cron)        │ │
│  └───────────┘ └───────────────┘ └───────────┘ └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
          ▲                                              │
          │                                              ▼
   pg_cron / triggers                          Webhooks salientes
   (cierre de periodos,                        (notificaciones email/
    recordatorios de pago)                      push, pasarela de pago)
```

**Decisiones clave:**

- **Monolito modular**, no microservicios. A 5.000 estudiantes, Postgres bien
  indexado + Next.js en un solo proyecto es más barato de operar y más rápido
  de evolucionar que un sistema distribuido. Los módulos están aislados por
  carpeta y por esquema de datos, no por proceso — la división física se puede
  hacer después si un módulo concreto (ej. facturación) lo justifica.
- **Postgres es la fuente de verdad y el motor de reglas críticas.** Todo lo
  que rompe la integridad del colegio si falla (notas duplicadas, cupos
  excedidos, doble cobro) se valida con `CHECK`, `UNIQUE`, `FOREIGN KEY` y
  triggers, no solo en la capa de aplicación.
- **RLS (Row Level Security) es el límite de autorización real.** El rol de la
  capa de aplicación es UX y conveniencia; la capa que de verdad impide que un
  padre vea las notas de otro estudiante es RLS en Postgres.
- **Multi-año académico desde el día uno.** Casi todas las tablas operativas
  llevan `anio_academico` o cuelgan de `periodos_academicos`. Nada se borra al
  cerrar el año: se archiva.
- **Generación de documentos (boletines, certificados, recibos) es asíncrona.**
  Se encola, se genera en background (Edge Function o job), se guarda en
  Storage, y la UI hace polling/Realtime sobre el estado — para que generar
  3.000 boletines al cierre de periodo no bloquee request HTTP alguno.

---

## 2. Estructura completa de carpetas

```
la-esperanza-app/
├── MASTER_PLAN.md
├── README.md
├── supabase/
│   ├── migrations/              # una migración por cambio, nunca editar las viejas
│   ├── seed.sql                 # datos de referencia (roles, tipos de documento...)
│   └── functions/                # Edge Functions (Deno)
│       ├── generar-boletin/
│       ├── generar-certificado/
│       ├── cerrar-periodo/
│       └── recordatorio-pagos/
├── src/
│   ├── app/
│   │   ├── (public)/             # landing, recuperar contraseña
│   │   ├── (auth)/
│   │   │   └── login/
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx        # shell: sidebar + topbar por rol
│   │   │   ├── [rol]/            # panel principal (rector, docente, ...)
│   │   │   ├── estudiantes/
│   │   │   ├── matricula/
│   │   │   ├── grados/
│   │   │   ├── docentes/
│   │   │   ├── asignaturas/
│   │   │   ├── periodos/
│   │   │   ├── notas/
│   │   │   ├── asistencia/
│   │   │   ├── disciplina/
│   │   │   ├── mensajeria/
│   │   │   ├── boletines/
│   │   │   ├── certificados/
│   │   │   ├── finanzas/
│   │   │   │   ├── conceptos/
│   │   │   │   ├── facturacion/
│   │   │   │   ├── pagos/
│   │   │   │   └── reportes/
│   │   │   ├── inventario/        # fase posterior
│   │   │   ├── biblioteca/        # fase posterior
│   │   │   ├── transporte/        # fase posterior
│   │   │   ├── recursos-humanos/  # fase posterior
│   │   │   └── reportes/          # tableros transversales
│   │   └── api/
│   │       ├── auth/callback/
│   │       ├── webhooks/
│   │       │   └── pasarela-pagos/
│   │       └── documentos/
│   │           ├── boletines/[id]/
│   │           └── certificados/[id]/
│   ├── components/
│   │   ├── ui/                   # botones, inputs, tabla, modal (design system propio)
│   │   ├── layout/                # Sidebar, Topbar, Breadcrumbs
│   │   └── <modulo>/              # componentes específicos de un módulo
│   ├── server/                    # capa de dominio, SOLO se importa desde server
│   │   ├── estudiantes/
│   │   │   ├── queries.ts
│   │   │   ├── mutations.ts
│   │   │   ├── validators.ts      # zod schemas
│   │   │   └── policies.ts        # quién puede hacer qué (defensa en profundidad sobre RLS)
│   │   ├── matricula/
│   │   ├── academico/             # grados, cursos, asignaturas, periodos, notas, asistencia
│   │   ├── finanzas/
│   │   ├── mensajeria/
│   │   ├── documentos/            # orquesta boletines/certificados
│   │   └── shared/                # paginación, búsqueda, auditoría
│   ├── lib/
│   │   ├── supabase/              # client.ts, server.ts, admin.ts, middleware.ts
│   │   ├── auth/                  # roles.ts, sesión, server actions de login
│   │   ├── pdf/                   # generación de PDF (boletines, certificados, recibos)
│   │   ├── email/                 # plantillas y envío
│   │   └── utils/
│   ├── types/
│   │   ├── database.ts            # generado desde el esquema de Supabase
│   │   └── dominio.ts             # tipos de negocio que no son 1:1 con tablas
│   └── proxy.ts                   # control de acceso a nivel de ruta
├── tests/
│   ├── unit/                      # validators, cálculo de promedios, mora, etc.
│   └── e2e/                       # flujos críticos con Playwright
└── docs/
    ├── adr/                       # Architecture Decision Records
    └── runbooks/                  # cierre de periodo, respaldo, incidentes
```

**Regla de dependencia:** `app/` solo llama a `server/`; `server/` es lo único
que toca Supabase directamente para escritura; los Client Components solo
llaman a server actions o a `/api`, nunca al cliente de Supabase con
operaciones de escritura sensibles.

---

## 3-4. Arquitectura de base de datos (PostgreSQL/Supabase) y relaciones

### 3.1 Convenciones

- PK `uuid` (`uuid_generate_v4()`), salvo tablas de catálogo pequeñas (`smallint`).
- Toda tabla transaccional tiene `created_at`, `updated_at`, y donde aplica
  `created_by` / `updated_by` para auditoría.
- Nombres en español, snake_case, igual que el código existente.
- Ningún DELETE físico de datos académicos o financieros: columna `anulado_en`
  / `estado` + tablas de auditoría. Borrado físico solo en catálogos sin uso.
- Particionamiento por `anio_academico` se evalúa en Fase 4 si el volumen de
  `notas`/`asistencia` lo justifica (a 5.000 estudiantes × ~10 asignaturas ×
  4 periodos ≈ 200k filas/año en notas — no requiere partición todavía, pero
  el diseño de índices ya lo anticipa).

### 3.2 Dominios y tablas

**Identidad y organización**
- `instituciones` (preparar multi-sede aunque hoy haya una sola)
- `sedes` (fk `institucion_id`)
- `profiles` (fk `auth.users`, `rol`, `nombre_completo`, `documento`, `sede_id`)
- `roles_permisos` (catálogo de permisos finos, ver sección 5)

**Estructura académica**
- `anios_academicos` (`anio`, `fecha_inicio`, `fecha_fin`, `estado: planeado|activo|cerrado`)
- `periodos_academicos` (fk `anio_academico_id`, `nombre`, `orden`, `fecha_inicio`, `fecha_fin`, `estado`)
- `niveles` (preescolar, primaria, secundaria, media)
- `grados` (fk `nivel_id`, `nombre`, `orden`)
- `cursos` (fk `grado_id`, `anio_academico_id`, `nombre`, `director_docente_id`, `cupo_maximo`)
- `asignaturas` (`nombre`, `area_id`)
- `areas` (agrupador de asignaturas, ej. "Ciencias Naturales")
- `plan_estudios` (fk `grado_id`, `asignatura_id`, `anio_academico_id`, `intensidad_horaria`)
- `asignaciones_docente` (fk `docente_id`, `asignatura_id`, `curso_id`, `anio_academico_id`)

**Personas**
- `docentes` (fk `profiles.id`, `especialidad`, `tipo_contrato`)
- `estudiantes` (fk `profiles.id`, `curso_id`, `documento`, `fecha_nacimiento`, `estado: activo|retirado|graduado|trasladado`)
- `acudientes_estudiantes` (fk `acudiente_id` → profiles, fk `estudiante_id`, `parentesco`, `es_responsable_pago`)
- `historico_matriculas` (fk `estudiante_id`, `anio_academico_id`, `curso_id`, `fecha_matricula`, `estado`) — una fila por año, nunca se sobrescribe

**Matrícula y admisiones**
- `solicitudes_admision` (datos del aspirante, `estado: pendiente|en_revision|aceptada|rechazada`, `curso_solicitado_id`)
- `documentos_matricula` (fk `solicitud_id` o `estudiante_id`, `tipo`, `url_storage`, `verificado`)
- `matriculas` (fk `estudiante_id`, `anio_academico_id`, `curso_id`, `fecha`, `estado`, `tipo: nueva|renovacion|traslado`)

**Académico (notas, asistencia, disciplina)**
- `periodos_evaluacion` = alias conceptual de `periodos_academicos` (no se duplica)
- `notas` (fk `estudiante_id`, `asignatura_id`, `periodo_id`, `docente_id`, `valor`, `tipo: periodo|recuperacion|final`)
- `escalas_valoracion` (catálogo configurable: "Superior 4.6-5.0", etc. — desacopla la lógica de boletines de números mágicos)
- `asistencia` (fk `estudiante_id`, `curso_id`, `fecha`, `estado: presente|tarde|falla_justificada|falla_injustificada`)
- `observaciones_disciplinarias` (fk `estudiante_id`, `tipo`, `descripcion`, `registrado_por`, `fecha`)

**Comunicación**
- `mensajes` (fk `remitente_id`, `destinatario_id`, `asunto`, `contenido`, `leido`)
- `circulares` (anuncios institucionales masivos, fk `curso_id` opcional para alcance segmentado)
- `notificaciones` (cola de notificaciones push/email, fk `usuario_id`, `tipo`, `payload`, `enviado_en`)

**Documentos**
- `boletines` (fk `estudiante_id`, `periodo_id`, `url_pdf`, `estado: pendiente|generado|error`)
- `certificados` (fk `estudiante_id`, `tipo`, `url_pdf`, `generado_por`)
- `plantillas_documento` (versión de la plantilla usada — para que un boletín viejo no cambie si la plantilla cambia)

**Financiero**
- `conceptos_pago` (`nombre` — matrícula, pensión, transporte —, `valor_base`, `recurrente: boolean`)
- `tarifas` (fk `concepto_id`, `grado_id`, `anio_academico_id`, `valor`) — la tarifa puede variar por grado/año sin tocar el concepto
- `facturas` (fk `estudiante_id`, `periodo_facturacion`, `fecha_vencimiento`, `estado: pendiente|pagada|vencida|anulada`, `total`)
- `factura_detalle` (fk `factura_id`, `concepto_id`, `valor`)
- `pagos` (fk `factura_id`, `monto`, `metodo`, `referencia_pasarela`, `fecha`, `estado`)
- `acuerdos_pago` (fk `estudiante_id`, plan de cuotas para mora — opcional, fase posterior)

**Auditoría y soporte transversal**
- `auditoria_eventos` (`tabla`, `registro_id`, `accion`, `usuario_id`, `payload_anterior`, `payload_nuevo`, `created_at`)
- `archivos` (capa única sobre Supabase Storage: `bucket`, `path`, `tipo`, `propietario_id`)

### 3.3 Relaciones críticas (resumen)

```
instituciones 1─n sedes
sedes 1─n cursos, docentes, estudiantes
anios_academicos 1─n periodos_academicos, cursos, matriculas
grados 1─n cursos; cursos 1─n estudiantes (vía curso_id en estudiantes, snapshot del año activo)
estudiantes 1─n historico_matriculas (histórico real, no se sobrescribe)
estudiantes n─n profiles(acudientes) vía acudientes_estudiantes
cursos n─n asignaturas vía plan_estudios; docentes n─n (asignatura,curso) vía asignaciones_docente
estudiantes 1─n notas, asistencia, observaciones_disciplinarias
estudiantes 1─n facturas 1─n factura_detalle; facturas 1─n pagos
estudiantes 1─n boletines, certificados
profiles 1─n mensajes (como remitente y como destinatario)
```

### 3.4 Índices que importan a 5.000+ estudiantes

- `notas(estudiante_id, periodo_id)`, `asistencia(estudiante_id, fecha)`,
  `facturas(estudiante_id, estado)`, `estudiantes(curso_id)` — son los
  patrones de consulta más frecuentes (boletín de un estudiante, estado de
  cuenta, lista de un curso).
- Índices parciales sobre `estado = 'activo'` en `estudiantes` y `facturas`
  vencidas, porque el 90% de las consultas operativas filtran por eso.

---

## 5. Roles y permisos

### 5.1 Roles (ya definidos en `profiles.rol`)

`rector`, `administrador`, `secretaria`, `docente`, `padre`, `estudiante`.

A esta escala conviene añadir, sin romper lo existente:

- `coordinador` (académico/disciplina, alcance por sede o por nivel)
- `tesoreria` (financiero, sin acceso a notas)
- `auxiliar_admisiones` (matrícula, sin acceso a finanzas ni notas)

`rol` sigue siendo el campo "grueso" para navegación; los permisos finos se
resuelven con una tabla `permisos` + `rol_permisos` (muchos-a-muchos) para
poder ajustar sin migrar el enum cada vez que cambian las reglas del colegio.

### 5.2 Matriz de permisos (alto nivel)

| Módulo | Rector | Administrador | Secretaría | Coordinador | Docente | Tesorería | Padre | Estudiante |
|---|---|---|---|---|---|---|---|---|
| Estudiantes (ver) | Todos | Todos | Todos | Su nivel | Sus cursos | Solo facturación | Sus acudidos | Él mismo |
| Estudiantes (crear/editar) | Sí | Sí | Sí | No | No | No | No | No |
| Matrícula | Sí | Sí | Sí | No | No | No | Solicitar | No |
| Notas (registrar) | No | No | No | No | Sus asignaturas | No | No | No |
| Notas (ver) | Todos | Todos | Todos | Su nivel | Sus cursos | No | Sus acudidos | Las suyas |
| Asistencia (registrar) | No | No | No | Su nivel | Sus cursos | No | No | No |
| Disciplina | Sí | Sí | Ver | Sí | Registrar | No | Ver | Ver |
| Mensajería | Todos pueden enviar/recibir según reglas de contacto (ver 15) |
| Finanzas | Ver todo | Ver todo | Ver | No | No | Gestionar | Su estado de cuenta | No |
| Boletines/certificados | Generar | Generar | Generar | Generar (su nivel) | No | No | Descargar (sus acudidos) | Descargar (los suyos) |

La tabla exacta se refina en Fase 1, pero esto fija el contrato de RLS:
**toda política de Postgres se escribe contra esta matriz, no al revés.**

### 5.3 Defensa en profundidad

1. **RLS en Postgres** — límite real e infranqueable.
2. **`server/<modulo>/policies.ts`** — valida intención antes de tocar la BD,
   da mensajes de error claros, evita confiar en que cada query nueva recuerde
   las reglas de RLS.
3. **UI** — oculta lo que el rol no puede usar (cosmético, no es seguridad).

---

## 6. Navegación completa de la aplicación

```
/ (redirige según rol)
/login
/(dashboard)/
├── [rol]                     → panel de inicio (KPIs según rol)
├── matricula/
│   ├── solicitudes
│   ├── solicitudes/[id]
│   └── nueva
├── estudiantes/
│   ├── (listado, filtros por curso/estado)
│   ├── nuevo
│   └── [id]/
│       ├── perfil
│       ├── academico        (notas + asistencia consolidadas)
│       ├── disciplina
│       ├── finanzas
│       └── documentos
├── grados/
│   └── [id]/cursos
├── docentes/
│   ├── (listado)
│   ├── nuevo
│   └── [id]/asignaciones
├── asignaturas/
├── periodos/
├── notas/
│   ├── (vista docente: planilla por curso+asignatura+periodo)
│   └── consolidado          (vista directiva: todos los cursos)
├── asistencia/
│   ├── tomar                (vista docente, diaria)
│   └── reportes
├── disciplina/
├── mensajeria/
│   ├── bandeja
│   ├── nuevo
│   └── circulares
├── boletines/
│   ├── generar               (masivo, por curso/periodo)
│   └── [id]
├── certificados/
│   ├── solicitar
│   └── [id]
├── finanzas/
│   ├── conceptos
│   ├── tarifas
│   ├── facturacion
│   │   ├── generar           (masivo, por periodo)
│   │   └── [id]
│   ├── pagos
│   │   └── registrar
│   └── reportes
│       ├── cartera
│       └── recaudo
└── reportes/                 (tableros transversales: matrícula, deserción, promedio institucional)
```

La navegación efectiva por rol sigue resuelta por `MODULOS_POR_ROL` (ya
existe en `src/lib/auth/roles.ts`): este árbol es el universo completo de
rutas; cada rol ve su subconjunto.

---

## 7. Módulos del sistema

**Ya construidos / en construcción:** Autenticación y roles, Estudiantes
(listado + matrícula básica).

**Núcleo académico (Fase 1-2):** Grados y cursos, Docentes, Asignaturas,
Periodos académicos, Notas, Asistencia/fallas.

**Comunicación y documentos (Fase 2-3):** Mensajería, Boletines en PDF,
Certificados institucionales.

**Matrícula y admisiones (Fase 2):** Solicitudes de admisión, proceso de
matrícula/renovación, documentos del estudiante.

**Financiero (Fase 3):** Conceptos y tarifas, facturación, pagos,
conciliación con pasarela, cartera y mora.

**Disciplina (Fase 3):** Observador del estudiante, seguimiento de casos.

**Reportes transversales (Fase 3-4):** Tableros institucionales (matrícula,
deserción, promedio, recaudo).

**Extensiones futuras (Fase 4+, fuera del alcance inicial pero
contempladas en el modelo de carpetas):** Biblioteca, transporte escolar,
inventario/recursos, recursos humanos/nómina docente.

---

## 8. Estructura del backend

No hay un "backend" separado: Next.js hace de backend vía:

- **Server Actions** para mutaciones desde formularios (matricular, registrar
  nota, registrar pago) — son el camino por defecto.
- **Route Handlers (`/api/*`)** solo donde se necesita: webhooks externos
  (pasarela de pagos), descarga de archivos binarios (PDF), endpoints que
  consume un cliente que no es la propia app (ej. futura app móvil).
- **Edge Functions de Supabase** para trabajo pesado o programado que no debe
  vivir en el ciclo de vida de un request de Next.js: generación masiva de
  boletines, cierre de periodo, recordatorios de pago, recálculo de mora.
- **`server/<modulo>/`** concentra: `queries.ts` (lectura), `mutations.ts`
  (escritura, siempre con validación zod + policy), `validators.ts`,
  `policies.ts`. Ningún componente importa el cliente de Supabase
  directamente para escribir.

## 9. Estructura del frontend

- App Router con grupos de rutas por contexto (`(auth)`, `(dashboard)`).
- Server Components por defecto; Client Components solo en hojas que
  necesitan interactividad (formularios, tablas con filtros en vivo, planillas
  de notas editables).
- **Design system propio mínimo** en `components/ui` (tabla, formulario,
  modal, badge de estado) para no repetir Tailwind crudo en cada módulo — ya
  se nota la repetición entre las pantallas de Estudiantes y Login.
- Componentes de módulo (`components/<modulo>/`) consumen `server/<modulo>/`
  vía server actions; no hay fetching ad-hoc disperso en cada página.
- Tablas grandes (estudiantes, facturas) usan paginación server-side desde el
  principio — a 5.000 estudiantes una tabla sin paginar no escala.

## 10. API que utilizará cada módulo

| Módulo | Server actions (mutación) | Route handlers (especiales) |
|---|---|---|
| Auth | `login`, `logout`, `recuperarPassword` | `/api/auth/callback` |
| Estudiantes | `matricularEstudiante`, `actualizarEstudiante`, `retirarEstudiante` | — |
| Matrícula | `crearSolicitud`, `aprobarSolicitud`, `confirmarMatricula` | `/api/documentos/matricula/[id]` (descarga) |
| Académico | `crearCurso`, `asignarDocente`, `crearPeriodo` | — |
| Notas | `guardarNota`, `cerrarPeriodoNotas` | — |
| Asistencia | `registrarAsistenciaDia` | — |
| Mensajería | `enviarMensaje`, `marcarLeido`, `publicarCircular` | — |
| Boletines | `solicitarGeneracionBoletin` (encola) | `/api/documentos/boletines/[id]` (descarga + estado) |
| Certificados | `solicitarCertificado` | `/api/documentos/certificados/[id]` |
| Finanzas | `generarFacturacionPeriodo`, `registrarPago`, `anularFactura` | `/api/webhooks/pasarela-pagos` |

Todas las mutaciones devuelven un resultado tipado (`{ ok: true, data }` o
`{ ok: false, error }`), no solo redirects con `?error=` — el patrón usado en
`matricularEstudiante` hoy es válido para flujos de una pantalla, pero a
partir de Fase 2 se migra a este formato para soportar UI más rica (toasts,
estados de carga) sin recargar la página.

## 11. Flujo de autenticación

1. Usuario entra a `/login` → Supabase Auth (email + password).
2. `proxy.ts` valida sesión en cada request; sin sesión → redirige a `/login`.
3. Tras login, se lee `profiles.rol` y se redirige a `/[rol]`.
4. Cada Server Component de dashboard vuelve a resolver el perfil (no confía
   en el estado del cliente) y aplica RLS automáticamente vía el cliente de
   Supabase autenticado con el JWT del usuario.
5. Recuperación de contraseña: flujo estándar de Supabase Auth (magic link),
   pantalla `(public)/recuperar`.
6. Cuentas de `padre`/`estudiante` se crean en el flujo de matrícula (no se
   auto-registran libremente): la institución controla quién entra.

## 12. Flujo de matrícula

```
Solicitud (aspirante) → Revisión (secretaría/admisiones)
   → Aceptada → Cargar documentos → Verificación
      → Confirmación de matrícula → Creación/activación de usuario
         (estudiante + acudiente) → Asignación a curso
            → Generación de factura de matrícula (si aplica)
```

- Año a año, los estudiantes activos pasan por **renovación** (no
  "solicitud" nueva): se crea una fila en `historico_matriculas` y se
  actualiza `estudiantes.curso_id` para el nuevo año, sin tocar el resto de
  la ficha.
- Traslados/retiros cambian `estudiantes.estado` y cierran la fila vigente de
  `historico_matriculas`; nunca se borra el estudiante.

## 13. Flujo académico

```
Inicio de año → Crear anio_academico + periodos_academicos
   → Crear/clonar cursos del año anterior → Asignar director de curso
      → Asignar docentes a (curso, asignatura) → Plan de estudios vigente
         → Periodo en curso:
            - Docentes registran notas y asistencia continuamente
            - Coordinación registra disciplina
         → Cierre de periodo (job):
            - Bloquea edición de notas del periodo
            - Encola generación de boletines del periodo
         → Cierre de año:
            - Calcula promoción/reprobación (regla configurable por colegio)
            - Archiva el año, prepara el siguiente
```

## 14. Flujo financiero

```
Definición de conceptos y tarifas (por grado/año)
   → Generación de facturación del periodo (job masivo)
      → Factura por estudiante con factura_detalle por concepto
         → Notificación al acudiente responsable de pago
            → Pago (manual en oficina o pasarela online)
               → Webhook de pasarela → registrar pago → actualizar estado factura
                  → Reportes de cartera/mora → recordatorios automáticos
```

- `acudientes_estudiantes.es_responsable_pago` determina a quién se factura
  cuando hay varios acudientes.
- Anulación de factura es un estado, no un borrado — preserva el rastro
  contable.

## 15. Flujo de comunicación

- **Mensajería 1 a 1**: reglas de contacto por rol (ej. un padre solo puede
  escribir a los docentes/coordinación de sus acudidos, no a cualquier
  docente del colegio) — se valida en `server/mensajeria/policies.ts` y en
  RLS.
- **Circulares**: anuncio institucional, alcance opcional (`curso_id`,
  `grado_id`, o institucional completo), visible como "mensaje" de solo
  lectura para el destinatario.
- **Notificaciones**: cola interna (`notificaciones`) que alimenta canales
  (email ahora; push/SMS son extensiones del mismo modelo, no un rediseño).

## 16. Flujo de generación de documentos

```
Usuario solicita boletín/certificado
   → Se crea fila en boletines/certificados con estado "pendiente"
      → Edge Function toma el job, renderiza PDF (datos + plantilla versionada)
         → Sube el PDF a Storage → actualiza fila a "generado" con url_pdf
            → UI hace poll/Realtime sobre el estado y habilita la descarga
```

- Generación **individual** (un estudiante pide su certificado) puede
  resolverse sincrónicamente si es rápida; generación **masiva** (boletines
  de un curso completo al cierre de periodo) siempre es asíncrona por colas,
  para no bloquear ni saturar memoria del proceso web.
- Las plantillas se versionan (`plantillas_documento`) para que un boletín ya
  emitido no cambie retroactivamente si la institución rediseña el formato.

## 17. Plan de desarrollo por fases

### Fase 0 — Hecho
- Arquitectura base Next.js + Supabase, auth, layout por rol, esquema inicial,
  módulo de Estudiantes (listado + matrícula simple).

### Fase 1 — Núcleo académico (siguiente paso natural)
- Grados y cursos (CRUD completo, cupos).
- Docentes (CRUD, asignaciones a curso/asignatura).
- Asignaturas y plan de estudios.
- Periodos académicos (crear, activar, cerrar).
- Refactor de `estudiantes` para usar `historico_matriculas` desde ya, antes
  de que haya datos reales que migrar.

### Fase 2 — Operación diaria del aula
- Notas (planilla por docente, consolidado directivo, cierre de periodo).
- Asistencia/fallas (toma diaria, reportes).
- Mensajería (1 a 1 + circulares).
- Solicitudes de admisión y flujo de matrícula completo (incluye documentos).

### Fase 3 — Documentos y finanzas
- Boletines en PDF (con Edge Function de generación masiva).
- Certificados institucionales.
- Módulo financiero completo: conceptos, tarifas, facturación, pagos,
  reportes de cartera.
- Disciplina (observador del estudiante).

### Fase 4 — Escala y consolidación
- Tableros transversales (reportes institucionales).
- Auditoría completa (`auditoria_eventos`) sobre todos los módulos sensibles.
- Revisión de índices/particionamiento con datos reales de producción.
- Roles finos (`coordinador`, `tesoreria`, `auxiliar_admisiones`) si la
  institución los necesita en la práctica.
- Extensiones opcionales: biblioteca, transporte, inventario, RRHH.

Cada fase termina con: migraciones aplicadas, RLS escrita y probada, tests
unitarios de las reglas de negocio nuevas, y un ADR corto si se tomó una
decisión de diseño no obvia.

---

## Pendiente de tu aprobación

No se crea ningún archivo de aplicación nuevo hasta que confirmes este plan
(o pidas ajustes). Si apruebas, el siguiente paso natural es la **Fase 1**
empezando por `grados`/`cursos`, reusando la migración `0001_init.sql` ya
existente (se ajusta con una migración nueva, no se reescribe la anterior).
