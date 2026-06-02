import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getTasks, getTaskRuns, triggerTaskRun } from "@/api/tasks";
import Topbar from "@/components/Topbar/Topbar";
import type { Task, TaskRun } from "@/types/task";

function statusBadge(status: TaskRun["status"]) {
  const map: Record<string, string> = {
    success: "bg-green-50 dark:bg-[#0d2010] text-green-700 dark:text-green-400",
    failed: "bg-red-50 dark:bg-[#200d0d] text-red-600 dark:text-red-400",
    running: "bg-blue-50 dark:bg-[#0d1020] text-blue-600 dark:text-blue-400",
    pending: "bg-[#f1f5f9] dark:bg-[#1a1a1a] text-[#94a3b8]",
  };
  const label: Record<string, string> = {
    success: "成功", failed: "失败", running: "运行中", pending: "等待中"
  };
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 ${map[status]}`}>
      {label[status]}
    </span>
  );
}

function formatTs(ms: number) {
  return new Date(ms).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function TaskRunsPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<Task | null>(null);
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!taskId) return;
    getTasks().then((ts) => setTask(ts.find((t) => t.id === taskId) ?? null));
    getTaskRuns(taskId).then(setRuns);
  }, [taskId]);

  useEffect(() => {
    if (!taskId) return;
    const hasRunning = runs.some((r) => r.status === "running" || r.status === "pending");
    if (hasRunning && !pollRef.current) {
      pollRef.current = setInterval(() => {
        getTaskRuns(taskId).then(setRuns);
      }, 3000);
    } else if (!hasRunning && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [runs, taskId]);

  const trigger = async () => {
    if (!taskId) return;
    setTriggering(true);
    try {
      const run = await triggerTaskRun(taskId);
      setRuns((prev) => [run, ...prev]);
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar
        title={task?.description ?? "任务详情"}
        action={
          <div className="flex gap-2">
            <button
              onClick={() => navigate("/tasks")}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555]"
            >
              ← 返回
            </button>
            <button
              onClick={trigger}
              disabled={triggering}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-[#0f0f0f] dark:bg-[#e8e8e8] text-white dark:text-[#0f0f0f] disabled:opacity-50"
            >
              {triggering ? "触发中..." : "立即触发"}
            </button>
          </div>
        }
      />
      <div className="flex-1 overflow-y-auto">
        {task && (
          <div className="max-w-[740px] mx-auto px-6 pt-4 pb-2">
            <p className="text-[11px] text-[#aaa]">cron: {task.cron}</p>
          </div>
        )}
        {runs.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-[#aaa] text-sm">
            暂无运行记录
          </div>
        ) : (
          <div className="max-w-[740px] mx-auto px-6 py-3 flex flex-col gap-2">
            {runs.map((run) => (
              <div
                key={run.id}
                className="bg-white dark:bg-[#1a1a1a] border border-[#e0dcd4] dark:border-[#202020] rounded-xl overflow-hidden"
              >
                <div
                  className="flex items-center gap-3 px-3.5 py-3 cursor-pointer"
                  onClick={() => setExpanded(expanded === run.id ? null : run.id)}
                >
                  {statusBadge(run.status)}
                  <span className="text-[11px] text-[#aaa] flex-1">{formatTs(run.started_at)}</span>
                  {run.output && (
                    <span className="text-[11px] text-[#555] truncate max-w-[200px]">
                      {run.output.slice(0, 60)}…
                    </span>
                  )}
                  <span className="text-[10px] text-[#aaa]">{expanded === run.id ? "▲" : "▼"}</span>
                </div>
                {expanded === run.id && (
                  <div className="px-3.5 pb-4 border-t border-[#f0ece4] dark:border-[#202020]">
                    {run.error ? (
                      <pre className="text-[11px] text-red-500 mt-3 whitespace-pre-wrap">{run.error}</pre>
                    ) : (
                      <pre className="text-[11.5px] text-[#333] dark:text-[#ccc] mt-3 whitespace-pre-wrap font-sans leading-relaxed">
                        {run.output || "（无输出）"}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
