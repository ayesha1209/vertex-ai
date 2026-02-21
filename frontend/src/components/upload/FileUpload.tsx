import { useCallback } from "react";
import { useDropzone } from "react-dropzone";

interface Props {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

export function FileUpload({ onFileSelected, disabled }: Props) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles[0]) onFileSelected(acceptedFiles[0]);
    },
    [onFileSelected]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    disabled,
    multiple: false,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "text/csv": [".csv"],
    },
  });

  return (
    <div
      {...getRootProps()}
      className={`
        flex min-h-[260px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-8 py-12 text-center transition-all duration-200
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2
        sm:min-h-[280px]
        ${isDragActive ? "border-teal-400 bg-teal-50/90 scale-[1.01]" : "border-slate-300 bg-slate-50/60 hover:border-slate-400 hover:bg-slate-100/80"}
        ${disabled ? "cursor-not-allowed opacity-60 scale-100" : ""}
      `}
    >
      <input {...getInputProps()} aria-label="Choose Excel or CSV file" />
      <div
        className={`mb-4 flex h-16 w-16 items-center justify-center rounded-2xl transition-colors duration-200 sm:h-20 sm:w-20 ${isDragActive ? "bg-teal-100 text-teal-600" : "bg-slate-200/80 text-slate-500"}`}
        aria-hidden
      >
        <svg className="h-9 w-9 sm:h-11 sm:w-11" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.25}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
      </div>
      <p className="text-base font-medium text-slate-700 sm:text-lg">{isDragActive ? "Drop file here" : "Drag and drop your file here"}</p>
      <p className="mt-1 text-sm text-slate-500">or click to browse</p>
      <ul className="mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-slate-500" role="list">
        <li className="flex items-center gap-1.5">
          <span className="rounded bg-slate-200/80 px-1.5 py-0.5 font-medium text-slate-600">.xlsx</span>
          <span>or</span>
          <span className="rounded bg-slate-200/80 px-1.5 py-0.5 font-medium text-slate-600">.csv</span>
        </li>
        <li>Required: <strong className="text-slate-600">Buyer Name</strong>, <strong className="text-slate-600">Product Name</strong></li>
      </ul>
    </div>
  );
}
