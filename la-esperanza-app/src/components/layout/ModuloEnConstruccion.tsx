export function ModuloEnConstruccion({ titulo }: { titulo: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-slate-800">{titulo}</h1>
      <p className="mt-2 text-sm text-slate-500">
        Este módulo está en construcción. La estructura de datos y rutas ya
        existen; falta conectar la lógica y las pantallas detalladas.
      </p>
    </div>
  );
}
