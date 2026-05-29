import { useState, useEffect, KeyboardEvent, useRef } from "react";
import useSWR from "swr";

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
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data: models = [] } = useSWR<ModelInfo[]>("/models/", fetcher);
  const { data: activeData } = useSWR<{ active_model: string }>("/models/active", fetcher);

  // 初始化选中默认模型
  useEffect(() => {
    if (!selectedModel && activeData?.active_model) {
      setSelectedModel(activeData.active_model);
    }
  }, [activeData, selectedModel]);

  // 点外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSend = () => {
    if (!text.trim() || disabled) return;
    const context: Record<string, unknown> = {};
    if (selectedModel) context.model_name = selectedModel;
    onSend(text.trim(), context);
    setText("");
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const currentModel = models.find((m) => m.name === selectedModel);
  const displayLabel = currentModel?.display_name ?? currentModel?.name ?? selectedModel;

  return (
    <div className="px-6 pb-4 pt-3">
      <div className="max-w-[740px] mx-auto">
        {/* 模型选择器 */}
        {models.length > 0 && (
          <div className="flex items-center gap-2 mb-2 px-1" ref={dropdownRef}>
            <span className="text-[10px] text-[#aaa] dark:text-[#555]">模型</span>
            <div className="relative">
              <button
                onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] bg-[#e8e4dc] dark:bg-[#1e1e1e] text-[#555] dark:text-[#888] hover:bg-[#ddd9d0] dark:hover:bg-[#252525] transition-colors"
              >
                <span>{displayLabel || "选择模型"}</span>
                <svg className="w-2.5 h-2.5 opacity-50" viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M1 1l4 4 4-4" />
                </svg>
              </button>
              {open && (
                <div className="absolute bottom-full mb-1 left-0 min-w-[140px] bg-white dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] rounded-lg shadow-md py-1 z-50">
                  {models.map((m) => (
                    <button
                      key={m.name}
                      onClick={() => { setSelectedModel(m.name); setOpen(false); }}
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

        {/* 输入框 */}
        <div className="flex items-end gap-2.5 bg-white dark:bg-[#1a1a1a] border border-[#d6d0c7] dark:border-[#252525] rounded-[13px] px-3.5 py-2.5 shadow-sm dark:shadow-none">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKey}
            placeholder="描述你想自动化的任务，例如：每周五整理 commit 发飞书…"
            disabled={disabled}
            rows={2}
            className="flex-1 resize-none outline-none bg-transparent text-[12.5px] text-[#1a1a1a] dark:text-[#e8e8e8] placeholder-[#bbb] dark:placeholder-[#3a3a3a]"
          />
          <button
            onClick={handleSend}
            disabled={disabled || !text.trim()}
            className="w-7 h-7 rounded-lg bg-[#1e293b] dark:bg-[#252525] text-white dark:text-[#aaa] flex items-center justify-center text-sm flex-shrink-0 disabled:opacity-30 hover:opacity-80 transition-opacity"
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  );
}
