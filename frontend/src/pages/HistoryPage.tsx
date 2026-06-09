import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { API } from "../hooks/useAnalysis";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AnalysisSummary {
  id: string;
  client_name: string;
  status: "pending" | "processing" | "done" | "error";
  created_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }) + " " + d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
};

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<AnalysisSummary["status"], string> = {
  done:       "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  pending:    "bg-amber-500/10   text-amber-400   border-amber-500/20",
  processing: "bg-amber-500/10   text-amber-400   border-amber-500/20",
  error:      "bg-red-500/10     text-red-400     border-red-500/20",
};

const STATUS_LABEL: Record<AnalysisSummary["status"], string> = {
  done:       "Terminé",
  pending:    "En attente",
  processing: "En cours",
  error:      "Erreur",
};

function StatusChip({ status }: { status: AnalysisSummary["status"] }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold
      border tracking-wide uppercase ${STATUS_STYLE[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function HistoryPage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    axios
      .get<AnalysisSummary[]>(`${API}/analyses`)
      .then((res) => setRows(res.data))
      .catch((e) =>
        setError(axios.isAxiosError(e) ? e.message : "Erreur de chargement")
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex flex-col">

      {/* ── Header ──────────────────────────────────────────────────────── */}
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
            <p className="text-sm font-semibold text-ink">Historique des analyses</p>
          </div>
        </div>

        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 px-4 py-2 text-xs tracking-wider uppercase
                     border border-edge rounded-sm text-ink-muted
                     hover:border-gold/60 hover:text-gold transition-colors"
        >
          + Nouvelle analyse
        </button>
      </header>

      {/* ── Body ────────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto px-6 py-6">

        {loading && (
          <div className="flex items-center justify-center py-24 gap-3 text-ink-faint">
            <svg className="animate-spin w-5 h-5 text-gold" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            <span className="text-xs tracking-widest uppercase">Chargement…</span>
          </div>
        )}

        {error && (
          <div className="rounded-sm bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400 max-w-lg">
            {error}
          </div>
        )}

        {!loading && !error && (
          <div className="bg-surface border border-edge rounded-sm overflow-hidden">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-edge bg-[#0F0F0F]">
                  {["Date", "Client", "Statut", "Actions"].map((h, i) => (
                    <th
                      key={h}
                      className={`px-5 py-3 text-[10px] tracking-widest uppercase text-ink-faint font-medium
                        ${i === 0 ? "text-left" : i === 3 ? "text-right" : "text-left"}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    className="border-b border-edge/50 hover:bg-surface-raised transition-colors"
                  >
                    <td className="px-5 py-3 font-mono text-xs text-ink-muted whitespace-nowrap">
                      {fmtDate(row.created_at)}
                    </td>
                    <td className="px-5 py-3 font-medium text-ink">
                      {row.client_name}
                    </td>
                    <td className="px-5 py-3">
                      <StatusChip status={row.status} />
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={() => navigate(`/results/${row.id}`)}
                        disabled={row.status !== "done"}
                        className="text-xs tracking-wider uppercase px-3 py-1.5 rounded-sm border
                                   border-gold/40 text-gold hover:bg-gold-dim
                                   disabled:opacity-30 disabled:cursor-not-allowed
                                   transition-colors"
                      >
                        Voir résultats
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {rows.length === 0 && (
              <div className="py-16 text-center">
                <p className="text-xs tracking-widest uppercase text-ink-faint">
                  Aucune analyse enregistrée
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
