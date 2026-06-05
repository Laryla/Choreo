import type { WikiPageMeta } from "@/hooks/useKnowledge";

interface Props {
  page: WikiPageMeta;
  selected: boolean;
  onSelect: (page: WikiPageMeta) => void;
}

const TYPE_LABELS: Record<WikiPageMeta["type"], string> = {
  concept: "概念",
  entity: "实体",
  "source-summary": "来源摘要",
  comparison: "对比",
};

const TYPE_BADGE: Record<WikiPageMeta["type"], string> = {
  concept: "bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400",
  entity: "bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400",
  "source-summary": "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400",
  comparison: "bg-pink-50 text-pink-600 dark:bg-pink-900/20 dark:text-pink-400",
};

function relativeTime(ts: number): string {
  const diff = Math.floor((Date.now() / 1000 - ts) / 86400);
  if (diff === 0) return "今天";
  if (diff === 1) return "昨天";
  if (diff < 7) return `${diff} 天前`;
  if (diff < 30) return `${Math.floor(diff / 7)} 周前`;
  return `${Math.floor(diff / 30)} 个月前`;
}

export default function WikiCard({ page, selected, onSelect }: Props) {
  return (
    <button
      onClick={() => onSelect(page)}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-150 ${
        selected
          ? "border-[#6366f1] ring-1 ring-[#6366f1] bg-white dark:bg-[#1a1a2e]"
          : "border-[#e6e2da] dark:border-[#2d2d48] bg-white dark:bg-[#1e1e35] hover:border-[#bbb] dark:hover:border-[#4a4a75] hover:-translate-y-px"
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs px-2 py-0.5 rounded bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400 font-medium">
          📖 Wiki
        </span>
        <span className={`text-xs px-2 py-0.5 rounded font-medium ${TYPE_BADGE[page.type]}`}>
          {TYPE_LABELS[page.type]}
        </span>
      </div>
      <div className="text-sm font-semibold text-[#1a1a1a] dark:text-[#e2e8f0] mb-1.5 leading-snug">
        {page.name}
      </div>
      {page.summary && (
        <div className="text-xs text-[#888] dark:text-[#64748b] leading-relaxed line-clamp-2 mb-2.5">
          {page.summary}
        </div>
      )}
      <div className="flex items-center gap-1.5 text-[10px] text-[#aaa] dark:text-[#475569]">
        {page.ref_count > 0 && (
          <>
            <span>🔗 {page.ref_count} 个来源</span>
            <span>·</span>
          </>
        )}
        <span>{relativeTime(page.modified_at)}</span>
      </div>
    </button>
  );
}
