import { useState } from "react";
import useSWR from "swr";
import Topbar from "@/components/Topbar/Topbar";
import SkillCard from "@/components/Skills/SkillCard";
import SkillEditor from "@/components/Skills/SkillEditor";
import type { Skill } from "@/api/skills";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
type Tab = "active" | "archived";

export default function SkillsPage() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<Tab>("active");
  const [editTarget, setEditTarget] = useState<Skill | null | undefined>(undefined);

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tab === "archived") params.set("state", "archived");
  const swrKey = `/api/skills/?${params.toString()}`;

  const { data: skills = [], mutate } = useSWR<Skill[]>(
    swrKey,
    (url: string) => fetch(`${API}${url}`).then(r => r.json())
  );

  const refresh = () => mutate();
  const categories = [...new Set(skills.map(s => s.category))].sort();

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="技能库" />
      <div className="flex items-center gap-2.5 px-6 py-2.5 border-b border-[#ddd9d0] dark:border-[#202020] bg-[#f0ede6] dark:bg-[#141414]">
        <div className="flex gap-1">
          {(["active", "archived"] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-lg text-[11.5px] transition-colors ${tab === t ? "bg-[#1e293b] dark:bg-[#2a2a2a] text-white" : "text-[#666] dark:text-[#888] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e]"}`}>
              {t === "active" ? "当前" : "归档"}
            </button>
          ))}
        </div>
        <input
          className="flex-1 max-w-xs px-3 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none"
          placeholder="搜索技能…"
          value={q}
          onChange={e => setQ(e.target.value)}
        />
        <button onClick={() => setEditTarget(null)}
          className="ml-auto px-3 py-1.5 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:bg-[#2d3f57] transition-colors">
          + 新建技能
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[900px] mx-auto px-6 py-5">
          {skills.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-[#bbb] dark:text-[#333] text-sm gap-2">
              <span className="text-4xl">⚡</span>
              <span>{q ? "没有匹配的技能" : "还没有技能，点击右上角新建"}</span>
            </div>
          ) : categories.map(cat => (
            <div key={cat} className="mb-6">
              <h3 className="text-[11px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wider mb-2 font-mono">{cat}/</h3>
              <div className="flex flex-col gap-2">
                {skills.filter(s => s.category === cat).map(skill => (
                  <SkillCard key={skill.id} skill={skill}
                    onUpdate={refresh} onDelete={refresh}
                    onEdit={s => setEditTarget(s)} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      {editTarget !== undefined && (
        <SkillEditor skill={editTarget} onSave={() => { refresh(); setEditTarget(undefined); }} onClose={() => setEditTarget(undefined)} />
      )}
    </div>
  );
}
