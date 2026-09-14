"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";

type ResultadoNota =
  | { ok: true; valor: number | null }
  | { ok: false; error: string };

export async function guardarNota(input: {
  estudianteId: string;
  actividadId: string;
  valor: number | null;
  observacion?: string;
}): Promise<ResultadoNota> {
  const { estudianteId, actividadId, observacion } = input;
  const valor = input.valor;

  if (valor !== null && (Number.isNaN(valor) || valor < 0 || valor > 5)) {
    return { ok: false, error: "La nota debe estar entre 0.0 y 5.0." };
  }

  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return { ok: false, error: "Sesión expirada, vuelve a iniciar sesión." };
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("rol")
    .eq("id", user.id)
    .single();

  const { data: notaExistente } = await supabase
    .from("notas")
    .select("id, valor")
    .eq("estudiante_id", estudianteId)
    .eq("actividad_id", actividadId)
    .maybeSingle();

  if (valor === null) {
    if (notaExistente) {
      const { error } = await supabase.from("notas").delete().eq("id", notaExistente.id);
      if (error) return { ok: false, error: error.message };
    }
    return { ok: true, valor: null };
  }

  const { data: guardada, error } = await supabase
    .from("notas")
    .upsert(
      {
        id: notaExistente?.id,
        estudiante_id: estudianteId,
        actividad_id: actividadId,
        valor,
        observacion: observacion ?? null,
      },
      { onConflict: "estudiante_id,actividad_id" },
    )
    .select("id")
    .single();

  if (error || !guardada) {
    return { ok: false, error: error?.message ?? "No se pudo guardar la nota." };
  }

  const admin = createAdminClient();
  await admin.from("auditoria_notas").insert({
    nota_id: guardada.id,
    estudiante_id: estudianteId,
    actividad_id: actividadId,
    usuario_id: user.id,
    rol: profile?.rol ?? null,
    valor_anterior: notaExistente?.valor ?? null,
    valor_nuevo: valor,
  });

  return { ok: true, valor };
}

export async function crearActividad(formData: FormData) {
  const asignacionDocenteId = String(formData.get("asignacion_docente_id") ?? "");
  const periodoId = String(formData.get("periodo_id") ?? "");
  const nombre = String(formData.get("nombre") ?? "").trim();
  const tipo = String(formData.get("tipo") ?? "trabajo");
  const pesoPorcentual = Number(formData.get("peso_porcentual") ?? 0);
  const esRecuperacion = formData.get("es_recuperacion") === "on";

  if (!asignacionDocenteId || !periodoId || !nombre || pesoPorcentual <= 0) {
    redirect(
      `/notas/configurar?asignacion=${asignacionDocenteId}&periodo=${periodoId}&error=campos`,
    );
  }

  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const { error } = await supabase.from("actividades_evaluacion").insert({
    asignacion_docente_id: asignacionDocenteId,
    periodo_id: periodoId,
    nombre,
    tipo,
    peso_porcentual: pesoPorcentual,
    es_recuperacion: esRecuperacion,
    created_by: user?.id,
  });

  if (error) {
    redirect(
      `/notas/configurar?asignacion=${asignacionDocenteId}&periodo=${periodoId}&error=guardar`,
    );
  }

  revalidatePath("/notas/configurar");
  redirect(`/notas/configurar?asignacion=${asignacionDocenteId}&periodo=${periodoId}`);
}

export async function desactivarActividad(formData: FormData) {
  const actividadId = String(formData.get("actividad_id") ?? "");
  const asignacionDocenteId = String(formData.get("asignacion_docente_id") ?? "");
  const periodoId = String(formData.get("periodo_id") ?? "");

  const supabase = await createClient();
  await supabase.from("actividades_evaluacion").update({ activa: false }).eq("id", actividadId);

  revalidatePath("/notas/configurar");
  redirect(`/notas/configurar?asignacion=${asignacionDocenteId}&periodo=${periodoId}`);
}

export async function cambiarEstadoPeriodo(formData: FormData) {
  const periodoId = String(formData.get("periodo_id") ?? "");
  const nuevoEstado = String(formData.get("nuevo_estado") ?? "");

  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  const { data: profile } = await supabase
    .from("profiles")
    .select("rol")
    .eq("id", user?.id ?? "")
    .single();

  const { data: periodo } = await supabase
    .from("periodos_academicos")
    .select("estado")
    .eq("id", periodoId)
    .single();

  const { error } = await supabase
    .from("periodos_academicos")
    .update({ estado: nuevoEstado })
    .eq("id", periodoId);

  if (!error) {
    const admin = createAdminClient();
    await admin.from("auditoria_periodos").insert({
      periodo_id: periodoId,
      usuario_id: user?.id,
      rol: profile?.rol ?? null,
      estado_anterior: periodo?.estado ?? null,
      estado_nuevo: nuevoEstado,
    });
  }

  revalidatePath("/periodos");
  redirect("/periodos");
}
