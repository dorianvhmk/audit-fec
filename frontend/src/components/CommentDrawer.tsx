import type { ReconciliationRow } from "../hooks/useAnalysis";
import StatusBadge from "./StatusBadge";

interface Props {
  row: ReconciliationRow | null;
  onClose: () => void;
}

const fmtEur = (v: number | null) =>
  v === null
    ? "—"
    : v.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + " €";

const fmtPct = (v: number | null) =>
  v === null ? "—" : v.toLocaleString("fr-FR", { maximumFractionDigits: 1 }) + " %";

function KpiTile({ label, value, highlight = false }: { label: string; value: React.ReactNode; highlight?: boolean }) {
  return (
    <div className="bg-[#0A0A0A] border border-edge rounded p-3">
      <p className="text-[10px] tracking-widest uppercase text-ink-faint mb-1.5">{label}</p>
      <p className={`text-sm font-medium tabular-nums ${highlight ? "text-red-400" : "text-ink"}`}>{value}</p>
    </div>
  );
}

import React from "react";

export default function CommentDrawer({ row, onClose }: Props) {
  if (!row) return null;

  const isNegative = row.delta_abs !== null && row.delta_abs < 0;
  const deltaStr = row.delta_abs !== null
    ? (isNegative ? "−" : "+") + fmtEur(Math.abs(row.delta_abs))
    : "—";

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-full max-w-[440px] bg-surface border-l border-edge z-50 flex flex-col">

        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-edge">
          <div className="pr-4">
            <p className="text-[10px] tracking-widest uppercase text-ink-faint mb-1">Poste analysé</p>
            <h2 className="font-semibold text-ink text-sm leading-snug">{row.label}</h2>
          </div>
          <button
            onClick={onClose}
            className="mt-0.5 text-ink-faint hover:text-gold transition-colors flex-shrink-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">

          {/* KPI grid */}
          <div className="grid grid-cols-2 gap-2">
            <KpiTile label="Montant plaquette" value={fmtEur(row.plaquette_amount)} />
            <KpiTile label="Montant FEC"       value={fmtEur(row.fec_amount)} />
            <KpiTile
              label="Écart (€)"
              value={deltaStr}
              highlight={row.delta_abs !== null && Math.abs(row.delta_abs) > 0}
            />
            <KpiTile
              label="Écart (%)"
              value={fmtPct(row.delta_pct)}
              highlight={row.delta_pct !== null && row.delta_pct >= 1}
            />
            <div className="bg-[#0A0A0A] border border-edge rounded p-3">
              <p className="text-[10px] tracking-widest uppercase text-ink-faint mb-1.5">Statut</p>
              <StatusBadge status={row.status} />
            </div>
            <div className="bg-[#0A0A0A] border border-edge rounded p-3">
              <p className="text-[10px] tracking-widest uppercase text-ink-faint mb-1.5">Section</p>
              <p className="text-xs text-ink-muted leading-snug">{row.section}</p>
            </div>
          </div>

          {/* Matched accounts */}
          {row.matched_accounts.length > 0 && (
            <div>
              <p className="text-[10px] tracking-widest uppercase text-ink-faint mb-2">
                Comptes FEC imputés
              </p>
              <div className="flex flex-wrap gap-1.5">
                {row.matched_accounts.map((a) => (
                  <span
                    key={a}
                    className="text-xs font-mono bg-gold-dim text-gold border border-gold/20 rounded px-1.5 py-0.5"
                  >
                    {a}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Divider */}
          <div className="border-t border-edge" />

          {/* Claude commentary */}
          <div>
            <p className="text-[10px] tracking-widest uppercase text-gold mb-3">
              Commentaire d'audit IA
            </p>
            {row.commentary ? (
              <p className="text-sm text-ink-muted leading-relaxed">
                {row.commentary}
              </p>
            ) : (
              <p className="text-sm text-ink-faint italic">
                Aucun commentaire disponible pour ce poste.
              </p>
            )}
          </div>

        </div>
      </div>
    </>
  );
}
