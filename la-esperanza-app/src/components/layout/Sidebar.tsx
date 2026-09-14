import Link from "next/link";
import { MODULOS_POR_ROL, ROL_LABEL, rutaPanel } from "@/lib/auth/roles";
import { logout } from "@/lib/auth/actions";
import type { Profile } from "@/types/database";

export function Sidebar({ profile }: { profile: Profile }) {
  const modulos = MODULOS_POR_ROL[profile.rol];

  return (
    <aside className="flex h-screen w-64 flex-col justify-between border-r border-slate-200 bg-white">
      <div>
        <div className="border-b border-slate-200 px-5 py-4">
          <p className="text-sm font-semibold text-slate-800">La Esperanza</p>
          <p className="text-xs text-slate-500">{ROL_LABEL[profile.rol]}</p>
        </div>
        <nav className="flex flex-col gap-1 p-3">
          <Link
            href={rutaPanel(profile.rol)}
            className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Panel principal
          </Link>
          {modulos.map((modulo) => (
            <Link
              key={modulo.href}
              href={modulo.href}
              className="rounded-md px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
            >
              {modulo.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="border-t border-slate-200 p-3">
        <p className="truncate px-3 text-xs text-slate-500">{profile.nombre_completo}</p>
        <form action={logout}>
          <button
            type="submit"
            className="mt-1 w-full rounded-md px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
          >
            Cerrar sesión
          </button>
        </form>
      </div>
    </aside>
  );
}
