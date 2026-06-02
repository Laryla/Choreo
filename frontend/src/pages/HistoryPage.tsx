import { useState } from "react";
import { useNavigate } from "react-router-dom";
import useSWR from "swr";
import Topbar from "@/components/Topbar/Topbar";
import { getHistory, type HistoryItem } from "@/api/history";

const STATUS_LABEL: Record<string, { text: string; color: string }> = {
  idle:    { text: "空闲", color: "text-[#aaa] dark:text-[#555]" },
  running: { text: "运行中", color: "text-green-500" },
  error:   { text: "出错", color: "text-red-400" },
};

function formatTime(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay} 天前`;
  return d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const SIZE = 20;

  const { data, isLoading } = useSWR(
    ["history", page],
    () => getHistory(page, SIZE),
    { revalidateOnFocus: false },
  );

  const totalPages = data ? Math.ceil(data.total / SIZE) : 1;

  const openThread = (item: HistoryItem) => {
    navigate(`/chat/${item.thread_id}`);
  };

  return (
    <div className="flex flex-col h-full bg-[#faf9f7] dark:bg-[#0a0a0a]">
      <Topbar title="历史记录" />

      <div className="flex-1 overflow-auto">
        <div className="max-w-[760px] mx-auto px-6 py-5">

          {isLoading && (
            <div className="py-16 text-center text-[12px] text-[#bbb] dark:text-[#333]">加载中…</div>
          )}

          {!isLoading && (!data?.items || data.items.length === 0) && (
            <div className="py-16 text-center">
              <p className="text-[13px] text-[#bbb] dark:text-[#333]">暂无对话历史</p>
              <p className="text-[11px] text-[#ccc] dark:text-[#2a2a2a] mt-1">发起一次对话后会在这里显示</p>
            </div>
          )}

          {!isLoading && data && data.items.length > 0 && (
            <>
              <div className="border border-[#e8e4dc] dark:border-[#1a1a1a] rounded-xl overflow-hidden bg-white dark:bg-[#0d0d0d]">
                {data.items.map((item, i) => {
                  const st = STATUS_LABEL[item.status] ?? STATUS_LABEL.idle;
                  return (
                    <div
                      key={item.thread_id}
                      onClick={() => openThread(item)}
                      className={`flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-[#faf8f5] dark:hover:bg-[#111] transition-colors ${
                        i !== 0 ? "border-t border-[#f0ede6] dark:border-[#141414]" : ""
                      }`}
                    >
                      {/* Icon */}
                      <div className="w-7 h-7 rounded-lg bg-[#f0ede6] dark:bg-[#1a1a1a] flex items-center justify-center flex-shrink-0">
                        <svg className="w-3.5 h-3.5 text-[#bbb] dark:text-[#444]" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                          <path d="M2 3h12M2 6h8M2 9h10M2 12h6" />
                        </svg>
                      </div>

                      {/* Title + thread id */}
                      <div className="flex-1 min-w-0">
                        <p className="text-[13px] text-[#1a1a1a] dark:text-[#e0e0e0] truncate">
                          {item.title}
                        </p>
                        <p className="text-[10.5px] text-[#bbb] dark:text-[#444] font-mono mt-0.5">
                          {item.thread_id.slice(0, 8)}…
                        </p>
                      </div>

                      {/* Status */}
                      <span className={`text-[11px] ${st.color} flex-shrink-0`}>
                        {st.text}
                      </span>

                      {/* Time */}
                      <span className="text-[11px] text-[#bbb] dark:text-[#444] flex-shrink-0 w-16 text-right">
                        {formatTime(item.created_at)}
                      </span>

                      {/* Arrow */}
                      <svg className="w-3.5 h-3.5 text-[#ccc] dark:text-[#333] flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <path d="M6 4l4 4-4 4" />
                      </svg>
                    </div>
                  );
                })}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 mt-5">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-3 py-1.5 text-[11px] rounded-lg border border-[#e8e4dc] dark:border-[#1a1a1a] text-[#666] dark:text-[#666] disabled:opacity-30 hover:bg-[#f0ede6] dark:hover:bg-[#1a1a1a] transition-colors"
                  >
                    上一页
                  </button>
                  <span className="text-[11px] text-[#aaa] dark:text-[#555]">
                    {page} / {totalPages}
                  </span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-3 py-1.5 text-[11px] rounded-lg border border-[#e8e4dc] dark:border-[#1a1a1a] text-[#666] dark:text-[#666] disabled:opacity-30 hover:bg-[#f0ede6] dark:hover:bg-[#1a1a1a] transition-colors"
                  >
                    下一页
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
