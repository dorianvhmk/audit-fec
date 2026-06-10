import { useState, useEffect } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import axios from "axios";
import DropZone from "../components/DropZone";
import { API } from "../hooks/useAnalysis";

export default function UploadPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [clientName, setClientName] = useState("");
  const [fecFile, setFecFile] = useState<File | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(
    (location.state as { toast?: string } | null)?.toast ?? null
  );

  // Auto-dismiss toast after 4 s
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const canSubmit = clientName.trim() && fecFile && pdfFile && !loading;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setError(null);
    setLoading(true);
    try {
      const form = new FormData();
      form.append("client_name", clientName.trim());
      form.append("fec_file", fecFile!);
      form.append("pdf_file", pdfFile!);

      const { data } = await axios.post<{ analysis_id: string }>(`${API}/upload`, form);
      await axios.post(`${API}/analyze/${data.analysis_id}`);
      navigate(`/results/${data.analysis_id}`);
    } catch (e: unknown) {
      const msg = axios.isAxiosError(e)
        ? (e.response?.data?.detail ?? e.message)
        : "Erreur inconnue";
      setError(String(msg));
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">

        {/* Logo / wordmark */}
        <div className="mb-10 text-center relative">
          <Link
            to="/history"
            className="absolute right-0 top-0 text-[10px] tracking-widest uppercase
                       text-ink-faint hover:text-gold transition-colors"
          >
            Historique →
          </Link>
          <p className="text-xs tracking-[0.35em] uppercase text-ink-faint mb-3">
            Cabinet d'audit
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-gold">
            AUDIT FEC
          </h1>
          <p className="text-sm text-ink-faint mt-2">
            Rapprochement FEC / Plaquette financière
          </p>
        </div>

        {/* Toast */}
        {toast && (
          <div className="mb-4 flex items-center gap-3 rounded-sm border border-amber-500/30
                          bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20A10 10 0 0012 2z" />
            </svg>
            {toast}
          </div>
        )}

        {/* Card */}
        <div className="bg-surface border border-edge rounded-sm p-6 space-y-5">

          {/* Client name */}
          <div>
            <label className="block text-[10px] tracking-widest uppercase text-ink-faint mb-2">
              Nom du client
            </label>
            <input
              type="text"
              className="w-full bg-[#0A0A0A] border border-edge rounded-sm px-3 py-2.5 text-sm
                         text-ink placeholder-ink-faint
                         focus:outline-none focus:border-gold focus:ring-0
                         transition-colors"
              placeholder="Société XYZ"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
          </div>

          {/* Divider */}
          <div className="border-t border-edge" />

          {/* FEC */}
          <div>
            <label className="block text-[10px] tracking-widest uppercase text-ink-faint mb-2">
              FEC DGFiP <span className="normal-case text-ink-faint/60">(.xlsx ou .txt)</span>
            </label>
            <DropZone label="Fichier FEC Excel ou pipe-délimité" accept=".xlsx,.txt" file={fecFile} onFile={setFecFile} />
          </div>

          {/* PDF */}
          <div>
            <label className="block text-[10px] tracking-widest uppercase text-ink-faint mb-2">
              Plaquette financière <span className="normal-case text-ink-faint/60">(.pdf)</span>
            </label>
            <DropZone label="Rapport annuel PDF" accept=".pdf" file={pdfFile} onFile={setPdfFile} />
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-sm bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {/* CTA */}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="w-full py-3 rounded-sm text-sm font-semibold tracking-wider uppercase
                       bg-gold text-black hover:bg-gold-light
                       disabled:opacity-30 disabled:cursor-not-allowed
                       transition-colors duration-150 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Envoi en cours…
              </>
            ) : (
              "Analyser"
            )}
          </button>
        </div>

        {/* Footer hint */}
        <p className="text-center text-[11px] text-ink-faint mt-6">
          Données traitées de façon confidentielle · Powered by Claude AI
        </p>
      </div>
    </div>
  );
}
