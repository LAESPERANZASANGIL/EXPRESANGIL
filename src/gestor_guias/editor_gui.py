from __future__ import annotations

from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
import re

from .config import OficinaSettings
from .excel_processor import format_pesos, normalize_guide
from .reports import generate_daily_report, generate_operator_report, generate_operator_report_pdf
from .recaudo import generate_recaudo_report
from .relacion_ce_rr import generate_relacion_ce_rr_report
from .repository import GuiaRepository


class GuiaEditorApp:
    def __init__(self, repository: GuiaRepository, output_dir: Path, oficina: OficinaSettings) -> None:
        self.repository = repository
        self.output_dir = output_dir
        self.oficina = oficina
        self.root = tk.Tk()
        self.root.title("Editor de guias")
        self.root.geometry("1180x650")
        self.root.state("zoomed")
        # El editor se lanza desde el panel en segundo plano; sin esto la
        # ventana queda detras del navegador o minimizada.
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.after(800, lambda: self.root.attributes("-topmost", False))

        self.guia_var = tk.StringVar()
        self.operador_var = tk.StringVar()
        self.estado_var = tk.StringVar()
        self.causal_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.delete_fecha_var = tk.StringVar()
        self.delete_estado_var = tk.StringVar()
        self.delete_operador_var = tk.StringVar()
        self.delete_guia_var = tk.StringVar()
        self.report_date_var = tk.StringVar(value=date.today().isoformat())
        self.rows: list[dict] = []
        self.checked_guides: set[str] = set()

        self._build_layout()
        self._load_rows()

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        search_frame = ttk.Frame(self.root)
        search_frame.pack(fill="x", padx=12, pady=(12, 4))

        ttk.Label(search_frame, text="Buscar").pack(side="left", padx=(0, 6))
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=45)
        search_entry.pack(side="left", fill="x", expand=True)
        search_entry.bind("<KeyRelease>", lambda _event: self._refresh_table())

        ttk.Button(search_frame, text="Limpiar filtro", command=self._clear_filter).pack(
            side="left",
            padx=(8, 0),
        )
        ttk.Button(search_frame, text="Actualizar", command=self._load_rows).pack(
            side="left",
            padx=(8, 0),
        )
        ttk.Button(
            search_frame,
            text="Cerrar y volver al menu",
            command=self._close_window,
        ).pack(side="left", padx=(8, 0))

        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        columns = ("sel", "planilla", "guia", "destinatario", "direccion", "municipio", "valor", "operador", "estado", "causal")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=20,
            selectmode="extended",
        )
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        headings = {
            "sel": "",
            "planilla": "PLANILLA",
            "guia": "GUIA",
            "destinatario": "DESTINATARIO",
            "direccion": "DIRECCION",
            "municipio": "MUNICIPIO",
            "valor": "VALOR",
            "operador": "OPERADOR",
            "estado": "ESTADO",
            "causal": "CAUSAL",
        }
        widths = {
            "sel": 36,
            "planilla": 110,
            "guia": 140,
            "destinatario": 260,
            "direccion": 240,
            "municipio": 160,
            "valor": 110,
            "operador": 150,
            "estado": 150,
            "causal": 220,
        }

        for column in columns:
            self.tree.heading(column, text=headings[column])
            anchor = "center" if column == "sel" else "w"
            self.tree.column(column, width=widths[column], anchor=anchor)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-1>", self._on_tree_click)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        form = ttk.Frame(self.root)
        form.pack(fill="x", padx=12, pady=(8, 4))

        self._add_input(form, "GUIA", self.guia_var, 0, readonly=True)
        self._add_input(form, "OPERADOR", self.operador_var, 1)
        self._add_input(form, "ESTADO", self.estado_var, 2)
        self._add_input(form, "CAUSAL", self.causal_var, 3)

        ttk.Button(form, text="Guardar una guia", command=self._save_changes).grid(
            row=0,
            column=8,
            padx=(16, 0),
            sticky="ew",
        )
        ttk.Button(form, text="Aplicar a seleccionadas", command=self._save_selected_changes).grid(
            row=0,
            column=9,
            padx=(8, 0),
            sticky="ew",
        )
        ttk.Button(form, text="Eliminar seleccionadas", command=self._delete_selected).grid(
            row=0,
            column=10,
            padx=(8, 0),
            sticky="ew",
        )

        bulk_frame = ttk.LabelFrame(self.root, text="Edicion masiva por lista de guias")
        bulk_frame.pack(fill="both", expand=False, padx=12, pady=(4, 8))

        self.bulk_text = tk.Text(bulk_frame, height=4, width=80)
        self.bulk_text.pack(side="left", fill="both", expand=True, padx=(8, 8), pady=8)

        button_frame = ttk.Frame(bulk_frame)
        button_frame.pack(side="right", fill="y", padx=(0, 8), pady=8)

        ttk.Button(
            button_frame,
            text="Seleccionar lista",
            command=self._select_guides_from_text,
        ).pack(fill="x", pady=(0, 6))
        ttk.Button(
            button_frame,
            text="Aplicar a lista",
            command=self._save_bulk_text_changes,
        ).pack(fill="x", pady=(6, 0))
        ttk.Button(
            button_frame,
            text="Eliminar lista",
            command=self._delete_bulk_text_guides,
        ).pack(fill="x", pady=(6, 0))
        ttk.Button(
            button_frame,
            text="Limpiar lista",
            command=self._clear_bulk_text,
        ).pack(fill="x", pady=(6, 0))

        delete_frame = ttk.LabelFrame(
            self.root, text="Eliminar guias por fecha, estado, operador o numero de guia"
        )
        delete_frame.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Label(delete_frame, text="FECHA (YYYY-MM-DD)").grid(row=0, column=0, padx=(8, 6), pady=(8, 4), sticky="w")
        ttk.Entry(delete_frame, textvariable=self.delete_fecha_var, width=18).grid(
            row=0, column=1, padx=(0, 10), pady=(8, 4), sticky="w"
        )
        ttk.Button(delete_frame, text="Eliminar por fecha", command=self._delete_by_fecha).grid(
            row=0, column=2, padx=(0, 24), pady=(8, 4), sticky="ew"
        )

        ttk.Label(delete_frame, text="ESTADO").grid(row=0, column=3, padx=(0, 6), pady=(8, 4), sticky="w")
        ttk.Entry(delete_frame, textvariable=self.delete_estado_var, width=18).grid(
            row=0, column=4, padx=(0, 10), pady=(8, 4), sticky="w"
        )
        ttk.Button(delete_frame, text="Eliminar por estado", command=self._delete_by_estado).grid(
            row=0, column=5, padx=(0, 8), pady=(8, 4), sticky="ew"
        )

        ttk.Label(delete_frame, text="OPERADOR").grid(row=1, column=0, padx=(8, 6), pady=(4, 8), sticky="w")
        ttk.Entry(delete_frame, textvariable=self.delete_operador_var, width=18).grid(
            row=1, column=1, padx=(0, 10), pady=(4, 8), sticky="w"
        )
        ttk.Button(delete_frame, text="Eliminar por operador", command=self._delete_by_operador).grid(
            row=1, column=2, padx=(0, 24), pady=(4, 8), sticky="ew"
        )

        ttk.Label(delete_frame, text="GUIA(S)").grid(row=1, column=3, padx=(0, 6), pady=(4, 8), sticky="w")
        ttk.Entry(delete_frame, textvariable=self.delete_guia_var, width=18).grid(
            row=1, column=4, padx=(0, 10), pady=(4, 8), sticky="w"
        )
        ttk.Button(delete_frame, text="Eliminar por guia", command=self._delete_by_guia).grid(
            row=1, column=5, padx=(0, 8), pady=(4, 8), sticky="ew"
        )

        reports_frame = ttk.Frame(self.root)
        reports_frame.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Label(reports_frame, text="Fecha informes (YYYY-MM-DD)").pack(side="left", padx=(0, 6))
        ttk.Entry(reports_frame, textvariable=self.report_date_var, width=12).pack(side="left", padx=(0, 12))

        ttk.Button(
            reports_frame,
            text="Informe por operador",
            command=self._generate_operator_report,
        ).pack(side="left")
        ttk.Button(
            reports_frame,
            text="Informe del dia",
            command=self._generate_daily_report,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            reports_frame,
            text="Informe de recaudo",
            command=self._generate_recaudo_report,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            reports_frame,
            text="Relacion CE y RR",
            command=self._generate_relacion_ce_rr_report,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            reports_frame,
            text="Cerrar y volver al menu",
            command=self._close_window,
        ).pack(side="right")

        status = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status.pack(fill="x", padx=12, pady=(0, 10))

    def _add_input(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        column: int,
        readonly: bool = False,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=0, column=column * 2, padx=(0, 6), sticky="w")
        state = "readonly" if readonly else "normal"
        ttk.Entry(parent, textvariable=variable, state=state, width=22).grid(
            row=0,
            column=column * 2 + 1,
            padx=(0, 10),
            sticky="ew",
        )

    def _load_rows(self) -> None:
        self.rows = self.repository.list_all()
        self._refresh_table()

    def _refresh_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        filtered_rows = self._filtered_rows()
        for row in filtered_rows:
            self.tree.insert(
                "",
                "end",
                iid=row["guia"],
                values=(
                    "[x]" if row["guia"] in self.checked_guides else "[ ]",
                    row["planilla"] or "",
                    row["guia"],
                    row["destinatario"],
                    row["direccion"] or "",
                    row["municipio"],
                    format_pesos(row["valor"]),
                    row["operador"],
                    row["estado"],
                    row["causal"],
                ),
            )
        self.status_var.set(
            f"Guias visibles: {len(filtered_rows)} | Guias guardadas: {len(self.rows)} | "
            f"Guias marcadas: {len(self.checked_guides)}"
        )

    def _filtered_rows(self) -> list[dict]:
        search = self.search_var.get().strip().upper()
        if not search:
            return self.rows

        fields = ("planilla", "guia", "destinatario", "direccion", "municipio", "operador", "estado", "causal")
        return [
            row
            for row in self.rows
            if any(search in str(row[field]).upper() for field in fields)
        ]

    def _on_select(self, _event) -> None:
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        if len(selected) == 1:
            self.guia_var.set(values[2])
            self.operador_var.set(values[7])
            self.estado_var.set(values[8])
            self.causal_var.set(values[9])
        else:
            self.guia_var.set(f"{len(selected)} guias seleccionadas")

    def _on_tree_click(self, event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return

        row = self.tree.identify_row(event.y)
        if not row:
            return

        if row in self.checked_guides:
            self.checked_guides.discard(row)
        else:
            self.checked_guides.add(row)

        self.tree.set(row, "sel", "[x]" if row in self.checked_guides else "[ ]")
        self.status_var.set(
            f"Guias visibles: {len(self._filtered_rows())} | Guias guardadas: {len(self.rows)} | "
            f"Guias marcadas: {len(self.checked_guides)}"
        )

    def _save_changes(self) -> None:
        guia = self.guia_var.get().strip()
        if not guia:
            messagebox.showwarning("Sin guia", "Selecciona una guia antes de guardar.")
            return

        self.repository.update_tracking_fields(
            guia=guia,
            operador=self.operador_var.get().strip(),
            estado=self.estado_var.get().strip(),
            causal=self.causal_var.get().strip(),
        )
        self._load_rows()
        messagebox.showinfo("Cambios guardados", f"Se actualizo la guia {guia}.")

    def _save_selected_changes(self) -> None:
        selected_guides = self._target_guides()
        if not selected_guides:
            messagebox.showwarning("Sin seleccion", "Marca o selecciona una o varias guias.")
            return

        updated = self.repository.update_many_tracking_fields(
            guias=selected_guides,
            operador=self.operador_var.get().strip(),
            estado=self.estado_var.get().strip(),
            causal=self.causal_var.get().strip(),
        )
        self.checked_guides.clear()
        self._load_rows()
        messagebox.showinfo("Cambios guardados", f"Se actualizaron {updated} guias.")

    def _delete_selected(self) -> None:
        selected_guides = self._target_guides()
        if not selected_guides:
            messagebox.showwarning("Sin seleccion", "Marca o selecciona una o varias guias.")
            return

        if not messagebox.askyesno(
            "Confirmar eliminacion", f"Se eliminaran {len(selected_guides)} guia(s). ¿Continuar?"
        ):
            return

        deleted = self.repository.delete_many(selected_guides)
        self.checked_guides.clear()
        self._load_rows()
        messagebox.showinfo("Guias eliminadas", f"Se eliminaron {deleted} guia(s).")

    def _delete_by_fecha(self) -> None:
        fecha = self.delete_fecha_var.get().strip()
        if not fecha:
            messagebox.showwarning("Sin fecha", "Escribe una fecha en formato YYYY-MM-DD.")
            return

        if not messagebox.askyesno(
            "Confirmar eliminacion", f"Se eliminaran todas las guias con fecha {fecha}. ¿Continuar?"
        ):
            return

        deleted = self.repository.delete_by_fecha(fecha)
        self.checked_guides.clear()
        self._load_rows()
        self.delete_fecha_var.set("")
        messagebox.showinfo("Guias eliminadas", f"Se eliminaron {deleted} guia(s) con fecha {fecha}.")

    def _delete_by_estado(self) -> None:
        estado = self.delete_estado_var.get().strip()
        if not estado:
            messagebox.showwarning("Sin estado", "Escribe un estado.")
            return

        if not messagebox.askyesno(
            "Confirmar eliminacion", f"Se eliminaran todas las guias con estado '{estado}'. ¿Continuar?"
        ):
            return

        deleted = self.repository.delete_by_estado(estado)
        self.checked_guides.clear()
        self._load_rows()
        self.delete_estado_var.set("")
        messagebox.showinfo("Guias eliminadas", f"Se eliminaron {deleted} guia(s) con estado '{estado}'.")

    def _delete_by_operador(self) -> None:
        operador = self.delete_operador_var.get().strip()
        if not operador:
            messagebox.showwarning("Sin operador", "Escribe un operador.")
            return

        if not messagebox.askyesno(
            "Confirmar eliminacion",
            f"Se eliminaran todas las guias del operador '{operador}'. ¿Continuar?",
        ):
            return

        deleted = self.repository.delete_by_operador(operador)
        self.checked_guides.clear()
        self._load_rows()
        self.delete_operador_var.set("")
        messagebox.showinfo(
            "Guias eliminadas", f"Se eliminaron {deleted} guia(s) del operador '{operador}'."
        )

    def _delete_by_guia(self) -> None:
        text = self.delete_guia_var.get()
        guides = [normalize_guide(match.group(0)) for match in re.finditer(r"\d{6,}", text)]
        if not guides:
            messagebox.showwarning(
                "Sin guia", "Escribe uno o varios numeros de guia (separados por coma o espacio)."
            )
            return

        if not messagebox.askyesno(
            "Confirmar eliminacion", f"Se eliminaran {len(guides)} guia(s). ¿Continuar?"
        ):
            return

        deleted = self.repository.delete_many(guides)
        self.checked_guides.clear()
        self._load_rows()
        self.delete_guia_var.set("")
        messagebox.showinfo("Guias eliminadas", f"Se eliminaron {deleted} de {len(guides)} guia(s).")

    def _delete_bulk_text_guides(self) -> None:
        guides = self._guides_from_text()
        if not guides:
            messagebox.showwarning("Sin guias", "Pega o escribe una lista de guias.")
            return

        if not messagebox.askyesno(
            "Confirmar eliminacion", f"Se eliminaran las {len(guides)} guia(s) de la lista. ¿Continuar?"
        ):
            return

        deleted = self.repository.delete_many(guides)
        self.checked_guides.clear()
        self._load_rows()
        self.bulk_text.delete("1.0", "end")
        messagebox.showinfo("Guias eliminadas", f"Se eliminaron {deleted} de {len(guides)} guia(s).")

    def _target_guides(self) -> list[str]:
        if self.checked_guides:
            return list(self.checked_guides)
        return list(self.tree.selection())

    def _save_bulk_text_changes(self) -> None:
        guides = self._guides_from_text()
        if not guides:
            messagebox.showwarning("Sin guias", "Pega o escribe una lista de guias.")
            return

        updated = self.repository.update_many_tracking_fields(
            guias=guides,
            operador=self.operador_var.get().strip(),
            estado=self.estado_var.get().strip(),
            causal=self.causal_var.get().strip(),
        )
        self._load_rows()
        self.bulk_text.delete("1.0", "end")
        messagebox.showinfo("Cambios guardados", f"Se actualizaron {updated} guias de la lista.")

    def _get_report_date(self) -> date:
        value = self.report_date_var.get().strip()
        try:
            return date.fromisoformat(value)
        except ValueError:
            messagebox.showwarning("Fecha invalida", "Usa el formato YYYY-MM-DD. Se usara la fecha de hoy.")
            return date.today()

    def _generate_operator_report(self) -> None:
        target_date = self._get_report_date()
        try:
            output_path = generate_operator_report(self.repository, self.output_dir, target_date)
            pdf_path = generate_operator_report_pdf(self.repository, self.output_dir, target_date)
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Error", f"No se pudo generar el informe: {error}")
            return

        messagebox.showinfo(
            "Informe generado",
            f"Informe por operador generado en:\n{output_path}\n\nInforme PDF generado en:\n{pdf_path}",
        )

    def _generate_daily_report(self) -> None:
        try:
            output_path = generate_daily_report(self.repository, self.output_dir, self._get_report_date())
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Error", f"No se pudo generar el informe: {error}")
            return

        messagebox.showinfo("Informe generado", f"Informe del dia generado en:\n{output_path}")

    def _generate_recaudo_report(self) -> None:
        try:
            output_path = generate_recaudo_report(self.repository, self.output_dir, self._get_report_date())
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Error", f"No se pudo generar el informe: {error}")
            return

        messagebox.showinfo("Informe generado", f"Informe de recaudo generado en:\n{output_path}")

    def _generate_relacion_ce_rr_report(self) -> None:
        try:
            output_path = generate_relacion_ce_rr_report(
                self.repository,
                self.output_dir,
                self._get_report_date(),
                admin_name=self.oficina.admin_name,
                oficina_nombre=self.oficina.nombre,
            )
        except Exception as error:  # noqa: BLE001
            messagebox.showerror("Error", f"No se pudo generar el informe: {error}")
            return

        messagebox.showinfo("Informe generado", f"Relacion de guias CE y RR generada en:\n{output_path}")

    def _select_guides_from_text(self) -> None:
        guides = set(self._guides_from_text())
        if not guides:
            messagebox.showwarning("Sin guias", "Pega o escribe una lista de guias.")
            return

        self.tree.selection_remove(self.tree.selection())
        found = 0
        for guide in guides:
            if self.tree.exists(guide):
                self.tree.selection_add(guide)
                found += 1

        if found:
            first = self.tree.selection()[0]
            self.tree.see(first)
        self.status_var.set(f"Guias encontradas en la tabla visible: {found} de {len(guides)}")

    def _guides_from_text(self) -> list[str]:
        text = self.bulk_text.get("1.0", "end")
        return [normalize_guide(match.group(0)) for match in re.finditer(r"\d{6,}", text)]

    def _clear_bulk_text(self) -> None:
        self.bulk_text.delete("1.0", "end")

    def _clear_filter(self) -> None:
        self.search_var.set("")
        self._refresh_table()

    def _close_window(self) -> None:
        self.root.destroy()


def run_editor(repository: GuiaRepository, output_dir: Path, oficina: OficinaSettings) -> None:
    GuiaEditorApp(repository, output_dir, oficina).run()
