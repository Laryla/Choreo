import { useState } from "react";
import { createTask } from "@/api/tasks";
import type { Task } from "@/types/task";

const CRON_PRESETS = [
  { label: "每天早上 9 点", value: "0 9 * * *" },
  { label: "每周一早上 9 点", value: "0 9 * * 1" },
  { label: "每小时", value: "0 * * * *" },
];

interface Props {
  onClose: () => void;
  onCreated: (task: Task) => void;
}

export default function CreateTaskModal({ onClose, onCreated }: Props) {
  const [form, setForm] = useState({
    description: "",
    cron: "",
    prompt: "",
    webhook: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async () => {
    if (!form.description || !form.cron || !form.prompt) {
      setError("名称、Cron 和指令为必填项");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const notify_config = form.webhook
        ? { channels: [{ type: "feishu", webhook: form.webhook }] }
        : {};
      const task = await createTask({
        description: form.description,
        cron: form.cron,
        prompt: form.prompt,
        notify_config,
      });
      onCreated(task);
    } catch {
      setError("创建失败，请检查输入");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-[#1a1a1a] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8]">新建定时任务</h2>
          <button onClick={onClose} className="text-[#aaa] hover:text-[#555] text-lg leading-none">×</button>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">任务名称 *</label>
            <input
              value={form.description}
              onChange={set("description")}
              placeholder="如：每周 GitHub 热门项目追踪"
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">执行频率 *</label>
            <select
              value={CRON_PRESETS.find(p => p.value === form.cron)?.value || "__custom"}
              onChange={(e) => {
                if (e.target.value !== "__custom") setForm(f => ({ ...f, cron: e.target.value }));
              }}
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-white dark:bg-[#1a1a1a] outline-none"
            >
              <option value="__custom">自定义 cron...</option>
              {CRON_PRESETS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
            <input
              value={form.cron}
              onChange={set("cron")}
              placeholder="0 9 * * 1"
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none font-mono"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">Agent 指令 *</label>
            <textarea
              value={form.prompt}
              onChange={set("prompt")}
              rows={4}
              placeholder="搜索本周 GitHub Stars 增长最快的 10 个项目，按增量排序，给出简短描述..."
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none resize-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">飞书 Webhook（可选）</label>
            <input
              value={form.webhook}
              onChange={set("webhook")}
              placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none"
            />
          </div>
        </div>

        {error && <p className="text-[11px] text-red-500">{error}</p>}

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onClose}
            className="text-[12px] px-3 py-1.5 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] text-[#555]"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={loading}
            className="text-[12px] px-4 py-1.5 rounded-lg bg-[#0f0f0f] dark:bg-[#e8e8e8] text-white dark:text-[#0f0f0f] disabled:opacity-50"
          >
            {loading ? "创建中..." : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
