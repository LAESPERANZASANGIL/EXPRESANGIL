"use client";

import { descargarPdfBoletin } from "@/lib/boletines/pdf";
import type { BoletinData } from "@/lib/boletines/queries";

export function BotonDescargarBoletin({ data }: { data: BoletinData }) {
  return (
    <button
      type="button"
      onClick={() => descargarPdfBoletin(data)}
      className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
    >
      Descargar PDF
    </button>
  );
}
