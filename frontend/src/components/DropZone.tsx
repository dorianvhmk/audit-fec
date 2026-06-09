import React, { useCallback, useState } from "react";

interface Props {
  label: string;
  accept: string;
  file: File | null;
  onFile: (f: File) => void;
}

export default function DropZone({ label, accept, file, onFile }: Props) {
  const [over, setOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setOver(false);
      const f = e.dataTransfer.files[0];
      if (f) onFile(f);
    },
    [onFile]
  );

  return (
    <label
      className={`flex flex-col items-center justify-center w-full h-32 border border-dashed
        rounded cursor-pointer transition-all duration-150
        ${over
          ? "border-gold bg-gold-dim text-gold"
          : file
          ? "border-gold/40 bg-gold-dim/50 text-gold"
          : "border-edge bg-surface text-ink-muted hover:border-gold/60 hover:text-gold/80"
        }`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={handleDrop}
    >
      <input
        type="file"
        className="sr-only"
        accept={accept}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }}
      />

      {file ? (
        <div className="text-center px-4">
          {/* checkmark */}
          <svg className="mx-auto mb-1.5 w-5 h-5 text-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <p className="text-sm font-medium text-gold truncate max-w-xs">{file.name}</p>
          <p className="text-xs text-ink-faint mt-0.5">{(file.size / 1024).toFixed(0)} Ko</p>
        </div>
      ) : (
        <div className="text-center px-4">
          <svg className="mx-auto mb-1.5 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 7.5m0 0L7.5 12M12 7.5v9" />
          </svg>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-ink-faint mt-0.5">Glisser-déposer ou cliquer</p>
        </div>
      )}
    </label>
  );
}
