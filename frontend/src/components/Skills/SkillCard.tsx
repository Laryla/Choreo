import { useState } from "react";
import type { Skill } from "@/api/skills";
import { listSkillFiles } from "@/api/skills";

interface Props {
  skill: Skill;
  selected?: boolean;
  selectedFile?: string | null; // null = SKILL.md
  onSelect: (skill: Skill) => void;
  onFileSelect: (skill: Skill, file: string | null) => void;
}

function FolderIcon() {
  return (
    <svg className="w-3.5 h-3.5 flex-shrink-0 text-[#aaa]" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M1.5 4.5A1.5 1.5 0 013 3h3.586a1 1 0 01.707.293L8.5 4.5H13A1.5 1.5 0 0114.5 6v5A1.5 1.5 0 0113 12.5H3A1.5 1.5 0 011.5 11V4.5z" />
    </svg>
  );
}

export default function SkillCard({ skill, selected, selectedFile, onSelect, onFileSelect }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [files, setFiles] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);

  const toggleExpand = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!expanded && files === null) {
      setLoading(true);
      try {
        const data = await listSkillFiles(skill.category, skill.name);
        setFiles(Array.isArray(data) ? data : []);
      } catch {
        setFiles([]);
      } finally {
        setLoading(false);
      }
    }
    setExpanded((v) => !v);
  };

  const isSkillMdActive = selected && selectedFile === null;

  return (
    <div>
      {/* Skill row */}
      <div
        onClick={() => { onSelect(skill); onFileSelect(skill, null); }}
        className={`flex items-center gap-1 pl-1 pr-3 py-2 rounded-lg cursor-pointer select-none transition-colors
          ${selected && !expanded
            ? "bg-[#eae7e0] dark:bg-[#222]"
            : "hover:bg-[#f0ede6] dark:hover:bg-[#181818]"}`}
      >
        <button
          onClick={toggleExpand}
          className="p-1 rounded flex-shrink-0 text-[#bbb] hover:text-[#555] dark:hover:text-[#aaa] transition-colors"
        >
          <svg
            className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`}
            viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"
          >
            <path d="M4 2l4 4-4 4" />
          </svg>
        </button>
        <span className={`font-mono text-[12px] flex-1 truncate leading-snug flex items-center gap-1
          ${selected ? "text-[#1e293b] dark:text-[#e8e8e8] font-semibold" : "text-[#444] dark:text-[#aaa]"}`}>
          <span className="truncate">{skill.name}</span>
          {skill.last_reviewed_at && Date.now() / 1000 - skill.last_reviewed_at < 86400 && (
            <span
              title={`AI 于 ${Math.round((Date.now() / 1000 - skill.last_reviewed_at) / 60)} 分钟前更新`}
              className="ml-1 inline-flex items-center px-1 py-0.5 rounded text-[9px] font-semibold bg-blue-100 dark:bg-blue-950/40 text-blue-500 dark:text-blue-400 leading-none flex-shrink-0"
            >
              ✦ AI
            </span>
          )}
        </span>
      </div>

      {/* File tree */}
      {expanded && (
        <div className="ml-6 mb-1">
          {/* SKILL.md */}
          <div
            onClick={() => { onSelect(skill); onFileSelect(skill, null); }}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-colors
              ${isSkillMdActive ? "bg-[#eae7e0] dark:bg-[#222]" : "hover:bg-[#f0ede6] dark:hover:bg-[#181818]"}`}
          >
            <span className={`text-[11.5px] ${isSkillMdActive ? "text-[#1e293b] dark:text-[#e8e8e8] font-medium" : "text-[#555] dark:text-[#888]"}`}>
              SKILL.md
            </span>
          </div>

          {loading ? (
            <div className="px-3 py-1 text-[10.5px] text-[#bbb]">加载中…</div>
          ) : (
            (files ?? []).map((f) => {
              const isDir = f.endsWith("/");
              const isActive = selected && selectedFile === f;
              return (
                <div
                  key={f}
                  onClick={isDir ? undefined : () => { onSelect(skill); onFileSelect(skill, f); }}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-colors
                    ${isDir ? "cursor-default" : "cursor-pointer"}
                    ${isActive ? "bg-[#eae7e0] dark:bg-[#222]" : isDir ? "" : "hover:bg-[#f0ede6] dark:hover:bg-[#181818]"}`}
                >
                  {isDir && <FolderIcon />}
                  <span className={`text-[11.5px] flex-1 truncate
                    ${isActive ? "text-[#1e293b] dark:text-[#e8e8e8] font-medium" : "text-[#555] dark:text-[#888]"}`}>
                    {f}
                  </span>
                  {isDir && (
                    <svg className="w-3 h-3 text-[#ccc] flex-shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M4 2l4 4-4 4" />
                    </svg>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
