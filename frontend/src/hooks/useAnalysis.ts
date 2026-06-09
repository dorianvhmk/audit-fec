import { useState, useEffect, useRef } from "react";
import axios from "axios";

// In production VITE_API_URL = "https://xxx.up.railway.app"
// In local dev it is undefined and Vite proxies /api → localhost:8000
export const API = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

export type RowStatus = "OK" | "écart" | "erreur" | "absent";

export interface ReconciliationRow {
  label: string;
  section: string;
  plaquette_amount: number | null;
  exercice_n1: number | null;
  fec_amount: number | null;
  matched_accounts: string[];
  pcg_prefixes_used: string[];
  delta_abs: number | null;
  delta_pct: number | null;
  status: RowStatus;
  commentary: string;
}

export interface AnalysisRecord {
  id: string;
  client_name: string;
  status: "pending" | "processing" | "done" | "error";
  created_at: string;
  results?: {
    rows: ReconciliationRow[];
    fec_errors: string[];
    fec_row_count: number;
    pdf_sections: Record<string, number | null>;
    error?: string;
  };
}

export function useAnalysis(analysisId: string | undefined) {
  const [data, setData] = useState<AnalysisRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!analysisId) return;

    const poll = async () => {
      try {
        setLoading(true);
        const res = await axios.get<AnalysisRecord>(`${API}/results/${analysisId}`);
        setData(res.data);
        if (res.data.status === "done" || res.data.status === "error") {
          if (intervalRef.current) clearInterval(intervalRef.current);
          setLoading(false);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Erreur inconnue");
        if (intervalRef.current) clearInterval(intervalRef.current);
        setLoading(false);
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [analysisId]);

  return { data, loading, error };
}
