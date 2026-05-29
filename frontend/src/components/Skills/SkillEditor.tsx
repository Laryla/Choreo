import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Skill, SkillCreate, SkillPatch } from "@/api/skills";
import { createSkill, patchSkill } from "@/api/skills";

interface Props {
  skill?: Skill | null;
  onSave: () => void;
  onClose: () => void;
}

const TEMPLATE = `## When to Use
-

## Steps
1.

## Common Pitfalls
-

## Verification Checklist
- [ ] `;

export default function SkillEditor({ skill, onSave, onClose }: Props) {
  const isCreate = !skill;
  const [category, setCategory] = useState(skill?.category ?? "");
  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [tags, setTags] = useState((skill?.tags ?? []).join(", "));
  const [content, setContent] = useState(skill?.content ?? TEMPLATE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    if (!description.trim()) { setError("description 不能为空"); return; }
    if (isCreate && (!category.trim() || !name.trim())) { setError("category 和 name 不能为空"); return; }
    setBusy(true); setError("");
    try {
      const tagsArr = tags.split(",").map(t => t.trim()).filter(Boolean);
      if (isCreate) {
        const body: SkillCreate = { category: category.trim(), name: name.trim(), description, tags: tagsArr, content };
        await createSkill(body);
      } else {
        const body: SkillPatch = { description, tags: tagsArr, content };
        await patchSkill(skill!.category, skill!.name, body);
      }
      onSave();
    } catch (e: any) {
      setError(e.message ?? "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-[#1a1a1a] rounded-2xl shadow-2xl w-[90vw] max-w-5xl h-[85vh] flex flex-col overflow-hidden border border-[#e5e1d8] dark:border-[#252525]">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#e5e1d8] dark:border-[#252525]">
          <h2 className="text-[13px] font-semibold text-[#1e293b] dark:text-[#c8c8c8]">
            {isCreate ? "新建技能" : `编辑 ${skill!.id}`}
          </h2>
          <button onClick={onClose} className="text-[#aaa] hover:text-[#555] text-lg leading-none">✕</button>
        </div>
        <div className="flex gap-2 px-5 py-2.5 border-b border-[#f0ede6] dark:border-[#222] flex-wrap">
          {isCreate && (
            <>
              <input className="px-2.5 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#141414] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none w-28" placeholder="category" value={category} onChange={e => setCategory(e.target.value)} />
              <input className="px-2.5 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#141414] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none w-40" placeholder="name (kebab-case)" value={name} onChange={e => setName(e.target.value)} />
            </>
          )}
          <input className="px-2.5 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#141414] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none flex-1 min-w-48" placeholder="description: Use when..." value={description} onChange={e => setDescription(e.target.value)} />
          <input className="px-2.5 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#141414] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none w-44" placeholder="tags: git, report" value={tags} onChange={e => setTags(e.target.value)} />
        </div>
        <div className="flex-1 flex overflow-hidden">
          <textarea
            className="flex-1 p-4 font-mono text-[12px] leading-relaxed bg-[#fafaf8] dark:bg-[#141414] text-[#1a1a1a] dark:text-[#c8c8c8] border-r border-[#e5e1d8] dark:border-[#252525] resize-none focus:outline-none"
            value={content}
            onChange={e => setContent(e.target.value)}
            spellCheck={false}
          />
          <div className="flex-1 p-4 overflow-y-auto prose prose-sm dark:prose-invert max-w-none text-[12px]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        </div>
        <div className="flex items-center justify-between px-5 py-2.5 border-t border-[#e5e1d8] dark:border-[#252525]">
          <span className={`text-[11px] ${error ? "text-red-500" : "text-[#aaa]"}`}>
            {error || "左侧编辑 · 右侧预览"}
          </span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#333] text-[#555] dark:text-[#888] text-[12px] hover:bg-[#f0ede6] dark:hover:bg-[#222] transition-colors">取消</button>
            <button onClick={save} disabled={busy} className="px-3 py-1.5 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:bg-[#2d3f57] transition-colors disabled:opacity-40">
              {busy ? "保存中…" : "保存"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
