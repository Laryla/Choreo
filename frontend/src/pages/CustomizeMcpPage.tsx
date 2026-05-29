// frontend/src/pages/CustomizeMcpPage.tsx
export default function CustomizeMcpPage() {
  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      {/* Content header */}
      <div className="px-7 pt-6 pb-4 border-b border-[#ddd9d0] dark:border-[#202020]">
        <h1 className="text-[17px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] mb-1">MCP 连接器</h1>
        <p className="text-[12px] text-[#999] dark:text-[#555]">允许 AI 助手连接外部工具和数据源</p>
      </div>

      {/* Placeholder */}
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-8">
        <div className="text-5xl opacity-20">🔌</div>
        <div className="text-[15px] font-medium text-[#aaa] dark:text-[#444]">MCP 连接器即将推出</div>
        <div className="text-[12px] text-[#bbb] dark:text-[#333] max-w-xs leading-relaxed">
          MCP（Model Context Protocol）让 AI 助手能够安全地连接数据库、API 和本地工具。
        </div>
      </div>
    </div>
  );
}
