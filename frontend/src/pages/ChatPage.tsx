import { useRef, useEffect } from "react";
import { ChatProvider, useChatStore } from "@/store/chatStore";
import { ReviewProvider } from "@/store/reviewStore";
import ChatMessage from "@/components/Chat/ChatMessage";
import ChatInput from "@/components/Chat/ChatInput";
import ReviewPanel from "@/components/ReviewPanel/ReviewPanel";
import Topbar from "@/components/Topbar/Topbar";
import { useChat } from "@/hooks/useChat";
import { useReviewStore } from "@/store/reviewStore";

function ChatInner() {
  const { messages, streamingContent, streamingThinking } = useChatStore();
  const { sendMessage, streaming } = useChat();
  const { current: reviewRequest } = useReviewStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title={messages.length > 0 ? "当前对话" : "新对话"} />

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[740px] mx-auto px-6 py-5 flex flex-col gap-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 text-[#bbb] dark:text-[#333] text-sm gap-2">
              <span className="text-4xl">🎼</span>
              <span>告诉我你想自动化什么开发杂活</span>
            </div>
          )}
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          {(streamingThinking || streamingContent) && (
            <div className="flex gap-2.5 items-start">
              <div className="w-[25px] h-[25px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">
                🎼
              </div>
              <div className="max-w-[80%]">
                {streamingThinking && (
                  <div className="mb-2">
                    <div className="flex items-center gap-1.5 text-[11px] text-[#999] dark:text-[#555] mb-1">
                      <svg className="w-3 h-3 rotate-90" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 2l4 4-4 4" />
                      </svg>
                      思考过程
                      <span className="inline-block w-1 h-3 bg-[#bbb] dark:bg-[#444] animate-pulse" />
                    </div>
                    <div className="pl-3 border-l-2 border-[#e2e8f0] dark:border-[#2a2a2a] text-[11px] text-[#888] dark:text-[#555] leading-relaxed whitespace-pre-wrap break-words">
                      {streamingThinking}
                    </div>
                  </div>
                )}
                {streamingContent && (
                  <div className="text-[12.5px] leading-[1.7] text-[#1a1a1a] dark:text-[#c8c8c8] whitespace-pre-wrap">
                    {streamingContent}
                    <span className="inline-block w-0.5 h-4 bg-[#aaa] ml-0.5 animate-pulse align-middle" />
                  </div>
                )}
                {streamingThinking && !streamingContent && (
                  <span className="inline-block w-0.5 h-4 bg-[#aaa] animate-pulse" />
                )}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {reviewRequest && <ReviewPanel />}

      <div className="border-t border-[#ddd9d0] dark:border-[#202020] bg-[#f0ede6] dark:bg-[#141414]">
        <ChatInput onSend={sendMessage} disabled={streaming || !!reviewRequest} />
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <ChatProvider>
      <ReviewProvider>
        <ChatInner />
      </ReviewProvider>
    </ChatProvider>
  );
}
