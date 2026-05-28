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
  const { messages, streamingContent } = useChatStore();
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
          {streamingContent && (
            <div className="flex gap-2.5 items-start">
              <div className="w-[25px] h-[25px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">
                🎼
              </div>
              <div className="text-[12.5px] leading-[1.7] text-[#1a1a1a] dark:text-[#c8c8c8] max-w-[80%]">
                {streamingContent}
                <span className="inline-block w-0.5 h-4 bg-[#aaa] ml-0.5 animate-pulse align-middle" />
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
