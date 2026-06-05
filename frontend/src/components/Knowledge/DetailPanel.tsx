import ReactMarkdown from "react-markdown";
import { useWikiPage } from "@/hooks/useKnowledge";
import type { WikiPageMeta, RawFile } from "@/hooks/useKnowledge";

type SelectedItem = { kind: "wiki"; data: WikiPageMeta } | { kind: "raw"; data: RawFile };

interface Props {
  item: SelectedItem | null;
  onClose: () => void;
}

function extractSources(content: string): string[] {
  const matches = [...content.matchAll(/\[\[([^\]]+)\]\]/g)];
  return [...new Set(matches.map((m) => m[1].trim()))];
}

function WikiDetail({ page, onClose }: { page: WikiPageMeta; onClose: () => void }) {
  const { data } = useWikiPage(page.path);
  const sources = data ? extractSources(data.content) : [];

  return (
    <>
      <div className="flex items-start justify-between gap-3 p-4 border-b border-[#e6e2da] dark:border-[#2d2d48]">
        <h2 className="text-base font-bold text-[#1a1a1a] dark:text-[#e2e8f0] leading-snug">{page.name}</h2>
        <button
          onClick={onClose}
          className="w-6 h-6 flex-shrink-0 flex items-center justify-center rounded text-[#aaa] hover:text-[#555] dark:hover:text-[#e2e8f0] bg-[#f5f2eb] dark:bg-[#22223a] border border-[#e6e2da] dark:border-[#3a3a55] text-xs"
        >
          ✕
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {data ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown>{data.content}</ReactMarkdown>
          </div>
        ) : (
          <div className="text-sm text-[#aaa] dark:text-[#475569]">加载中…</div>
        )}
      </div>
      {sources.length > 0 && (
        <div className="p-4 border-t border-[#e6e2da] dark:border-[#2d2d48]">
          <p className="text-[10px] uppercase tracking-wide text-[#aaa] dark:text-[#475569] font-semibold mb-2">
            引用来源
          </p>
          <div className="flex flex-col gap-1">
            {sources.map((src) => (
              <div
                key={src}
                className="text-xs px-2 py-1.5 rounded-md bg-[#f5f2eb] dark:bg-[#1e1e35] border border-[#e6e2da] dark:border-[#2d2d48] text-[#666] dark:text-[#94a3b8]"
              >
                🔗 {src}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function RawDetail({ file, onClose }: { file: RawFile; onClose: () => void }) {
  const sizeKB = (file.size / 1024).toFixed(1);
  return (
    <>
      <div className="flex items-start justify-between gap-3 p-4 border-b border-[#e6e2da] dark:border-[#2d2d48]">
        <h2 className="text-base font-bold text-[#1a1a1a] dark:text-[#e2e8f0] leading-snug break-all">{file.name}</h2>
        <button
          onClick={onClose}
          className="w-6 h-6 flex-shrink-0 flex items-center justify-center rounded text-[#aaa] hover:text-[#555] dark:hover:text-[#e2e8f0] bg-[#f5f2eb] dark:bg-[#22223a] border border-[#e6e2da] dark:border-[#3a3a55] text-xs"
        >
          ✕
        </button>
      </div>
      <div className="p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-sm text-[#555] dark:text-[#94a3b8]">
          <span
            className={`w-2 h-2 rounded-full ${file.compiled ? "bg-emerald-500" : "bg-amber-400"}`}
          />
          <span>{file.compiled ? "已编译入知识图谱" : "尚未编译"}</span>
        </div>
        <div className="text-sm text-[#888] dark:text-[#64748b]">大小：{sizeKB} KB</div>
        {!file.compiled && (
          <p className="text-xs text-[#aaa] dark:text-[#475569]">
            点击「触发编译」将此文件编译进知识库。
          </p>
        )}
      </div>
    </>
  );
}

export default function DetailPanel({ item, onClose }: Props) {
  const visible = item !== null;

  return (
    <div
      className={`flex flex-col flex-shrink-0 bg-white dark:bg-[#16162a] border-l border-[#e6e2da] dark:border-[#2d2d48] overflow-hidden transition-all duration-200 ${
        visible ? "w-96 translate-x-0" : "w-0 translate-x-full"
      }`}
    >
      {item?.kind === "wiki" && <WikiDetail page={item.data} onClose={onClose} />}
      {item?.kind === "raw" && <RawDetail file={item.data} onClose={onClose} />}
    </div>
  );
}
