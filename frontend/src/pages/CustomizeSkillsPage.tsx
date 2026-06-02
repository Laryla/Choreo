// frontend/src/pages/CustomizeSkillsPage.tsx
import { useState, useRef, useEffect } from "react";
import useSWR from "swr";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SkillCard from "@/components/Skills/SkillCard";
import SkillEditor from "@/components/Skills/SkillEditor";
import SkillImportModal from "@/components/Skills/SkillImportModal";
import type { Skill, SkillPatch, ReviewLogEntry } from "@/api/skills";
import { patchSkill, deleteSkill, readSkillFile, getReviewLog } from "@/api/skills";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

const SOURCE_LABEL: Record<string, string> = {
  builtin: "Choreo 内置",
  auto: "自动生成",
  manual: "用户",
};

function getFileExt(filename: string) {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

function FilePreview({ filename, content }: { filename: string; content: string }) {
  const ext = getFileExt(filename);

  if (ext === "html") {
    return (
      <iframe
        srcDoc={content}
        sandbox="allow-scripts allow-same-origin"
        className="w-full h-full border-0 bg-white"
        title={filename}
      />
    );
  }

  if (ext === "md") {
    return (
      <div className="px-8 py-6 prose prose-sm dark:prose-invert max-w-none
        prose-headings:font-semibold prose-headings:text-[#1e293b] dark:prose-headings:text-[#e0e0e0]
        prose-p:text-[#444] dark:prose-p:text-[#aaa] prose-p:leading-relaxed
        prose-li:text-[#444] dark:prose-li:text-[#aaa]
        prose-code:bg-[#f5f2eb] dark:prose-code:bg-[#1e1e1e] prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-[#d4473a] dark:prose-code:text-[#f97583]">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    );
  }

  // Code files and plain text
  return (
    <pre className="px-8 py-6 text-[12px] font-mono text-[#444] dark:text-[#aaa] leading-relaxed whitespace-pre-wrap break-words">
      {content}
    </pre>
  );
}

export default function CustomizeSkillsPage() {
  const [q, setQ] = useState("");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  // null = SKILL.md, string = other file path
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [viewMode, setViewMode] = useState<"preview" | "source">("preview");
  const [menuOpen, setMenuOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastReview, setLastReview] = useState<ReviewLogEntry | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: allSkills = [], mutate } = useSWR<Skill[]>(
    "/api/skills/?",
    (url: string) => fetch(`${API}${url}`).then((r) => r.json())
  );

  // Fetch file content when selectedFile changes
  useEffect(() => {
    if (!selectedSkill || selectedFile === null) {
      setFileContent(null);
      return;
    }
    setFileLoading(true);
    readSkillFile(selectedSkill.category, selectedSkill.name, selectedFile)
      .then((d) => setFileContent(d.content))
      .catch(() => setFileContent("（文件读取失败）"))
      .finally(() => setFileLoading(false));
  }, [selectedSkill?.id, selectedFile]);

  useEffect(() => {
    getReviewLog(1).then((entries) => {
      const entry = entries[0] ?? null;
      if (entry && (entry.updated.length > 0 || entry.created.length > 0)) {
        setLastReview(entry);
      } else {
        setLastReview(null);
      }
    }).catch(() => {});
  }, [allSkills]);

  const refresh = () =>
    mutate().then((updated) => {
      if (selectedSkill && updated) {
        const fresh = updated.find((s) => s.id === selectedSkill.id);
        setSelectedSkill(fresh ?? null);
      }
    });

  const skills = q
    ? allSkills.filter(
        (s) =>
          s.name.includes(q) ||
          s.description.toLowerCase().includes(q.toLowerCase()) ||
          s.category.includes(q)
      )
    : allSkills;

  const categories = [...new Set(skills.map((s) => s.category))].sort();

  const patch = async (body: SkillPatch) => {
    if (!selectedSkill) return;
    setBusy(true);
    try {
      await patchSkill(selectedSkill.category, selectedSkill.name, body);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!selectedSkill) return;
    if (!confirm(`删除技能 ${selectedSkill.id}？此操作不可撤销。`)) return;
    setBusy(true);
    try {
      await deleteSkill(selectedSkill.category, selectedSkill.name);
      setSelectedSkill(null);
      setSelectedFile(null);
      mutate();
    } finally {
      setBusy(false);
      setMenuOpen(false);
    }
  };

  const handleFileSelect = (skill: Skill, file: string | null) => {
    setSelectedSkill(skill);
    setSelectedFile(file);
    setViewMode("preview");
  };

  const isActive = selectedSkill?.state === "active";

  // What to show in the preview card
  const currentFilename = selectedFile ?? "SKILL.md";
  const currentContent = selectedFile !== null ? fileContent : (selectedSkill?.content ?? "");
  const isSkillMd = selectedFile === null;

  return (
    <div className="flex h-full bg-[#f5f2eb] dark:bg-[#141414] overflow-hidden">

      {/* ── Left: skill list ── */}
      <div className="w-[280px] flex-shrink-0 flex flex-col border-r border-[#ddd9d0] dark:border-[#202020] bg-[#f5f2eb] dark:bg-[#141414]">
        <div className="flex items-center justify-between px-4 pt-5 pb-3">
          <h2 className="text-[14px] font-semibold text-[#1e293b] dark:text-[#e8e8e8]">Skills</h2>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="p-1.5 rounded-lg text-[#888] hover:text-[#333] dark:hover:text-[#ccc] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e] transition-colors"
            title="导入技能"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M8 2v8M5 7l3 3 3-3M3 11v2a1 1 0 001 1h8a1 1 0 001-1v-2" />
            </svg>
          </button>
          <input ref={fileInputRef} type="file" accept=".md,.zip" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) setImportFile(f); e.target.value = ""; }} />
        </div>

        <div className="px-4 pb-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#1a1a1a]">
            <svg className="w-3.5 h-3.5 text-[#bbb] flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
              <circle cx="6.5" cy="6.5" r="4" /><path d="M11 11l2.5 2.5" />
            </svg>
            <input
              className="flex-1 bg-transparent text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] placeholder-[#bbb] focus:outline-none"
              placeholder="搜索…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        </div>

        {/* Review summary */}
        {lastReview && (lastReview.updated.length > 0 || lastReview.created.length > 0) && (
          <div className="mx-4 mb-2 px-3 py-2 rounded-lg bg-blue-50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/30 flex flex-col gap-1">
            <p className="text-[10px] text-blue-400 dark:text-blue-500 font-medium uppercase tracking-wide">上次对话</p>
            {lastReview.created.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <span className="text-[10.5px] text-blue-500 dark:text-blue-400 flex-shrink-0">新建</span>
                {lastReview.created.map((name) => (
                  <span key={name} className="text-[10.5px] bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded px-1.5 py-0.5 font-mono">
                    {name}
                  </span>
                ))}
              </div>
            )}
            {lastReview.updated.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <span className="text-[10.5px] text-blue-500 dark:text-blue-400 flex-shrink-0">更新</span>
                {lastReview.updated.map((name) => (
                  <span key={name} className="text-[10.5px] bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded px-1.5 py-0.5 font-mono">
                    {name}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {skills.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-[#bbb] dark:text-[#444] text-[12px] gap-1.5">
              <svg className="w-8 h-8 opacity-40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
              </svg>
              <span>{q ? "无匹配技能" : "还没有技能"}</span>
            </div>
          ) : (
            categories.map((cat) => (
              <div key={cat} className="mb-2">
                <div className="flex items-center gap-1.5 px-3 py-1.5">
                  <svg className="w-2.5 h-2.5 text-[#aaa]" viewBox="0 0 8 8" fill="currentColor">
                    <path d="M0 2l4 4 4-4z" />
                  </svg>
                  <span className="text-[10.5px] font-semibold text-[#999] dark:text-[#555] uppercase tracking-wider font-mono">
                    {cat}
                  </span>
                </div>
                <div className="ml-3">
                  {skills
                    .filter((s) => s.category === cat)
                    .map((skill) => (
                      <SkillCard
                        key={skill.id}
                        skill={skill}
                        selected={selectedSkill?.id === skill.id}
                        selectedFile={selectedSkill?.id === skill.id ? selectedFile : undefined}
                        onSelect={(s) => { setSelectedSkill(s); setSelectedFile(null); }}
                        onFileSelect={handleFileSelect}
                      />
                    ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Right: detail panel ── */}
      {selectedSkill ? (
        <div className="flex-1 flex flex-col overflow-hidden bg-[#f5f2eb] dark:bg-[#141414]">
          {/* Header */}
          <div className="flex items-center justify-between px-8 pt-6 pb-4 flex-shrink-0">
            <div className="min-w-0">
              <h1 className="text-[18px] font-semibold text-[#1e293b] dark:text-[#e8e8e8] font-mono">
                {selectedSkill.id}
              </h1>
              {selectedFile && (
                <p className="text-[11.5px] text-[#aaa] dark:text-[#555] font-mono mt-0.5">
                  /{selectedFile}
                </p>
              )}
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              <button
                role="switch"
                aria-checked={isActive}
                disabled={busy}
                onClick={() => patch({ state: isActive ? "archived" : "active" })}
                title={isActive ? "停用" : "启用"}
                className={`relative inline-flex h-[26px] w-[46px] flex-shrink-0 items-center rounded-full transition-colors duration-200 disabled:opacity-40
                  ${isActive ? "bg-[#1e90ff]" : "bg-[#d1d5db] dark:bg-[#3a3a3a]"}`}
              >
                <span className={`inline-block h-[20px] w-[20px] transform rounded-full bg-white shadow-md transition-transform duration-200
                  ${isActive ? "translate-x-[22px]" : "translate-x-[3px]"}`} />
              </button>
              {/* Lock toggle */}
              <button
                onClick={() => {
                  if (selectedSkill.source !== "builtin") {
                    patch({ locked: !selectedSkill.locked });
                  }
                }}
                disabled={busy || selectedSkill.source === "builtin"}
                title={
                  selectedSkill.source === "builtin"
                    ? "内置技能不可解锁"
                    : selectedSkill.locked
                    ? "已锁定（AI 不可修改）— 点击解锁"
                    : "未锁定 — 点击锁定"
                }
                className={`p-1.5 rounded-lg transition-colors disabled:opacity-40
                  ${selectedSkill.locked || selectedSkill.source === "builtin"
                    ? "text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950/20"
                    : "text-[#bbb] hover:text-[#666] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e]"
                  }`}
              >
                {selectedSkill.locked || selectedSkill.source === "builtin" ? (
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <rect x="3" y="7" width="10" height="7" rx="1.5" />
                    <path d="M5 7V5a3 3 0 016 0v2" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <rect x="3" y="7" width="10" height="7" rx="1.5" />
                    <path d="M5 7V5a3 3 0 016 0" />
                  </svg>
                )}
              </button>
              <div className="relative">
                <button
                  onClick={() => setMenuOpen((o) => !o)}
                  className="p-1.5 rounded-lg text-[#888] hover:text-[#333] dark:hover:text-[#ccc] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e] transition-colors"
                >
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="currentColor">
                    <circle cx="8" cy="3" r="1.2" /><circle cx="8" cy="8" r="1.2" /><circle cx="8" cy="13" r="1.2" />
                  </svg>
                </button>
                {menuOpen && (
                  <div className="absolute right-0 top-8 w-40 rounded-xl border border-[#e5e1d8] dark:border-[#2a2a2a] bg-white dark:bg-[#1a1a1a] shadow-lg z-20 py-1 overflow-hidden">
                    <button onClick={() => { setEditingSkill(selectedSkill); setMenuOpen(false); }}
                      className="w-full text-left px-4 py-2 text-[12px] text-[#333] dark:text-[#ccc] hover:bg-[#f5f2eb] dark:hover:bg-[#222] transition-colors">
                      编辑
                    </button>
                    <button onClick={() => { patch({ pinned: !selectedSkill.pinned }); setMenuOpen(false); }} disabled={busy}
                      className="w-full text-left px-4 py-2 text-[12px] text-[#333] dark:text-[#ccc] hover:bg-[#f5f2eb] dark:hover:bg-[#222] transition-colors disabled:opacity-40">
                      {selectedSkill.pinned ? "取消置顶" : "置顶"}
                    </button>
                    <div className="my-1 border-t border-[#f0ede6] dark:border-[#222]" />
                    <button onClick={remove} disabled={busy || selectedSkill.pinned}
                      className="w-full text-left px-4 py-2 text-[12px] text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors disabled:opacity-30">
                      删除
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Metadata — only for SKILL.md view */}
          {isSkillMd && (
            <>
              <div className="flex items-start gap-10 px-8 pb-4 flex-shrink-0">
                <div>
                  <p className="text-[10.5px] font-medium text-[#aaa] dark:text-[#555] uppercase tracking-wide mb-1">来源</p>
                  <p className="text-[12.5px] text-[#333] dark:text-[#ccc] font-medium">
                    {SOURCE_LABEL[selectedSkill.source] ?? selectedSkill.source}
                  </p>
                </div>
                <div>
                  <p className="text-[10.5px] font-medium text-[#aaa] dark:text-[#555] uppercase tracking-wide mb-1">触发方式</p>
                  <p className="text-[12.5px] text-[#333] dark:text-[#ccc] font-medium">Agent 自动</p>
                </div>
                {selectedSkill.use_count > 0 && (
                  <div>
                    <p className="text-[10.5px] font-medium text-[#aaa] dark:text-[#555] uppercase tracking-wide mb-1">调用次数</p>
                    <p className="text-[12.5px] text-[#333] dark:text-[#ccc] font-medium">{selectedSkill.use_count}</p>
                  </div>
                )}
              </div>
              <div className="px-8 pb-5 flex-shrink-0">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <p className="text-[11px] font-semibold text-[#888] dark:text-[#666] uppercase tracking-wide">描述</p>
                  <svg className="w-3 h-3 text-[#bbb]" viewBox="0 0 16 16" fill="currentColor">
                    <path fillRule="evenodd" d="M8 15A7 7 0 108 1a7 7 0 000 14zm0-9a1 1 0 110-2 1 1 0 010 2zm-1 1h2v4H7v-4z" />
                  </svg>
                </div>
                <p className="text-[13px] text-[#444] dark:text-[#aaa] leading-relaxed">{selectedSkill.description}</p>
                {selectedSkill.tags.length > 0 && (
                  <div className="flex gap-1.5 mt-2 flex-wrap">
                    {selectedSkill.tags.map((t) => (
                      <span key={t} className="px-2 py-0.5 rounded-full text-[10.5px] bg-[#e8e4dc] dark:bg-[#1e1e1e] text-[#666] dark:text-[#888]">#{t}</span>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* Preview card */}
          <div className="flex-1 overflow-hidden px-8 pb-8 flex flex-col">
            <div className="flex-1 rounded-2xl border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#0e0e0e] flex flex-col overflow-hidden shadow-sm">
              {/* Card toolbar */}
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#f0ede6] dark:border-[#1a1a1a] flex-shrink-0">
                <span className="text-[11px] font-mono text-[#bbb] dark:text-[#444]">{currentFilename}</span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setViewMode("preview")}
                    title="渲染预览"
                    className={`p-1.5 rounded-lg transition-colors ${viewMode === "preview" ? "bg-[#f0ede6] dark:bg-[#222] text-[#333] dark:text-[#ccc]" : "text-[#bbb] hover:text-[#666]"}`}
                  >
                    <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" /><circle cx="8" cy="8" r="2" />
                    </svg>
                  </button>
                  <button
                    onClick={() => setViewMode("source")}
                    title="查看源码"
                    className={`p-1.5 rounded-lg transition-colors ${viewMode === "source" ? "bg-[#f0ede6] dark:bg-[#222] text-[#333] dark:text-[#ccc]" : "text-[#bbb] hover:text-[#666]"}`}
                  >
                    <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <path d="M5 4L1 8l4 4M11 4l4 4-4 4M9 2l-2 12" />
                    </svg>
                  </button>
                </div>
              </div>

              {/* Card content */}
              <div className="flex-1 overflow-y-auto">
                {fileLoading ? (
                  <div className="flex items-center justify-center h-24 text-[12px] text-[#bbb]">加载中…</div>
                ) : viewMode === "source" ? (
                  <pre className="px-8 py-6 text-[12px] text-[#555] dark:text-[#888] font-mono leading-relaxed whitespace-pre-wrap break-words">
                    {currentContent || "（无内容）"}
                  </pre>
                ) : currentContent ? (
                  <FilePreview filename={currentFilename} content={currentContent} />
                ) : (
                  <p className="px-8 py-6 text-[12px] text-[#bbb] dark:text-[#444] italic">暂无内容</p>
                )}
              </div>

              {/* Card footer */}
              {isSkillMd && (
                <div className="border-t border-[#f0ede6] dark:border-[#1a1a1a] px-6 py-2.5 flex items-center gap-3 flex-shrink-0">
                  <span className="text-[10.5px] text-[#ccc] dark:text-[#444]">v{selectedSkill.version}</span>
                  {selectedSkill.last_activity_at && (
                    <span className="text-[10.5px] text-[#ccc] dark:text-[#444]">
                      {new Date(selectedSkill.last_activity_at * 1000).toLocaleDateString("zh-CN")}
                    </span>
                  )}
                  <button
                    onClick={() => setEditingSkill(selectedSkill)}
                    className="ml-auto px-3 py-1 rounded-lg text-[11.5px] bg-[#1e293b] dark:bg-[#2a2a2a] text-white hover:bg-[#2d3f57] transition-colors"
                  >
                    编辑
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-[#ccc] dark:text-[#333] gap-3">
          <svg className="w-14 h-14 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
            <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
          </svg>
          <p className="text-[13px]">从左侧选择一个技能查看详情</p>
        </div>
      )}

      {menuOpen && <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />}

      {importFile && (
        <SkillImportModal file={importFile} onClose={() => setImportFile(null)} onDone={refresh} />
      )}
      {editingSkill && (
        <SkillEditor skill={editingSkill} onSave={() => { setEditingSkill(null); refresh(); }} onClose={() => setEditingSkill(null)} />
      )}
    </div>
  );
}
