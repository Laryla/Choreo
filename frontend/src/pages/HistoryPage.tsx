import Topbar from "@/components/Topbar/Topbar";

export default function HistoryPage() {
  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="历史记录" />
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-[#bbb] dark:text-[#333]">
          <div className="text-3xl mb-2">🕐</div>
          <p className="text-sm">暂无历史记录</p>
        </div>
      </div>
    </div>
  );
}
