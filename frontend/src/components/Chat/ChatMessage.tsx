import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import type { Message, ToolCall } from "@/store/chatStore";

// ── Tool type registry ────────────────────────────────────────────────────────

interface ToolType {
  label: string;
  bar: string;        // left border color
  badge: string;      // badge bg
  badgeText: string;  // badge text
  cardBg: string;
  cardBorder: string;
  resultBg: string;
  resultBorder: string;
  icon: string;
}

const TOOL_TYPES: Record<string, ToolType> = {
  read: {
    label: "Read",
    bar: "bg-blue-500",
    badge: "bg-blue-100 dark:bg-blue-950",
    badgeText: "text-blue-700 dark:text-blue-300",
    cardBg: "bg-[#f8faff] dark:bg-[#0c111f]",
    cardBorder: "border-blue-100 dark:border-blue-900/50",
    resultBg: "bg-[#f0f7ff] dark:bg-[#0a1525]",
    resultBorder: "border-blue-200 dark:border-blue-900",
    icon: "📄",
  },
  edit: {
    label: "Edit",
    bar: "bg-amber-500",
    badge: "bg-amber-100 dark:bg-amber-950",
    badgeText: "text-amber-700 dark:text-amber-400",
    cardBg: "bg-[#fffbf0] dark:bg-[#1a1400]",
    cardBorder: "border-amber-100 dark:border-amber-900/50",
    resultBg: "bg-[#fffbf0] dark:bg-[#1a1400]",
    resultBorder: "border-amber-200 dark:border-amber-900",
    icon: "✏️",
  },
  exec: {
    label: "Exec",
    bar: "bg-red-500",
    badge: "bg-red-100 dark:bg-red-950",
    badgeText: "text-red-700 dark:text-red-400",
    cardBg: "bg-[#fff8f8] dark:bg-[#1a0a0a]",
    cardBorder: "border-red-100 dark:border-red-900/50",
    resultBg: "bg-[#0f1117] dark:bg-[#0f1117]",
    resultBorder: "border-red-900/30 dark:border-red-900/30",
    icon: "⚡",
  },
  search: {
    label: "Search",
    bar: "bg-purple-500",
    badge: "bg-purple-100 dark:bg-purple-950",
    badgeText: "text-purple-700 dark:text-purple-300",
    cardBg: "bg-[#faf8ff] dark:bg-[#110f1f]",
    cardBorder: "border-purple-100 dark:border-purple-900/50",
    resultBg: "bg-[#f5f0ff] dark:bg-[#0e0b1a]",
    resultBorder: "border-purple-200 dark:border-purple-900",
    icon: "🔍",
  },
  notify: {
    label: "Notify",
    bar: "bg-emerald-500",
    badge: "bg-emerald-100 dark:bg-emerald-950",
    badgeText: "text-emerald-700 dark:text-emerald-300",
    cardBg: "bg-[#f0fdf8] dark:bg-[#071a10]",
    cardBorder: "border-emerald-100 dark:border-emerald-900/50",
    resultBg: "bg-[#f0fdf4] dark:bg-[#071a10]",
    resultBorder: "border-emerald-200 dark:border-emerald-900",
    icon: "🔔",
  },
};

const TOOL_CATEGORY: Record<string, keyof typeof TOOL_TYPES> = {
  read_file: "read",
  read_git_log: "read",
  skill_view: "read",
  write_file: "edit",
  edit_file: "edit",
  bash: "exec",
  grep: "search",
  list_dir: "search",
  send_notification: "notify",
};

function getToolType(name: string): ToolType {
  const key = TOOL_CATEGORY[name] ?? "read";
  return TOOL_TYPES[key];
}

// ── Diff view (for edit_file / write_file) ────────────────────────────────────

