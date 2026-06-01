import { useState, useRef, useEffect } from "react";
import type { CuratorLogLine } from "@/api/skills";
import { runCurator, getCuratorLog, getCuratorProgress } from "@/api/skills";

const LINE_STYLES: Record<CuratorLogLine["type"], string> = {
  phase:   "text-[#555] dark:text-[#aaa] font-semibold mt-4 first:mt-0",
  info:    "text-[#888] dark:text-[#666]",
  archive: "text-[#c0622a] dark:text-[#e07b54]",
  merge:   "text-[#2d8a2d] dark:text-[#4ec94e]",
  skip:    "text-[#aaa] dark:text-[#555]",
  llm:     "text-[#888] dark:text-[#666] italic",
  ok:      "text-[#888] dark:text-[#666] mt-1",
  done:    "text-[#1e293b] dark:text-[#e8e8e8] font-semibold mt-4",
  error:   "text-red-500 dark:text-red-400",
};

export default function CustomizeCuratorPage() {
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<CuratorLogLine[]>([]);
  const [lastRunTs, setLastRunTs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startPolling = (deadline: number) => {
    const poll = async () => {
      if (Date.now() > deadline) {
        localStorage.removeItem("curatorTriggeredAt");
        localStorage.removeItem("curatorDeadline");
        setError("超时未完成，请稍后查看后端日志");
        setRunning(false);
        return;
      }
      try {
        const progress = await getCuratorProgress();
        if (progress.lines.length > 0) {
          setLines(progress.lines);
        }
        if (!progress.running) {
          // 完成（无论 progress 文件是否还有内容）：从主日志加载最终结果
          localStorage.removeItem("curatorTriggeredAt");
          localStorage.removeItem("curatorDeadline");
          setRunning(false);
          getCuratorLog(1).then((entries) => {
            if (entries.length > 0) {
              const entry = entries[entries.length - 1];
              setLines(entry.lines ?? []);
              setLastRunTs(entry.ts);
            }
          }).catch(() => {});
          return;
        }
      } catch {}
      pollRef.current = setTimeout(poll, 1000);
    };
    pollRef.current = setTimeout(poll, 1000);
  };

  // Mount: always load last log first, then resume polling if mid-run
  useEffect(() => {
    // Always load the latest log to show something immediately
    getCuratorLog(1).then((entries) => {
      if (entries.length > 0) {
        const entry = entries[entries.length - 1];
        setLines(entry.lines ?? []);
        setLastRunTs(entry.ts);
      }
    }).catch(() => {});

    // Check if we left mid-run
    const savedTriggeredAt = localStorage.getItem("curatorTriggeredAt");
    const savedDeadline = localStorage.getItem("curatorDeadline");
    if (savedTriggeredAt && savedDeadline) {
      const deadline = parseInt(savedDeadline, 10);
      if (Date.now() < deadline) {
        setRunning(true);
        startPolling(deadline);
      } else {
        localStorage.removeItem("curatorTriggeredAt");
        localStorage.removeItem("curatorDeadline");
      }
    }
  }, []);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines]);

  const handleRun = async () => {
    if (running) return;
    setRunning(true);
    setError(null);
    setLines([{ type: "info", text: "正在启动整理任务…" }]);
    const triggeredAt = Math.floor(Date.now() / 1000);
    const deadline = Date.now() + 120_000;

    try {
      await runCurator();
    } catch {
      setError("启动失败，请检查后端日志");
      setRunning(false);
      return;
    }

    // 持久化，切换页面回来后可恢复轮询
    localStorage.setItem("curatorTriggeredAt", String(triggeredAt));
    localStorage.setItem("curatorDeadline", String(deadline));
    startPolling(deadline);
  };

  useEffect(() => {
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, []);

  const lastRunLabel = lastRunTs
    ? new Date(lastRunTs * 1000).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="h-full flex flex-col bg-[#f7f5f0] dark:bg-[#0f0f0f]">

      {/* 顶部操作栏 */}
      <div className="flex-shrink-0 px-8 pt-7 pb-5 border-b border-[#ede9e1] dark:border-[#1a1a1a] flex items-start justify-between">
        <div>
          <h2 className="text-[15px] font-semibold text-[#1e293b] dark:text-[#e8e8e8]">技能整理</h2>
          <p className="text-[12px] text-[#999] dark:text-[#555] mt-0.5">
            归档 30 天未使用的技能，合并重复技能。每 24 小时自动执行。
            {lastRunLabel && <span className="ml-2 text-[#bbb] dark:text-[#444]">上次：{lastRunLabel}</span>}
          </p>
        </div>
        <button
          onClick={handleRun}
          disabled={running}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] font-medium hover:bg-[#0f172a] disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
        >
          {running ? (
            <>
              <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              整理中…
            </>
          ) : "立即整理"}
        </button>
      </div>

      {/* 日志区 */}
      <div ref={logRef} className="flex-1 overflow-y-auto px-8 py-6">
        {lines.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-3 text-[#ccc] dark:text-[#333]">
            <span className="text-[32px]">✦</span>
            <p className="text-[13px]">点击「立即整理」开始，或等待自动执行</p>
          </div>
        ) : (
          <div className="font-mono text-[12px] space-y-0.5 max-w-[680px]">
            {lines
              .map((line, i) => (
                <div key={i} className={`leading-5 ${LINE_STYLES[line.type] ?? "text-[#aaa]"}`}>
                  {line.text}
                </div>
              ))}
          </div>
        )}

        {error && (
          <p className="mt-4 text-[12px] text-red-400">{error}</p>
        )}
      </div>
    </div>
  );
}
