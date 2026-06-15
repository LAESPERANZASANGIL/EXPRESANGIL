from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
import re

from .repository import GuiaRepository


class GuiaEditorApp:
    def __init__(self, repository: GuiaRepository) -> None:
        self.repository = repository
        self.root = tk.Tk()
        self.root.title("Editor de guias")
        self.root.geometry("1180x650")

        self.guia_var = tk.StringVar()
        self.operador_var = tk.StringVar()
        self.estado_var = tk.StringVar()
        self.causal_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.rows: list[dict] = []

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

        columns = ("guia", "destinatario", "municipio", "valor", "operador", "estado", "causal")
        self.tree = ttk.Treeview(
            self.root,
            columns=columns,
            show="headings",
            height=20,
            selectmode="extended",
        )

        headings = {
            "guia": "GUIA",
            "destinatario": "DESTINATARIO",
            "municipio": "MUNICIPIO",
            "valor": "VALOR",
            "operador": "OPERADOR",
            "estado": "ESTADO",
            "causal": "CAUSAL",
        }
        widths = {
            "guia": 140,
            "destinatario": 260,
            "municipio": 160,
            "valor": 110,
            "operador": 150,
            "estado": 150,
            "causal": 220,
        }

        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.pack(fill="both", expand=True, padx=12, pady=(12, 6))

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
        ).pack(fill="x")

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
                    row["guia"],
                    row["destinatario"],
                    row["municipio"],
                    row["valor"],
                    row["operador"],
                    row["estado"],
                    row["causal"],
                ),
            )
        self.status_var.set(
            f"Guias visibles: {len(filtered_rows)} | Guias guardadas: {len(self.rows)}"
        )

    def _filtered_rows(self) -> list[dict]:
        search = self.search_var.get().strip().upper()
        if not search:
            return self.rows

        fields = ("guia", "destinatario", "municipio", "operador", "estado", "causal")
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
            self.guia_var.set(values[0])
            self.operador_var.set(values[4])
            self.estado_var.set(values[5])
            self.causal_var.set(values[6])
        else:
            self.guia_var.set(f"{len(selected)} guias seleccionadas")

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
        selected_guides = list(self.tree.selection())
        if not selected_guides:
            messagebox.showwarning("Sin seleccion", "Selecciona una o varias guias.")
            return

        updated = self.repository.update_many_tracking_fields(
            guias=selected_guides,
            operador=self.operador_var.get().strip(),
            estado=self.estado_var.get().strip(),
            causal=self.causal_var.get().strip(),
        )
        self._load_rows()
        messagebox.showinfo("Cambios guardados", f"Se actualizaron {updated} guias.")

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
        messagebox.showinfo("Cambios guardados", f"Se actualizaron {updated} guias de la lista.")

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
        return [match.group(0) for match in re.finditer(r"\d{6,}", text)]

    def _clear_filter(self) -> None:
        self.search_var.set("")
        self._refresh_table()


def run_editor(repository: GuiaRepository) -> None:
    GuiaEditorApp(repository).run()
