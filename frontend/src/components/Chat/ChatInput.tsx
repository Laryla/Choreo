import { useState, KeyboardEvent } from "react";

interface Props { onSend: (text: string) => void; disabled?: boolean }

export default function ChatInput({ onSend, disabled }: Props) {
  const [text, setText] = useState("");

  const handleSend = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText("");
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="px-6 pb-4 pt-3">
      <div className="max-w-[740px] mx-auto flex items-end gap-2.5 bg-white dark:bg-[#1a1a1a] border border-[#d6d0c7] dark:border-[#252525] rounded-[13px] px-3.5 py-2.5 shadow-sm dark:shadow-none">
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
  );
}
