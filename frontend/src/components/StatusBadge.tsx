import type { RowStatus } from "../hooks/useAnalysis";

const STYLES: Record<RowStatus, string> = {
  OK: "bg-green-100 text-green-800 border-green-200",
  écart: "bg-yellow-100 text-yellow-800 border-yellow-200",
  absent: "bg-red-100 text-red-700 border-red-200",
};

export default function StatusBadge({ status }: { status: RowStatus }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border ${STYLES[status]}`}>
      {status}
    </span>
  );
}
