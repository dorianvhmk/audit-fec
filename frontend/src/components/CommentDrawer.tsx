import type { ReconciliationRow } from "../hooks/useAnalysis";
import StatusBadge from "./StatusBadge";

interface Props {
  row: ReconciliationRow | null;
  onClose: () => void;
}

const fmtEur = (v: number | null) =>
  v === null ? "—" : v.toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + " €";

const fmtPct = (v: number | null) =>
  v === null ? "—" : v.toLocaleString("fr-FR", { maximumFractionDigits: 1 }) + " %";

export default function CommentDrawer({ row, onClose }: Props) {
  if (!row) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />

      {/* Slide-in panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-md bg-white shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900 text-sm truncate pr-4">{row.label}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 flex-shrink-0">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* KPI grid */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Montant plaquette</p>
              <p className="font-medium text-gray-800">{fmtEur(row.plaquette_amount)}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Montant FEC</p>
              <p className="font-medium text-gray-800">{fmtEur(row.fec_amount)}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Écart (€)</p>
              <p className={`font-medium ${row.delta_abs && Math.abs(row.delta_abs) > 0 ? "text-red-600" : "text-gray-800"}`}>
                {row.delta_abs !== null
                  ? (row.delta_abs >= 0 ? "+" : "") + fmtEur(row.delta_abs)
                  : "—"}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-1">Écart (%)</p>
              <p className={`font-medium ${row.delta_pct !== null && row.delta_pct >= 1 ? "text-red-600" : "text-gray-800"}`}>
                {fmtPct(row.delta_pct)}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 col-span-1">
              <p className="text-xs text-gray-500 mb-1">Section</p>
              <p className="font-medium text-gray-800 text-xs">{row.section}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 col-span-1">
              <p className="text-xs text-gray-500 mb-2">Statut</p>
              <StatusBadge status={row.status} />
            </div>
          </div>

          {/* Matched accounts */}
          {row.matched_accounts.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Comptes FEC imputés
              </p>
              <div className="flex flex-wrap gap-1">
                {row.matched_accounts.map((a) => (
                  <span
                    key={a}
                    className="text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5 font-mono"
                  >
                    {a}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Claude commentary */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Commentaire d'audit IA
            </p>
            {row.commentary ? (
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                {row.commentary}
              </p>
            ) : (
              <p className="text-sm text-gray-400 italic">
                Aucun commentaire (poste sans anomalie ou analyse non disponible).
              </p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
