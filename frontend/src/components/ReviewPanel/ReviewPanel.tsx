import { useState } from "react";
import { useReview } from "@/hooks/useReview";
import type { Decision } from "@/types/review";

export default function ReviewPanel() {
  const { current, submitDecision } = useReview();
  const [loading, setLoading] = useState(false);

  if (!current) return null;

  const action = current.action_requests[0];
  const config = current.review_configs[0];
  const allowed = config?.allowed_decisions ?? ["approve", "reject"];

  const handle = async (type: Decision["type"]) => {
    setLoading(true);
    await submitDecision({ decisions: [{ type }] });
    setLoading(false);
  };

  return (
    <div className="max-w-[740px] mx-auto px-6 mb-3">
      <div className="rounded-xl p-3 bg-[#fefce8] dark:bg-[#1a1700] border border-[#fef08a] dark:border-[#2e2a00]">
        <div className="text-[11.5px] font-semibold text-[#713f12] dark:text-[#d4a017] mb-1.5 flex items-center gap-1.5">
          ⚠️ 需要确认：{action?.name}
        </div>
        {action?.description && (
          <p className="text-[10.5px] text-[#92400e] dark:text-[#a37a00] mb-1.5">{action.description}</p>
        )}
        <div className="font-mono text-[10.5px] bg-[#fef9c3] dark:bg-[#231e00] text-[#854d0e] dark:text-[#d4a017] px-2 py-1 rounded mb-2 inline-block">
          {JSON.stringify(action?.arguments)}
        </div>
        <div className="flex gap-2">
          {allowed.includes("approve") && (
            <button
              onClick={() => handle("approve")}
              disabled={loading}
              className="bg-green-600 text-white text-[11px] px-3 py-1 rounded-lg disabled:opacity-40 hover:bg-green-700"
            >
              ✓ 确认执行
            </button>
          )}
          {allowed.includes("reject") && (
            <button
              onClick={() => handle("reject")}
              disabled={loading}
              className="text-[11px] px-3 py-1 rounded-lg border border-[#fca5a5] dark:border-[#4a1515] text-red-600 dark:text-[#f87171] disabled:opacity-40"
            >
              ✕ 拒绝
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
