import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { rutaPanel } from "@/lib/auth/roles";
import type { RolUsuario } from "@/types/database";

export default async function HomePage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("rol")
    .eq("id", user.id)
    .single();

  redirect(rutaPanel((profile?.rol as RolUsuario) ?? "estudiante"));
}
