import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import type { BoletinData } from "@/lib/boletines/queries";

export function generarPdfBoletin(data: BoletinData): jsPDF {
  const doc = new jsPDF();

  doc.setFontSize(14);
  doc.text("Institución Educativa La Esperanza", 14, 16);
  doc.setFontSize(11);
  doc.text(`Boletín académico - Año ${data.anioAcademico}`, 14, 24);
  doc.text(`Estudiante: ${data.estudiante.nombre_completo}`, 14, 32);
  doc.text(`Curso: ${data.curso?.nombre ?? "—"}`, 14, 39);

  const encabezado = ["Asignatura", ...data.periodos.map((p) => p.nombre), "Promedio anual", "Desempeño"];
  const filas = data.asignaturas.map((a) => [
    a.asignatura_nombre,
    ...data.periodos.map((p) => a.porPeriodo[p.id]?.toString() ?? "—"),
    a.promedioAnual?.toString() ?? "—",
    a.desempenoAnual ?? "—",
  ]);

  autoTable(doc, {
    startY: 46,
    head: [encabezado],
    body: filas,
    styles: { fontSize: 9 },
    headStyles: { fillColor: [16, 122, 87] },
  });

  return doc;
}

export function descargarPdfBoletin(data: BoletinData) {
  const doc = generarPdfBoletin(data);
  const nombreArchivo = `boletin_${data.estudiante.nombre_completo.replace(/\s+/g, "_")}_${data.anioAcademico}.pdf`;
  doc.save(nombreArchivo);
}
