import { useEffect, useState } from "react";
import { useReview } from "@/hooks/useReview";
import type { Decision } from "@/types/review";

// 工具图标映射
const TOOL_ICONS: Record<string, string> = {
  bash: "⬢",
  read_file: "◈",
  write_file: "◈",
  edit_file: "◈",
  list_dir: "◈",
  grep: "◉",
  send_notification: "◎",
};

const MCP_SERVER_ICONS: Record<string, string> = {
  github: "🐙", postgres: "🐘", filesystem: "🗂️",
  slack: "💬", notion: "📝", "brave-search": "🔍",
};

// 需要用代码块渲染的参数
const CODE_KEYS = new Set(["command", "content", "pattern", "old_string", "new_string"]);

export default function ReviewPanel() {
  const { current, submitDecision } = useReview();
  const [loading, setLoading] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [collected, setCollected] = useState<Decision[]>([]);

  // Reset step state whenever a new interrupt arrives
  useEffect(() => {
    setStepIndex(0);
    setCollected([]);
  }, [current]);

  const total = current?.action_requests.length ?? 0;
  const action = current?.action_requests[stepIndex];
  const config = current?.review_configs[stepIndex] ?? current?.review_configs[0];
  const allowed = config?.allowed_decisions ?? ["approve", "reject"];
  const args = action?.args ?? {};
  const isMcpTool = action?.name?.includes(" · ");
  const [mcpServer, mcpTool] = isMcpTool
    ? action!.name.split(" · ", 2)
    : ["", ""];
  const displayArgs = isMcpTool ? ((args as any).arguments ?? args) : args;
  const icon = isMcpTool
    ? (MCP_SERVER_ICONS[mcpServer] ?? "🔌")
    : (TOOL_ICONS[action?.name ?? ""] ?? "◆");

  const handle = async (type: Decision["type"]) => {
    const next = [...collected, { type }];
    if (stepIndex + 1 < total) {
      // More tool calls to review — advance to next
      setCollected(next);
      setStepIndex(stepIndex + 1);
    } else {
      // All decisions collected — submit together
      setLoading(true);
      await submitDecision({ decisions: next });
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!current) return;
    const onKey = (e: KeyboardEvent) => {
      if (loading) return;
      if (e.key === "y" && allowed.includes("approve")) handle("approve");
      if (e.key === "n" && allowed.includes("reject")) handle("reject");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, loading, allowed, stepIndex, collected]);

  if (!current) return null;

  return (
    <div className="px-6 pb-3">
      <div className="max-w-[740px] mx-auto">
        <div className="rounded-lg overflow-hidden border border-[#2a2a2a] bg-[#0d0d0d] shadow-xl font-mono text-[12px]">

          {/* 顶栏 */}
          <div className="flex items-center gap-2 px-3 py-2 bg-[#161616] border-b border-[#2a2a2a]">
            <span className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
            <span className="ml-2 text-[11px] text-[#555]">choreo — tool confirmation</span>
            {total > 1 && (
              <span className="ml-auto text-[11px] text-[#444]">{stepIndex + 1} / {total}</span>
            )}
          </div>

          {/* 工具名行 */}
          <div className="flex items-center gap-2.5 px-4 pt-3 pb-2 border-b border-[#1a1a1a]">
            <span className="text-[#e2b714] text-[14px]">{icon}</span>
            {isMcpTool ? (
              <>
                <span className="text-[#e2b714] text-[13px] font-semibold">{mcpServer}</span>
                <span className="text-[#555] text-[13px] mx-1">·</span>
                <span className="text-[#e2b714] text-[13px] font-semibold">{mcpTool}</span>
              </>
            ) : (
              <span className="text-[#e2b714] text-[13px] font-semibold">{action?.name}</span>
            )}
            {action?.description && (
              <span className="text-[#444] text-[11px] ml-1">{action.description}</span>
            )}
          </div>

          {/* 参数列表 */}
          {Object.keys(displayArgs).length > 0 && (
            <div className="px-4 py-3 space-y-2.5 border-b border-[#1a1a1a]">
              {Object.entries(displayArgs).map(([key, val]) => {
                const strVal = typeof val === "string" ? val : JSON.stringify(val, null, 2);
                const isCode = CODE_KEYS.has(key);
                const isLong = strVal.length > 60 || strVal.includes("\n");

                return (
                  <div key={key}>
                    <div className="text-[#569cd6] text-[11px] mb-1">{key}</div>
                    {isCode ? (
                      <div className={`bg-[#111] border border-[#222] rounded px-3 py-2 text-[#ce9178] leading-5 ${isLong ? "whitespace-pre-wrap break-all" : "whitespace-nowrap overflow-x-auto"}`}>
                        {strVal}
                      </div>
                    ) : (
                      <div className="text-[#9cdcfe] pl-1">{strVal}</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* 确认行 */}
          <div className="flex items-center gap-3 px-4 py-2.5">
            <span className="text-[#555]">❯</span>
            <span className="text-[#666]">Allow this action?</span>
            <div className="flex gap-2 ml-auto">
              {allowed.includes("reject") && (
                <button
                  onClick={() => handle("reject")}
                  disabled={loading}
                  className="px-3 py-1 rounded text-[11px] bg-[#1a1a1a] border border-[#333] text-[#888] hover:border-[#555] hover:text-[#aaa] disabled:opacity-40 transition-colors"
                >
                  No <kbd className="ml-1 text-[10px] text-[#555]">n</kbd>
                </button>
              )}
              {allowed.includes("approve") && (
                <button
                  onClick={() => handle("approve")}
                  disabled={loading}
                  className="px-3 py-1 rounded text-[11px] bg-[#1a3a1a] border border-[#2d5a2d] text-[#4ec94e] hover:bg-[#1f4a1f] hover:border-[#3d7a3d] disabled:opacity-40 transition-colors"
                >
                  Yes <kbd className="ml-1 text-[10px] text-[#2d7a2d]">y</kbd>
                </button>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