function DiffView({ args, path }: { args: Record<string, unknown>; path: string }) {
  const oldStr = String(args.old_string ?? "");
  const newStr = String(args.new_string ?? args.content ?? "");
  const oldLines = oldStr ? oldStr.split("\n") : [];
  const newLines = newStr ? newStr.split("\n") : [];

  return (
    <div className="font-mono text-[11px] leading-[1.6]">
      {/* File path header */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-[#f5f2eb] dark:bg-[#1a1400] border-b border-amber-100 dark:border-amber-900/40 text-[#666] dark:text-[#888]">
        <span className="text-amber-500">@@</span>
        <span>{path}</span>
      </div>

      <div className="overflow-x-auto max-h-48">
        {/* Deleted lines */}
        {oldLines.map((line, i) => (
          <div key={`-${i}`} className="flex items-start gap-2 px-3 py-0.5 bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-400">
            <span className="flex-shrink-0 w-3 select-none opacity-60">-</span>
            <span className="whitespace-pre break-all">{line}</span>
          </div>
        ))}
        {/* Added lines */}
        {newLines.map((line, i) => (
          <div key={`+${i}`} className="flex items-start gap-2 px-3 py-0.5 bg-green-50 dark:bg-green-950/40 text-green-700 dark:text-green-400">
            <span className="flex-shrink-0 w-3 select-none opacity-60">+</span>
            <span className="whitespace-pre break-all">{line}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tool call card ────────────────────────────────────────────────────────────

function getArgsSummary(name: string, args: Record<string, unknown>): string {
  const p = (args.path ?? args.file_path ?? args.skill_id ?? "") as string;
  const cmd = (args.command ?? "") as string;
  const pattern = (args.pattern ?? args.query ?? "") as string;

  if (p) return p;
  if (cmd) return cmd.slice(0, 60) + (cmd.length > 60 ? "…" : "");
  if (pattern) return `"${String(pattern).slice(0, 40)}…"`;
  const first = Object.values(args)[0];
  return first != null ? String(first).slice(0, 60) : "";
}

function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const [open, setOpen] = useState(false);
  const type = getToolType(toolCall.name);
  const isDiff = toolCall.name === "edit_file" || toolCall.name === "write_file";
  const path = String(toolCall.args.path ?? toolCall.args.file_path ?? "");
  const summary = getArgsSummary(toolCall.name, toolCall.args);

  return (
    <div className={`mb-1.5 rounded-xl border ${type.cardBorder} ${type.cardBg} overflow-hidden`}>
      {/* Header row */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2.5 w-full px-0 py-0 text-left group"
      >
        {/* Colored left bar */}
        <div className={`w-[3px] self-stretch ${type.bar} flex-shrink-0 rounded-l-xl`} />

        <div className="flex items-center gap-2 flex-1 min-w-0 py-2.5 pr-3">
          {/* Type badge */}
          <span className={`text-[9.5px] font-bold px-1.5 py-0.5 rounded-md flex-shrink-0 ${type.badge} ${type.badgeText} uppercase tracking-wide`}>
            {type.label}
          </span>

          {/* Tool name */}
          <span className="font-mono text-[11.5px] font-semibold text-[#1e293b] dark:text-[#d0d0d0] flex-shrink-0">
            {toolCall.name}
          </span>

          {/* Args summary */}
          {!open && summary && (
            <span className="text-[11px] text-[#999] dark:text-[#555] truncate">{summary}</span>
          )}

          {/* Chevron */}
          <svg
            className={`w-3 h-3 text-[#bbb] ml-auto flex-shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"
          >
            <path d="M4 2l4 4-4 4" />
          </svg>
        </div>
      </button>

      {/* Expanded body */}
      {open && (
        <div className="border-t border-inherit">
          {isDiff ? (
            <DiffView args={toolCall.args} path={path} />
          ) : (
            <pre className="px-4 py-2.5 text-[11px] font-mono text-[#555] dark:text-[#888] leading-relaxed whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
              {JSON.stringify(toolCall.args, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tool result card ──────────────────────────────────────────────────────────

function ToolResultCard({ message }: { message: Message }) {
  const [open, setOpen] = useState(false);
  const type = getToolType(message.tool_name ?? "");
  const lines = (message.content ?? "").split("\n");
  const isExec = TOOL_CATEGORY[message.tool_name ?? ""] === "exec";

  return (
    <div className={`mb-1.5 rounded-xl border ${type.resultBorder} overflow-hidden text-[11.5px]`}>
      {/* Header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-0 w-full text-left"
      >
        <div className={`w-[3px] self-stretch ${type.bar} flex-shrink-0 rounded-l-xl`} />

        <div className={`flex items-center gap-2 flex-1 min-w-0 px-3 py-2 ${type.resultBg}`}>
          {/* Status dot */}
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${type.bar}`} />
          <span className={`font-mono font-semibold flex-shrink-0 ${type.badgeText}`}>
            {message.tool_name}
          </span>
          <span className="text-[10.5px] text-[#bbb] dark:text-[#444] flex-shrink-0">
            {lines.length} 行
          </span>

          {/* Preview */}
          {!open && (
            <span className="text-[11px] text-[#999] dark:text-[#555] truncate flex-1">
              {lines[0]?.slice(0, 60)}
            </span>
          )}

          <svg
            className={`w-3 h-3 text-[#bbb] ml-auto flex-shrink-0 transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"
          >
            <path d="M4 2l4 4-4 4" />
          </svg>
        </div>
      </button>

      {/* Content */}
      {open && (
        <pre className={`px-4 py-3 text-[11px] font-mono leading-relaxed whitespace-pre-wrap break-all max-h-56 overflow-y-auto
          ${isExec
            ? "bg-[#0f1117] text-[#c8c8c8]"
            : `${type.resultBg} text-[#444] dark:text-[#aaa]`}`}>
          {message.content || "（无输出）"}
        </pre>
      )}
    </div>
  );
}

// ── Thinking block ────────────────────────────────────────────────────────────

function ThinkingBlock({ content, streaming }: { content: string; streaming?: boolean }) {
  const [open, setOpen] = useState(streaming ?? false);
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-[11px] text-[#999] dark:text-[#555] hover:text-[#666] dark:hover:text-[#888] transition-colors"
      >
        <svg className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`}
          viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 2l4 4-4 4" />
        </svg>
        思考过程
        {streaming && <span className="inline-block w-1 h-3 bg-[#bbb] dark:bg-[#444] ml-0.5 animate-pulse align-middle" />}
      </button>
      {open && (
        <div className="mt-1.5 pl-3 border-l-2 border-[#e2e8f0] dark:border-[#2a2a2a] text-[11px] text-[#888] dark:text-[#555] leading-relaxed whitespace-pre-wrap break-words max-w-full">
          {content}
        </div>
      )}
    </div>
  );
}

// ── Main ChatMessage ──────────────────────────────────────────────────────────

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
      <div className="flex justify-center my-0.5">
        <div className="text-[10.5px] text-[#bbb] dark:text-[#444] italic">{message.content}</div>
      </div>
    );
  }

  if (message.role === "tool") {
    return (
      <div className="flex gap-2.5 items-start">
        <div className="w-[25px] flex-shrink-0" />
        <div className="flex-1 min-w-0 max-w-[84%]">
          <ToolResultCard message={message} />
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="flex gap-2.5 items-start">
      <div className="w-[25px] h-[25px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">
        🎼
      </div>
      <div className="flex-1 min-w-0 max-w-[84%]">
        {message.thinking && <ThinkingBlock content={message.thinking} />}

        {/* Tool calls */}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mb-2">
            {message.tool_calls.map((tc) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Text response */}
        {message.content && (
          <div className="prose prose-sm dark:prose-invert text-[12.5px] leading-[1.7] text-[#1a1a1a] dark:text-[#c8c8c8]">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
