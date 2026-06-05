import type { RawFile } from "@/hooks/useKnowledge";

interface Props {
  file: RawFile;
  selected: boolean;
  onSelect: (file: RawFile) => void;
}

function extBadge(name: string): { label: string; cls: string } {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return { label: "PDF", cls: "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400" };
  if (ext === "md") return { label: "MD", cls: "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400" };
  if (ext === "docx") return { label: "DOCX", cls: "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400" };
  return { label: ext.toUpperCase() || "FILE", cls: "bg-[#f5f2eb] text-[#555] dark:bg-[#2d2d48] dark:text-[#94a3b8]" };
}

export default function RawFileCard({ file, selected, onSelect }: Props) {
  const badge = extBadge(file.name);
  const sizeKB = (file.size / 1024).toFixed(1);

  return (
    <button
      onClick={() => onSelect(file)}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-150 ${
        selected
          ? "border-[#6366f1] ring-1 ring-[#6366f1] bg-white dark:bg-[#1a1a2e]"
          : "border-[#e6e2da] dark:border-[#2d2d48] bg-white dark:bg-[#1e1e35] hover:border-[#bbb] dark:hover:border-[#4a4a75] hover:-translate-y-px"
      }`}
    >
      <span className={`text-xs px-2 py-0.5 rounded font-medium mb-2 inline-block ${badge.cls}`}>
        📄 {badge.label}
      </span>
      <div className="text-sm font-semibold text-[#1a1a1a] dark:text-[#e2e8f0] mb-2 leading-snug truncate">
        {file.name}
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-[#aaa] dark:text-[#475569]">
        <span
          className={`w-1.5 h-1.5 rounded-full inline-block ${
            file.compiled ? "bg-emerald-500" : "bg-amber-400"
          }`}
        />
        <span>{file.compiled ? "已编译" : "待编译"}</span>
        <span>·</span>
        <span>{sizeKB} KB</span>
      </div>
    </button>
  );
}
