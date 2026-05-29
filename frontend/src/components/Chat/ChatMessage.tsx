import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import type { Message } from "@/store/chatStore";

function ThinkingBlock({ content, streaming }: { content: string; streaming?: boolean }) {
  const [open, setOpen] = useState(streaming ?? false);
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-[11px] text-[#999] dark:text-[#555] hover:text-[#666] dark:hover:text-[#888] transition-colors"
      >
        <svg
          className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`}
          viewBox="0 0 12 12" fill="none" stroke="currentColor"
          strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
        >
          <path d="M4 2l4 4-4 4" />
        </svg>
        思考过程
        {streaming && (
          <span className="inline-block w-1 h-3 bg-[#bbb] dark:bg-[#444] ml-0.5 animate-pulse align-middle" />
        )}
      </button>
      {open && (
        <div className="mt-1.5 pl-3 border-l-2 border-[#e2e8f0] dark:border-[#2a2a2a] text-[11px] text-[#888] dark:text-[#555] leading-relaxed whitespace-pre-wrap break-words max-w-full">
          {content}
        </div>
      )}
    </div>
  );
}

interface Props { message: Message }

export default function ChatMessage({ message }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[68%] px-3.5 py-2.5 rounded-2xl rounded-br-[3px] bg-[#1e293b] dark:bg-[#2a2a2a] text-white dark:text-[#e8e8e8] text-[12.5px] leading-relaxed whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "system") {
    return (
      <div className="flex justify-center">
        <div className="text-[11px] text-[#aaa] dark:text-[#444] italic">{message.content}</div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5 items-start">
      <div className="w-[25px] h-[25px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">
        🎼
      </div>
      <div className="max-w-[80%]">
        {message.thinking && <ThinkingBlock content={message.thinking} />}
        <div className="prose prose-sm dark:prose-invert text-[12.5px] leading-[1.7] text-[#1a1a1a] dark:text-[#c8c8c8]">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
