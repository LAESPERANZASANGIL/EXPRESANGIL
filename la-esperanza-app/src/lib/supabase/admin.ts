import { createClient as createSupabaseClient } from "@supabase/supabase-js";

// Cliente con la service role key: solo se usa en server actions /
// route handlers para operaciones administrativas (ej. crear usuarios
// de Auth al matricular un estudiante). Nunca exponer al navegador.
export function createAdminClient() {
  return createSupabaseClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { autoRefreshToken: false, persistSession: false } },
  );
}
