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
      className={`flex flex-col items-center justify-center w-full h-36 border-2 border-dashed rounded-xl cursor-pointer transition-colors
        ${over ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-white hover:border-blue-400 hover:bg-gray-50"}`}
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
          <p className="text-sm font-medium text-blue-700 truncate max-w-xs">{file.name}</p>
          <p className="text-xs text-gray-400 mt-1">{(file.size / 1024).toFixed(0)} Ko</p>
        </div>
      ) : (
        <div className="text-center px-4">
          <svg className="mx-auto mb-2 w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
          <p className="text-sm font-medium text-gray-600">{label}</p>
          <p className="text-xs text-gray-400">Glisser-déposer ou cliquer</p>
        </div>
      )}
    </label>
  );
}
