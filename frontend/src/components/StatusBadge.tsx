import type { RowStatus } from "../hooks/useAnalysis";

const STYLES: Record<RowStatus, string> = {
  OK:     "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  écart:  "bg-amber-500/10   text-amber-400   border-amber-500/20",
  erreur: "bg-red-500/10     text-red-400     border-red-500/20",
  absent: "bg-white/5        text-ink-muted   border-white/10",
};

export default function StatusBadge({ status }: { status: RowStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold
        border tracking-wide uppercase ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
