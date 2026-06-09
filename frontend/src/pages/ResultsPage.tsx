import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAnalysis, ReconciliationRow, RowStatus, API } from "../hooks/useAnalysis";
import StatusBadge from "../components/StatusBadge";
import CommentDrawer from "../components/CommentDrawer";

// ── Formatters ────────────────────────────────────────────────────────────────

const fmtEur = (v: number | null) =>
  v === null
    ? "—"
    : v.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + " €";

const fmtPct = (pct: number | null, abs: number | null) => {
  if (pct === null) return "—";
  const sign = abs !== null && abs < 0 ? "−" : "+";
  return `${sign}${pct.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`;
};

const truncate = (s: string, n = 60) =>
  s.length > n ? s.slice(0, n) + "…" : s;

// ── Badge config for summary cards ───────────────────────────────────────────

const STATUS_ORDER: RowStatus[] = ["erreur", "écart", "absent", "OK"];

const CARD_STYLES: Record<RowStatus, string> = {
  erreur: "border-red-200    bg-red-50    ring-red-400    text-red-700",
  écart:  "border-orange-200 bg-orange-50 ring-orange-400 text-orange-700",
  absent: "border-gray-200   bg-gray-50   ring-gray-400   text-gray-600",
  OK:     "border-green-200  bg-green-50  ring-green-400  text-green-700",
};

// ── Spinner ──────────────────────────────────────────────────────────────────

function Spinner({ label }: { label: string }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 text-gray-500">
      <svg className="animate-spin w-9 h-9 text-blue-500" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
      <p className="font-medium text-sm">{label}</p>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data } = useAnalysis(id);
  const [drawerRow, setDrawerRow] = useState<ReconciliationRow | null>(null);
  const [filterStatus, setFilterStatus] = useState<RowStatus | "all">("all");

  // ── Loading ────────────────────────────────────────────────────────────────
  if (!data) return <Spinner label="Chargement…" />;

  // ── Processing ────────────────────────────────────────────────────────────
  if (data.status === "pending" || data.status === "processing") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-gray-600">
        <svg className="animate-spin w-10 h-10 text-blue-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        <p className="font-semibold">Analyse en cours…</p>
        <p className="text-sm text-gray-400">Extraction FEC · PDF · Commentaires IA</p>
      </div>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (data.status === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="max-w-md text-center space-y-3">
          <p className="text-red-600 font-semibold">Erreur lors de l'analyse</p>
          <p className="text-sm text-gray-500">{data.results?.error ?? "Erreur inconnue"}</p>
          <button
            onClick={() => navigate("/")}
            className="text-sm text-blue-600 hover:underline"
          >
            ← Nouvelle analyse
          </button>
        </div>
      </div>
    );
  }

  // ── Done ──────────────────────────────────────────────────────────────────
  const rows = data.results?.rows ?? [];
  const filtered =
    filterStatus === "all" ? rows : rows.filter((r) => r.status === filterStatus);

  const counts = Object.fromEntries(
    STATUS_ORDER.map((s) => [s, rows.filter((r) => r.status === s).length])
  ) as Record<RowStatus, number>;

  const handleExport = () => {
    window.open(`${API}/export/${id}`, "_blank");
  };

  return (
    <>
      <div className="min-h-screen bg-gray-50 flex flex-col">
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div>
            <button
              onClick={() => navigate("/")}
              className="text-xs text-gray-400 hover:text-gray-600 mb-1 flex items-center gap-1"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Nouvelle analyse
            </button>
            <h1 className="font-semibold text-gray-900">{data.client_name}</h1>
            <p className="text-xs text-gray-400 mt-0.5">
              {data.results?.fec_row_count?.toLocaleString("fr-FR")} écritures FEC
            </p>
          </div>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300
                       text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z" />
            </svg>
            Exporter Excel
          </button>
        </header>

        {/* ── Summary cards ───────────────────────────────────────────────── */}
        <div className="px-6 py-4 flex flex-wrap gap-3 items-center">
          {STATUS_ORDER.map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(filterStatus === s ? "all" : s)}
              className={`rounded-xl border px-4 py-3 text-left transition-all min-w-[100px]
                ${CARD_STYLES[s]}
                ${filterStatus === s ? "ring-2 ring-offset-1" : "hover:opacity-90"}`}
            >
              <p className="text-2xl font-bold text-gray-900">{counts[s]}</p>
              <p className="text-xs capitalize mt-0.5">{s}</p>
            </button>
          ))}
          {filterStatus !== "all" && (
            <button
              onClick={() => setFilterStatus("all")}
              className="text-xs text-blue-600 hover:underline ml-1"
            >
              Tout afficher
            </button>
          )}
        </div>

        {/* ── Table ───────────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-auto px-6 pb-10">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide w-64">
                    Poste
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    FEC
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Plaquette
                  </th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Δ %
                  </th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Statut
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Commentaire
                  </th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((row, i) => (
                  <tr
                    key={i}
                    onClick={() => setDrawerRow(row)}
                    className="border-b border-gray-100 hover:bg-blue-50/40 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-medium text-gray-800 truncate max-w-xs">
                      {row.label}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700 whitespace-nowrap">
                      {fmtEur(row.fec_amount)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-gray-700 whitespace-nowrap">
                      {fmtEur(row.plaquette_amount)}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono whitespace-nowrap
                        ${row.delta_pct !== null && row.delta_pct >= 5
                          ? "text-red-600 font-semibold"
                          : row.delta_pct !== null && row.delta_pct >= 1
                          ? "text-orange-600 font-medium"
                          : "text-gray-500"}`}
                    >
                      {fmtPct(row.delta_pct, row.delta_abs)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <StatusBadge status={row.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs max-w-[260px] truncate">
                      {row.commentary ? truncate(row.commentary) : <em>—</em>}
                    </td>
                    <td className="px-3 py-3 text-gray-300">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filtered.length === 0 && (
              <p className="text-center text-sm text-gray-400 py-14">
                Aucun poste à afficher.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── Drawer ──────────────────────────────────────────────────────────── */}
      <CommentDrawer row={drawerRow} onClose={() => setDrawerRow(null)} />
    </>
  );
}
