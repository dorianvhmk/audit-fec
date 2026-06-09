import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAnalysis, ReconciliationRow, RowStatus } from "../hooks/useAnalysis";
import StatusBadge from "../components/StatusBadge";
import CommentDrawer from "../components/CommentDrawer";

const API = "/api";

const fmt = (v: number | null) =>
  v === null ? "—" : v.toLocaleString("fr-FR", { minimumFractionDigits: 2 }) + " €";

const TABLE_LABELS: Record<string, string> = {
  bilan_actif: "Bilan Actif",
  bilan_passif: "Bilan Passif",
  compte_resultat: "Compte de résultat",
  unknown: "Inconnu",
};

const STATUS_ORDER: RowStatus[] = ["écart", "absent", "OK"];

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data } = useAnalysis(id);
  const [drawerRow, setDrawerRow] = useState<ReconciliationRow | null>(null);
  const [filterStatus, setFilterStatus] = useState<RowStatus | "all">("all");

  const handleExport = () => {
    window.open(`${API}/export/${id}`, "_blank");
  };

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-3 text-gray-500">
          <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Chargement…
        </div>
      </div>
    );
  }

  const isProcessing = data.status === "pending" || data.status === "processing";

  if (isProcessing) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 text-gray-600">
        <svg className="animate-spin w-10 h-10 text-blue-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        <p className="font-medium">Analyse en cours…</p>
        <p className="text-sm text-gray-400">Extraction FEC, PDF et génération des commentaires IA</p>
      </div>
    );
  }

  if (data.status === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="max-w-md text-center">
          <p className="text-red-600 font-medium mb-2">Erreur lors de l'analyse</p>
          <p className="text-sm text-gray-500 mb-4">{data.results?.error}</p>
          <button onClick={() => navigate("/")} className="text-sm text-blue-600 hover:underline">
            ← Nouvelle analyse
          </button>
        </div>
      </div>
    );
  }

  const rows = data.results?.rows ?? [];
  const filtered = filterStatus === "all" ? rows : rows.filter((r) => r.status === filterStatus);

  const counts = {
    OK: rows.filter((r) => r.status === "OK").length,
    écart: rows.filter((r) => r.status === "écart").length,
    absent: rows.filter((r) => r.status === "absent").length,
  };

  return (
    <>
      <div className="min-h-screen flex flex-col">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div>
            <button onClick={() => navigate("/")} className="text-xs text-gray-400 hover:text-gray-600 mb-1 flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Nouvelle analyse
            </button>
            <h1 className="font-semibold text-gray-900">{data.client_name}</h1>
            <p className="text-xs text-gray-400">
              {data.results?.fec_row_count} écritures FEC · {data.results?.pdf_page_count} pages PDF
            </p>
          </div>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z" />
            </svg>
            Exporter Excel
          </button>
        </header>

        {/* Summary cards */}
        <div className="px-6 py-4 flex gap-3">
          {STATUS_ORDER.map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(filterStatus === s ? "all" : s)}
              className={`flex-1 max-w-[140px] rounded-xl border px-4 py-3 text-left transition-all
                ${filterStatus === s ? "ring-2 ring-offset-1" : "hover:border-gray-400"}
                ${s === "OK" ? "border-green-200 bg-green-50 ring-green-400" : ""}
                ${s === "écart" ? "border-yellow-200 bg-yellow-50 ring-yellow-400" : ""}
                ${s === "absent" ? "border-red-200 bg-red-50 ring-red-400" : ""}
              `}
            >
              <p className="text-2xl font-bold text-gray-900">{counts[s]}</p>
              <p className="text-xs text-gray-500 capitalize">{s}</p>
            </button>
          ))}
          {filterStatus !== "all" && (
            <button onClick={() => setFilterStatus("all")} className="text-xs text-blue-600 hover:underline self-center ml-1">
              Tout afficher
            </button>
          )}
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto px-6 pb-8">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-gray-200">
                <th className="text-left py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide w-1/3">Poste</th>
                <th className="text-left py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">Tableau</th>
                <th className="text-right py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">Plaquette</th>
                <th className="text-right py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">FEC</th>
                <th className="text-right py-2 pr-4 text-xs font-semibold text-gray-500 uppercase tracking-wide">Écart</th>
                <th className="text-center py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">Statut</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-gray-100 hover:bg-gray-50 cursor-pointer"
                  onClick={() => setDrawerRow(row)}
                >
                  <td className="py-2.5 pr-4 font-medium text-gray-800 truncate max-w-xs">{row.label}</td>
                  <td className="py-2.5 pr-4 text-gray-500 whitespace-nowrap">
                    {TABLE_LABELS[row.table_type] ?? row.table_type}
                  </td>
                  <td className="py-2.5 pr-4 text-right font-mono text-gray-700">{fmt(row.plaquette_amount)}</td>
                  <td className="py-2.5 pr-4 text-right font-mono text-gray-700">{fmt(row.fec_amount)}</td>
                  <td className={`py-2.5 pr-4 text-right font-mono ${row.delta && Math.abs(row.delta) > 1 ? "text-red-600 font-semibold" : "text-gray-500"}`}>
                    {row.delta !== null ? (row.delta >= 0 ? "+" : "") + fmt(row.delta) : "—"}
                  </td>
                  <td className="py-2.5 text-center">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="py-2.5 pl-2 text-gray-300">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filtered.length === 0 && (
            <p className="text-center text-sm text-gray-400 py-12">Aucun poste à afficher.</p>
          )}
        </div>
      </div>

      <CommentDrawer row={drawerRow} onClose={() => setDrawerRow(null)} />
    </>
  );
}
