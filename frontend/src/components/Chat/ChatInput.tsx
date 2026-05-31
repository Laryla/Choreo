import { useState, useEffect, useCallback, useRef, KeyboardEvent } from "react";
import useSWR from "swr";
import type { Skill } from "@/api/skills";
import { SKILLS_KEY } from "@/hooks/useChat";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const fetcher = (url: string) => fetch(`${API}${url}`).then((r) => r.json());

interface ModelInfo { name: string; model?: string; display_name?: string }
interface Props {
  onSend: (text: string, context: Record<string, unknown>) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [modelOpen, setModelOpen] = useState(false);

  // Slash command state
  const [slashSkill, setSlashSkill] = useState<{id: string; category: string; name: string} | null>(null);
  const [dropdownIdx, setDropdownIdx] = useState(0);

  const modelDropdownRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: models = [] } = useSWR<ModelInfo[]>("/models/", fetcher);
  const { data: activeData } = useSWR<{ active_model: string }>("/models/active", fetcher);
  const { data: allSkills = [] } = useSWR<Skill[]>(SKILLS_KEY, fetcher);

  // 初始化默认模型
  useEffect(() => {
    if (!selectedModel && activeData?.active_model) {
      setSelectedModel(activeData.active_model);
    }
  }, [activeData, selectedModel]);

  // 点击模型下拉外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) {
        setModelOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // 当文字变化时重置弹窗高亮索引
  useEffect(() => {
    setDropdownIdx(0);
  }, [text]);

  // 技能弹窗过滤逻辑：未在命令模式 且 以 "/" 开头
  const slashQuery =
    slashSkill === null && text.startsWith("/")
      ? text.slice(1).toLowerCase()
      : null;

  const filteredSkills: Skill[] =
    slashQuery !== null
      ? allSkills
          .filter(
            (s) =>
              s.state === "active" &&
              (s.id.toLowerCase().includes(slashQuery) ||
                s.description.toLowerCase().includes(slashQuery))
          )
          .slice(0, 6)
      : [];

  const showSkillDropdown = filteredSkills.length > 0;

  // 选中技能，进入命令模式
  const selectSkill = useCallback((skill: Skill) => {
    setSlashSkill({ id: skill.id, category: skill.category, name: skill.name });
    setText("");
    setDropdownIdx(0);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, []);

  // 清除命令模式
  const clearSlashMode = useCallback(() => {
    setSlashSkill(null);
    setText("");
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, []);

  // 发送（含展开逻辑）
  const handleSend = useCallback(async () => {
    const hasContent = slashSkill !== null || text.trim();
    if (!hasContent || disabled) return;

    let messageText = text.trim();
    const context: Record<string, unknown> = {};
    if (selectedModel) context.model_name = selectedModel;

    if (slashSkill) {
      try {
        const res = await fetch(`${API}/api/skills/${slashSkill.category}/${slashSkill.name}`);
        if (res.ok) {
          const skill: Skill = await res.json();
          const content = skill.content ?? "";
          const args = messageText;
          let skillContent: string;
          if (content.includes("$ARGUMENTS")) {
            skillContent = content.replace(/\$ARGUMENTS/g, args);
          } else {
            skillContent = content;
          }
          context.skill_context = skillContent;
          // messageText stays as the user's original input — do NOT overwrite it
        }
      } catch {
        // fetch 失败则继续，不带 skill context
      }
    }

    // skill selected but no user text — use skill name as a minimal trigger
    if (!messageText.trim() && context.skill_context) {
      messageText = `/${slashSkill!.id}`;
    }

    if (!messageText.trim() && !context.skill_context) return;

    onSend(messageText, context);
    setText("");
    setSlashSkill(null);
  }, [slashSkill, text, disabled, selectedModel, onSend]);

  const handleKey = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // 弹窗导航
      if (showSkillDropdown) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setDropdownIdx((i) => Math.min(i + 1, filteredSkills.length - 1));
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          setDropdownIdx((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === "Enter" || e.key === "Tab") {
          e.preventDefault();
          selectSkill(filteredSkills[dropdownIdx]);
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setText("");
          return;
        }
      }
      // 普通 Enter 发送
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [showSkillDropdown, filteredSkills, dropdownIdx, selectSkill, handleSend]
  );

  const currentModel = models.find((m) => m.name === selectedModel);
  const displayLabel = currentModel?.display_name ?? currentModel?.name ?? selectedModel;
  const canSend = !disabled && (slashSkill !== null || !!text.trim());

  return (
    <div className="px-6 pb-4 pt-3">
      <div className="max-w-[740px] mx-auto">
        {/* 模型选择器 */}
        {models.length > 0 && (
          <div className="flex items-center gap-2 mb-2 px-1" ref={modelDropdownRef}>
            <span className="text-[10px] text-[#aaa] dark:text-[#555]">模型</span>
            <div className="relative">
              <button
                onClick={() => setModelOpen((v) => !v)}
                className="flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] bg-[#e8e4dc] dark:bg-[#1e1e1e] text-[#555] dark:text-[#888] hover:bg-[#ddd9d0] dark:hover:bg-[#252525] transition-colors"
              >
                <span>{displayLabel || "选择模型"}</span>
                <svg className="w-2.5 h-2.5 opacity-50" viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M1 1l4 4 4-4" />
                </svg>
              </button>
              {modelOpen && (
                <div className="absolute bottom-full mb-1 left-0 min-w-[140px] bg-white dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] rounded-lg shadow-md py-1 z-50">
                  {models.map((m) => (
                    <button
                      key={m.name}
                      onClick={() => { setSelectedModel(m.name); setModelOpen(false); }}
                      className={`w-full text-left px-3 py-1.5 text-[11px] hover:bg-[#f5f2eb] dark:hover:bg-[#252525] transition-colors ${
                        m.name === selectedModel
                          ? "text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                          : "text-[#555] dark:text-[#888]"
                      }`}
                    >
                      {m.display_name ?? m.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 输入区域（含弹窗定位容器） */}
        <div className="relative">
          {/* 技能选择弹窗 */}
          {showSkillDropdown && (
            <div className="absolute bottom-full left-0 right-0 mb-1.5 bg-white dark:bg-[#1a1a1a] border border-[#d6d0c7] dark:border-[#252525] rounded-xl shadow-lg overflow-hidden z-50">
              {filteredSkills.map((skill, i) => (
                <button
                  key={skill.id}
                  onMouseDown={(e) => { e.preventDefault(); selectSkill(skill); }}
                  className={`w-full text-left px-3 py-2 transition-colors ${
                    i === dropdownIdx
                      ? "bg-[#f5f2eb] dark:bg-[#252525]"
                      : "hover:bg-[#f9f7f3] dark:hover:bg-[#1f1f1f]"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-[#888] dark:text-[#555]">/</span>
                    <span className="text-[11.5px] font-medium text-[#1a1a1a] dark:text-[#e8e8e8]">{skill.id}</span>
                  </div>
                  <p className="text-[10px] text-[#999] dark:text-[#555] truncate mt-0.5">{skill.description}</p>
                  {skill.arguments && (
                    <p className="text-[9.5px] text-[#bbb] dark:text-[#444] mt-0.5">参数：{skill.arguments}</p>
                  )}
                </button>
              ))}
            </div>
          )}

          {/* 输入框主体 */}
          <div className="flex flex-col bg-white dark:bg-[#1a1a1a] border border-[#d6d0c7] dark:border-[#252525] rounded-[13px] px-3.5 py-2.5 shadow-sm dark:shadow-none">
            {/* 命令模式 chip */}
            {slashSkill && (
              <div className="flex items-center gap-1.5 mb-2">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900/50 text-[11px] font-mono text-blue-600 dark:text-blue-400 leading-none">
                  /{slashSkill.id}
                  <button
                    onClick={clearSlashMode}
                    className="ml-0.5 text-blue-400 dark:text-blue-600 hover:text-blue-600 dark:hover:text-blue-400 transition-colors leading-none"
                    tabIndex={-1}
                  >
                    ×
                  </button>
                </span>
              </div>
            )}

            {/* 文本输入 + 发送按钮 */}
            <div className="flex items-end gap-2.5">
              <textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={handleKey}
                placeholder={
                  slashSkill
                    ? "输入参数（可选）…"
                    : "描述你想自动化的任务，或输入 / 选择技能…"
                }
                disabled={disabled}
                rows={2}
                className="flex-1 resize-none outline-none bg-transparent text-[12.5px] text-[#1a1a1a] dark:text-[#e8e8e8] placeholder-[#bbb] dark:placeholder-[#3a3a3a]"
              />
              <button
                onClick={handleSend}
                disabled={!canSend}
                className="w-7 h-7 rounded-lg bg-[#1e293b] dark:bg-[#252525] text-white dark:text-[#aaa] flex items-center justify-center text-sm flex-shrink-0 disabled:opacity-30 hover:opacity-80 transition-opacity"
              >
                ↑
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
