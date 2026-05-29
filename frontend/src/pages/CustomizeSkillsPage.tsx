// frontend/src/pages/CustomizeSkillsPage.tsx
import { useState } from "react";
import useSWR from "swr";
import SkillCard from "@/components/Skills/SkillCard";
import SkillEditor from "@/components/Skills/SkillEditor";
import type { Skill } from "@/api/skills";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
type Tab = "active" | "archived";

export default function CustomizeSkillsPage() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<Tab>("active");
  const [editTarget, setEditTarget] = useState<Skill | null | undefined>(undefined);

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tab === "archived") params.set("state", "archived");
  const swrKey = `/api/skills/?${params.toString()}`;

  const { data: skills = [], mutate } = useSWR<Skill[]>(
    swrKey,
    (url: string) => fetch(`${API}${url}`).then((r) => r.json())
  );

  const refresh = () => mutate();
  const categories = [...new Set(skills.map((s) => s.category))].sort();

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#0d0d0d]">
      {/* Content header */}
      <div className="px-7 pt-6 pb-4 border-b border-[#ddd9d0] dark:border-[#141414]">
        <h1 className="text-[17px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] mb-1">技能库</h1>
        <p className="text-[12px] text-[#999] dark:text-[#555]">管理 AI 助手的专项技能，技能会在对话中被自动调用</p>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2.5 px-7 py-3 border-b border-[#ddd9d0] dark:border-[#141414] bg-[#f0ede6] dark:bg-[#0d0d0d]">
        <div className="flex gap-1">
          {(["active", "archived"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-lg text-[11.5px] transition-colors ${
                tab === t
                  ? "bg-[#1e293b] dark:bg-[#2a2a2a] text-white"
                  : "text-[#666] dark:text-[#888] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e]"
              }`}
            >
              {t === "active" ? "当前" : "归档"}
            </button>
          ))}
        </div>
        <input
          className="flex-1 max-w-xs px-3 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none"
          placeholder="搜索技能…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button
          onClick={() => setEditTarget(null)}
          className="ml-auto px-3 py-1.5 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:bg-[#2d3f57] transition-colors"
        >
          + 新建技能
        </button>
      </div>

      {/* Skills list */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[860px] mx-auto px-7 py-5">
          {skills.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-[#bbb] dark:text-[#333] text-sm gap-2">
              <span className="text-4xl">⚡</span>
              <span>{q ? "没有匹配的技能" : "还没有技能，点击右上角新建"}</span>
            </div>
          ) : (
            categories.map((cat) => (
              <div key={cat} className="mb-6">
                <h3 className="text-[11px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wider mb-2 font-mono">
                  {cat}/
                </h3>
                <div className="flex flex-col gap-2">
                  {skills
                    .filter((s) => s.category === cat)
                    .map((skill) => (
                      <SkillCard
                        key={skill.id}
                        skill={skill}
                        onUpdate={refresh}
                        onDelete={refresh}
                        onEdit={(s) => setEditTarget(s)}
                      />
                    ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {editTarget !== undefined && (
        <SkillEditor
          skill={editTarget}
          onSave={() => { refresh(); setEditTarget(undefined); }}
          onClose={() => setEditTarget(undefined)}
        />
      )}
    </div>
  );
}
