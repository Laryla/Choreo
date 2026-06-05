import WikiCard from "./WikiCard";
import RawFileCard from "./RawFileCard";
import type { WikiPageMeta, RawFile } from "@/hooks/useKnowledge";

type SelectedItem = { kind: "wiki"; data: WikiPageMeta } | { kind: "raw"; data: RawFile };

interface Props {
  wikiPages: WikiPageMeta[];
  rawFiles: RawFile[];
  filter: "all" | "wiki" | "raw";
  query: string;
  selectedItem: SelectedItem | null;
  onSelectWiki: (page: WikiPageMeta) => void;
  onSelectRaw: (file: RawFile) => void;
}

export default function KnowledgeGrid({
  wikiPages,
  rawFiles,
  filter,
  query,
  selectedItem,
  onSelectWiki,
  onSelectRaw,
}: Props) {
  const q = query.toLowerCase();

  const filteredWiki = wikiPages.filter(
    (p) =>
      (filter === "all" || filter === "wiki") &&
      (!q || p.name.toLowerCase().includes(q) || p.summary?.toLowerCase().includes(q))
  );

  const filteredRaw = rawFiles.filter(
    (f) =>
      (filter === "all" || filter === "raw") &&
      (!q || f.name.toLowerCase().includes(q))
  );

  const isEmpty = filteredWiki.length === 0 && filteredRaw.length === 0;

  if (isEmpty) {
    return (
      <div className="flex-1 flex items-center justify-center h-full text-sm text-[#aaa] dark:text-[#475569]">
        {q ? `未找到与「${query}」相关的内容` : "暂无内容"}
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-0 h-full overflow-y-auto p-6">
      {filteredWiki.length > 0 && (
        <>
          <p className="text-xs font-semibold uppercase tracking-wide text-[#aaa] dark:text-[#475569] mb-3 pb-2 border-b border-[#e6e2da] dark:border-[#2d2d48]">
            Wiki 条目 · {filteredWiki.length} 篇
          </p>
          <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {filteredWiki.map((p) => (
              <WikiCard
                key={p.path}
                page={p}
                selected={selectedItem?.kind === "wiki" && selectedItem.data.path === p.path}
                onSelect={onSelectWiki}
              />
            ))}
          </div>
        </>
      )}
      {filteredRaw.length > 0 && (
        <>
          <p className="text-xs font-semibold uppercase tracking-wide text-[#aaa] dark:text-[#475569] mb-3 pb-2 border-b border-[#e6e2da] dark:border-[#2d2d48]">
            原始资料 · {filteredRaw.length} 份
          </p>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {filteredRaw.map((f) => (
              <RawFileCard
                key={f.name}
                file={f}
                selected={selectedItem?.kind === "raw" && selectedItem.data.name === f.name}
                onSelect={onSelectRaw}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
