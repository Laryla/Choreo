import { createContext, useContext, useState, useRef, ReactNode } from "react";

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  thinking?: string;
  tool_calls?: ToolCall[];   // assistant message 调用了工具
  tool_name?: string;        // tool result: 工具名
  tool_call_id?: string;     // tool result: 对应的调用 id
}

interface ChatState {
  messages: Message[];
  streamingContent: string;
  streamingThinking: string;
  addMessage: (msg: Omit<Message, "id">) => void;
  appendToken: (token: string) => void;
  appendThinking: (token: string) => void;
  finalizeToken: () => void;
  resetMessages: (msgs?: Omit<Message, "id">[]) => void;
}

const ChatContext = createContext<ChatState | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");

  const contentRef = useRef("");
  const thinkingRef = useRef("");

  const addMessage = (msg: Omit<Message, "id">) => {
    setMessages((prev) => [...prev, { ...msg, id: crypto.randomUUID() }]);
  };

  const appendToken = (token: string) => {
    contentRef.current += token;
    setStreamingContent(contentRef.current);
  };

  const appendThinking = (token: string) => {
    thinkingRef.current += token;
    setStreamingThinking(thinkingRef.current);
  };

  const resetMessages = (msgs?: Omit<Message, "id">[]) => {
    setMessages((msgs ?? []).map((m) => ({ ...m, id: crypto.randomUUID() })));
    contentRef.current = "";
    thinkingRef.current = "";
    setStreamingContent("");
    setStreamingThinking("");
  };

  const finalizeToken = () => {
    const content = contentRef.current;
    const thinking = thinkingRef.current;

    if (content) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content,
          thinking: thinking || undefined,
        },
      ]);
    }

    contentRef.current = "";
    thinkingRef.current = "";
    setStreamingContent("");
    setStreamingThinking("");
  };

  return (
    <ChatContext.Provider
      value={{
        messages,
        streamingContent,
        streamingThinking,
        addMessage,
        appendToken,
        appendThinking,
        finalizeToken,
        resetMessages,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChatStore() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatStore must be inside ChatProvider");
  return ctx;
}
