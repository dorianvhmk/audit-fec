import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "/api";

export type RowStatus = "OK" | "écart" | "absent";

export interface ReconciliationRow {
  label: string;
  table_type: string;
  plaquette_amount: number | null;
  fec_amount: number | null;
  delta: number | null;
  status: RowStatus;
  matched_accounts: string[];
  pcg_prefixes_used: string[];
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
    pdf_errors: string[];
    fec_row_count: number;
    pdf_page_count: number;
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

    const fetch = async () => {
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

    fetch();
    intervalRef.current = setInterval(fetch, 3000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [analysisId]);

  return { data, loading, error };
}
