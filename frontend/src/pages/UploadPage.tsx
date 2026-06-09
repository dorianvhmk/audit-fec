import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import DropZone from "../components/DropZone";
import { API } from "../hooks/useAnalysis";

export default function UploadPage() {
  const navigate = useNavigate();
  const [clientName, setClientName] = useState("");
  const [fecFile, setFecFile] = useState<File | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        {/* Title */}
        <div className="mb-8 text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-blue-600 mb-4">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Rapprochement FEC / Plaquette</h1>
          <p className="text-sm text-gray-500 mt-1">
            Déposez les fichiers pour lancer l'analyse automatique
          </p>
        </div>

        {/* Form card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-5">
          {/* Client name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nom du client
            </label>
            <input
              type="text"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm
                         focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Société XYZ"
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
            />
          </div>

          {/* FEC drop zone */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              FEC DGFiP <span className="text-gray-400 font-normal">(.txt)</span>
            </label>
            <DropZone
              label="Fichier FEC pipe-délimité"
              accept=".txt"
              file={fecFile}
              onFile={setFecFile}
            />
          </div>

          {/* PDF drop zone */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Plaquette financière <span className="text-gray-400 font-normal">(.pdf)</span>
            </label>
            <DropZone
              label="Plaquette PDF annuelle"
              accept=".pdf"
              file={pdfFile}
              onFile={setPdfFile}
            />
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="w-full py-2.5 rounded-lg text-sm font-semibold text-white bg-blue-600
                       hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed
                       transition-colors flex items-center justify-center gap-2"
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
      </div>
    </div>
  );
}
