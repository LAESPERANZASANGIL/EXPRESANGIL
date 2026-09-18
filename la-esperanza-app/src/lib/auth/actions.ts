"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { rutaPanel } from "@/lib/auth/roles";
import type { RolUsuario } from "@/types/database";

export async function login(formData: FormData) {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");

  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });

  if (error || !data.user) {
    redirect("/login?error=credenciales");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("rol")
    .eq("id", data.user.id)
    .single();

  redirect(rutaPanel((profile?.rol as RolUsuario) ?? "estudiante"));
}

export async function logout() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}
