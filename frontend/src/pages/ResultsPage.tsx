import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAnalysis, ReconciliationRow, RowStatus, API } from "../hooks/useAnalysis";
import StatusBadge from "../components/StatusBadge";
import CommentDrawer from "../components/CommentDrawer";

// ── Formatters ────────────────────────────────────────────────────────────────

const fmtEur = (v: number | null) =>
  v === null
    ? "—"
    : v.toLocaleString("fr-FR", { maximumFractionDigits: 0 });

const fmtPct = (pct: number | null, abs: number | null) => {
  if (pct === null) return "—";
  const sign = abs !== null && abs < 0 ? "−" : "+";
  return `${sign}${pct.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`;
};

const truncate = (s: string, n = 55) => (s.length > n ? s.slice(0, n) + "…" : s);

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_ORDER: RowStatus[] = ["erreur", "écart", "absent", "OK"];

const CARD_NUM_COLOR: Record<RowStatus, string> = {
  erreur: "text-red-400",
  écart:  "text-amber-400",
  absent: "text-ink-muted",
  OK:     "text-emerald-400",
};

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="min-h-screen bg-[#0A0A0A] flex flex-col items-center justify-center gap-4">
      <svg className="animate-spin w-7 h-7 text-gold" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
      <p className="text-xs tracking-widest uppercase text-ink-faint">Chargement…</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data } = useAnalysis(id);
  const [drawerRow, setDrawerRow] = useState<ReconciliationRow | null>(null);
  const [filterStatus, setFilterStatus] = useState<RowStatus | "all">("all");

  if (!data) return <Spinner />;

  // ── Processing ──────────────────────────────────────────────────────────────
  if (data.status === "pending" || data.status === "processing") {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex flex-col items-center justify-center gap-4">
        <svg className="animate-spin w-7 h-7 text-gold" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        <div className="text-center">
          <p className="text-sm font-medium text-ink">Analyse en cours…</p>
          <p className="text-xs text-ink-faint mt-1 tracking-wide">
            Extraction FEC · PDF · Commentaires IA
          </p>
        </div>
      </div>
    );
  }

  // ── Error ───────────────────────────────────────────────────────────────────
  if (data.status === "error") {
    return (
      <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center p-6">
        <div className="max-w-sm text-center space-y-3">
          <p className="text-xs tracking-widest uppercase text-red-400 mb-2">Erreur d'analyse</p>
          <p className="text-sm text-ink-muted">{data.results?.error ?? "Erreur inconnue"}</p>
          <button
            onClick={() => navigate("/")}
            className="mt-4 text-xs tracking-wider uppercase text-gold hover:text-gold-light transition-colors"
          >
            ← Nouvelle analyse
          </button>
        </div>
      </div>
    );
  }

  // ── Done ────────────────────────────────────────────────────────────────────
  const rows = data.results?.rows ?? [];
  const filtered =
    filterStatus === "all" ? rows : rows.filter((r) => r.status === filterStatus);

  const counts = Object.fromEntries(
    STATUS_ORDER.map((s) => [s, rows.filter((r) => r.status === s).length])
  ) as Record<RowStatus, number>;

  const handleExport = () => window.open(`${API}/export/${id}`, "_blank");

  return (
    <>
      <div className="min-h-screen bg-[#0A0A0A] flex flex-col">

        {/* ── Top bar ────────────────────────────────────────────────────── */}
        <header className="bg-surface border-b border-edge px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-5">
            <button
              onClick={() => navigate("/")}
              className="text-ink-faint hover:text-gold transition-colors"
              title="Nouvelle analyse"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div className="h-4 w-px bg-edge" />
            <div>
              <p className="text-[10px] tracking-widest uppercase text-gold">Audit FEC</p>
              <p className="text-sm font-semibold text-ink">{data.client_name}</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <p className="text-xs text-ink-faint hidden sm:block">
              {data.results?.fec_row_count?.toLocaleString("fr-FR")} écritures
            </p>
            <button
              onClick={handleExport}
              className="flex items-center gap-2 px-4 py-2 text-xs tracking-wider uppercase
                         border border-edge rounded-sm text-ink-muted
                         hover:border-gold/60 hover:text-gold transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z" />
              </svg>
              Excel
            </button>
          </div>
        </header>

        {/* ── Summary strip ──────────────────────────────────────────────── */}
        <div className="px-6 py-4 flex flex-wrap gap-2 items-center border-b border-edge">
          {STATUS_ORDER.map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(filterStatus === s ? "all" : s)}
              className={`flex items-center gap-3 px-4 py-2.5 border rounded-sm transition-all
                ${filterStatus === s
                  ? "border-gold/40 bg-gold-dim"
                  : "border-edge bg-surface hover:border-edge/80"}`}
            >
              <span className={`text-xl font-semibold tabular-nums ${CARD_NUM_COLOR[s]}`}>
                {counts[s]}
              </span>
              <span className="text-[10px] tracking-widest uppercase text-ink-faint">{s}</span>
            </button>
          ))}

          {filterStatus !== "all" && (
            <button
              onClick={() => setFilterStatus("all")}
              className="ml-1 text-[10px] tracking-wider uppercase text-gold hover:text-gold-light transition-colors"
            >
              Tout afficher
            </button>
          )}

          <span className="ml-auto text-xs text-ink-faint">
            {filtered.length} poste{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* ── Table ──────────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-edge bg-surface">
                {[
                  ["Poste",       "text-left   px-6 py-3"],
                  ["FEC",         "text-right  px-4 py-3"],
                  ["Plaquette",   "text-right  px-4 py-3"],
                  ["Δ %",         "text-right  px-4 py-3"],
                  ["Statut",      "text-center px-4 py-3"],
                  ["Commentaire", "text-left   px-4 py-3"],
                  ["",            "w-6 px-3"],
                ].map(([label, cls]) => (
                  <th
                    key={label}
                    className={`${cls} text-[10px] tracking-widest uppercase text-ink-faint font-medium`}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, i) => (
                <tr
                  key={i}
                  onClick={() => setDrawerRow(row)}
                  className="border-b border-edge/50 hover:bg-surface cursor-pointer transition-colors group"
                >
                  <td className="px-6 py-3 font-medium text-ink text-sm max-w-[220px] truncate">
                    {row.label}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-ink-muted tabular-nums whitespace-nowrap">
                    {fmtEur(row.fec_amount)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-ink-muted tabular-nums whitespace-nowrap">
                    {fmtEur(row.plaquette_amount)}
                  </td>
                  <td className={`px-4 py-3 text-right font-mono text-xs tabular-nums whitespace-nowrap
                    ${row.delta_pct !== null && row.delta_pct >= 5
                      ? "text-red-400 font-semibold"
                      : row.delta_pct !== null && row.delta_pct >= 1
                      ? "text-amber-400"
                      : "text-ink-faint"}`}
                  >
                    {fmtPct(row.delta_pct, row.delta_abs)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <StatusBadge status={row.status} />
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-faint max-w-[240px] truncate">
                    {row.commentary ? truncate(row.commentary) : <span className="italic">—</span>}
                  </td>
                  <td className="px-3 py-3 text-ink-faint group-hover:text-gold transition-colors">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {filtered.length === 0 && (
            <div className="py-20 text-center">
              <p className="text-xs tracking-widest uppercase text-ink-faint">
                Aucun poste à afficher
              </p>
            </div>
          )}
        </div>
      </div>

      <CommentDrawer row={drawerRow} onClose={() => setDrawerRow(null)} />
    </>
  );
}
