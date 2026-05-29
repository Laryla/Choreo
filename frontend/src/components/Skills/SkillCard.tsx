import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Skill, SkillPatch } from "@/api/skills";
import { patchSkill, deleteSkill } from "@/api/skills";

interface Props {
  skill: Skill;
  onUpdate: () => void;
  onDelete: () => void;
  onEdit: (skill: Skill) => void;
}

export default function SkillCard({ skill, onUpdate, onDelete, onEdit }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const patch = async (body: SkillPatch) => {
    setBusy(true);
    try { await patchSkill(skill.category, skill.name, body); onUpdate(); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!confirm(`删除技能 ${skill.id}？此操作不可撤销。`)) return;
    setBusy(true);
    try { await deleteSkill(skill.category, skill.name); onDelete(); }
    finally { setBusy(false); }
  };

  const sourceLabel: Record<string, string> = {
    auto: "自动", builtin: "内置", manual: "",
  };
  const sourceBadge: Record<string, string> = {
    auto: "bg-[#f0fdf4] dark:bg-[#0d1f12] text-[#16a34a] dark:text-[#4ade80] border-[#bbf7d0] dark:border-[#14532d]",
    builtin: "bg-[#eff6ff] dark:bg-[#0c1a2e] text-[#3b82f6] dark:text-[#60a5fa] border-[#bfdbfe] dark:border-[#1e3a5f]",
  };

  return (
    <div className={`rounded-xl border bg-white dark:bg-[#1a1a1a] ${skill.pinned ? "border-[#e2b714] dark:border-[#a38200]" : "border-[#e5e1d8] dark:border-[#252525]"}`}>
      <div className="flex items-start gap-2 px-4 py-3 cursor-pointer select-none" onClick={() => setExpanded(e => !e)}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            {skill.pinned && <span className="text-[#e2b714]">📌</span>}
            <span className="font-mono text-[12px] font-semibold text-[#1e293b] dark:text-[#c8c8c8]">{skill.id}</span>
            {skill.source !== "manual" && (
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] border ${sourceBadge[skill.source] ?? ""}`}>
                {sourceLabel[skill.source]}
              </span>
            )}
            {skill.tags.map(t => (
              <span key={t} className="px-1.5 py-0.5 rounded-full text-[10px] bg-[#f5f2eb] dark:bg-[#222] text-[#666] dark:text-[#888]">#{t}</span>
            ))}
          </div>
          <p className="text-[11.5px] text-[#555] dark:text-[#888] line-clamp-1">{skill.description}</p>
          {skill.use_count > 0 && (
            <p className="text-[10px] text-[#bbb] dark:text-[#555] mt-0.5">
              调用 {skill.use_count} 次{skill.last_activity_at ? ` · ${new Date(skill.last_activity_at * 1000).toLocaleDateString("zh-CN")}` : ""}
            </p>
          )}
        </div>
        <svg className={`w-3.5 h-3.5 text-[#aaa] flex-shrink-0 mt-1 transition-transform ${expanded ? "rotate-90" : ""}`} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 2l4 4-4 4" />
        </svg>
      </div>
      {expanded && (
        <div className="px-4 pb-3 border-t border-[#f0ede6] dark:border-[#222] pt-3">
          <div className="prose prose-sm dark:prose-invert max-w-none text-[12px] leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{skill.content || "_（无内容）_"}</ReactMarkdown>
          </div>
        </div>
      )}
      <div className="flex gap-1 px-4 py-2 border-t border-[#f0ede6] dark:border-[#222]">
        <button onClick={() => patch({ pinned: !skill.pinned })} disabled={busy}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-[#e2b714] hover:bg-[#fef9c3] dark:hover:bg-[#1c1900] transition-colors disabled:opacity-40">
          {skill.pinned ? "取消锁定" : "锁定"}
        </button>
        <button onClick={() => onEdit(skill)} disabled={busy}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-[#1e293b] dark:hover:text-[#c8c8c8] hover:bg-[#f0ede6] dark:hover:bg-[#252525] transition-colors disabled:opacity-40">
          编辑
        </button>
        <button onClick={() => patch({ state: skill.state === "active" ? "archived" : "active" })} disabled={busy}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-[#555] hover:bg-[#f0ede6] dark:hover:bg-[#252525] transition-colors disabled:opacity-40">
          {skill.state === "active" ? "归档" : "恢复"}
        </button>
        <button onClick={remove} disabled={busy || skill.pinned}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 transition-colors disabled:opacity-40 ml-auto">
          删除
        </button>
      </div>
    </div>
  );
}
