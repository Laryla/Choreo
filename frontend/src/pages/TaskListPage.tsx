import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTasks, deleteTask, patchTask } from "@/api/tasks";
import Topbar from "@/components/Topbar/Topbar";
import CreateTaskModal from "@/components/Tasks/CreateTaskModal";
import type { Task } from "@/types/task";

export default function TaskListPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    getTasks().then(setTasks).catch(console.error);
  }, []);

  const toggleStatus = async (task: Task) => {
    const updated = await patchTask(task.id, {
      status: task.status === "active" ? "paused" : "active",
    });
    setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
  };

  const remove = async (id: string) => {
    await deleteTask(id);
    setTasks((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar
        title="定时任务"
        action={
          <button
            onClick={() => setShowCreate(true)}
            className="text-[11px] px-2.5 py-1 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555] dark:text-[#555] hover:opacity-80"
          >
            + 新建任务
          </button>
        }
      />
      <div className="flex-1 overflow-y-auto">
        {tasks.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-[#aaa] dark:text-[#333] text-sm">
            暂无定时任务，通过对话让 Choreo 帮你创建
          </div>
        ) : (
          <div className="max-w-[740px] mx-auto px-6 py-5 flex flex-col gap-2.5">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center gap-3 bg-white dark:bg-[#1a1a1a] border border-[#e0dcd4] dark:border-[#202020] rounded-xl px-3.5 py-3"
              >
                <div
                  className="flex-1 min-w-0 cursor-pointer"
                  onClick={() => navigate(`/tasks/${task.id}`)}
                >
                  <p className="text-[12.5px] font-medium text-[#0f0f0f] dark:text-[#e8e8e8] truncate hover:underline">
                    {task.description}
                  </p>
                  <p className="text-[10.5px] text-[#aaa] dark:text-[#444] mt-0.5 truncate">
                    cron: {task.cron}
                  </p>
                </div>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 ${
                    task.status === "active"
                      ? "bg-green-50 dark:bg-[#0d2010] text-green-700 dark:text-green-400"
                      : "bg-[#f1f5f9] dark:bg-[#1a1a1a] text-[#94a3b8] dark:text-[#444]"
                  }`}
                >
                  {task.status === "active" ? "运行中" : "已暂停"}
                </span>
                <button
                  onClick={() => toggleStatus(task)}
                  className="text-[10.5px] text-[#64748b] dark:text-[#444] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8]"
                >
                  {task.status === "active" ? "暂停" : "恢复"}
                </button>
                <button
                  onClick={() => remove(task.id)}
                  className="text-[10.5px] text-red-400 dark:text-[#f87171] hover:text-red-600"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      {showCreate && (
        <CreateTaskModal
          onClose={() => setShowCreate(false)}
          onCreated={(task) => {
            setTasks((prev) => [task, ...prev]);
            setShowCreate(false);
          }}
        />
      )}
    </div>
  );
}
