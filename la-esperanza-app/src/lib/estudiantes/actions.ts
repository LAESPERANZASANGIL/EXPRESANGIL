"use server";

import { randomUUID } from "node:crypto";
import { redirect } from "next/navigation";
import { createAdminClient } from "@/lib/supabase/admin";

export async function matricularEstudiante(formData: FormData) {
  const nombreCompleto = String(formData.get("nombre_completo") ?? "").trim();
  const documento = String(formData.get("documento") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const cursoId = String(formData.get("curso_id") ?? "") || null;
  const fechaNacimiento = String(formData.get("fecha_nacimiento") ?? "") || null;

  if (!nombreCompleto || !documento || !email) {
    redirect("/estudiantes/nuevo?error=campos");
  }

  const admin = createAdminClient();

  const { data: usuario, error: errorUsuario } = await admin.auth.admin.createUser({
    email,
    password: randomUUID(),
    email_confirm: true,
  });

  if (errorUsuario || !usuario.user) {
    redirect("/estudiantes/nuevo?error=usuario");
  }

  const { error: errorPerfil } = await admin.from("profiles").insert({
    id: usuario.user.id,
    rol: "estudiante",
    nombre_completo: nombreCompleto,
    documento,
  });

  if (errorPerfil) {
    redirect("/estudiantes/nuevo?error=perfil");
  }

  const { error: errorEstudiante } = await admin.from("estudiantes").insert({
    id: usuario.user.id,
    curso_id: cursoId,
    documento,
    fecha_nacimiento: fechaNacimiento,
  });

  if (errorEstudiante) {
    redirect("/estudiantes/nuevo?error=estudiante");
  }

  redirect("/estudiantes");
}
