import type { Message } from "@/store/chatStore";

interface Props { message: Message }

export default function ChatMessage({ message }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[68%] px-3.5 py-2.5 rounded-2xl rounded-br-[3px] bg-[#1e293b] dark:bg-[#2a2a2a] text-white dark:text-[#e8e8e8] text-[12.5px] leading-relaxed whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "system") {
    return (
      <div className="flex justify-center">
        <div className="text-[11px] text-[#aaa] dark:text-[#444] italic">{message.content}</div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5 items-start">
      <div className="w-[25px] h-[25px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">
        🎼
      </div>
      <div className="text-[12.5px] leading-[1.7] text-[#1a1a1a] dark:text-[#c8c8c8] whitespace-pre-wrap break-words max-w-[80%]">
        {message.content}
      </div>
    </div>
  );
}
