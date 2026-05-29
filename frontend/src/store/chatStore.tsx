import { createContext, useContext, useState, ReactNode } from "react";

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  thinking?: string;   // 思考内容（可选）
  streaming?: boolean;
}

interface ChatState {
  messages: Message[];
  streamingContent: string;
  streamingThinking: string;   // 正在流式输出的思考内容
  addMessage: (msg: Omit<Message, "id">) => void;
  appendToken: (token: string) => void;
  appendThinking: (token: string) => void;
  finalizeToken: () => void;
}

const ChatContext = createContext<ChatState | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");

  const addMessage = (msg: Omit<Message, "id">) => {
    setMessages((prev) => [...prev, { ...msg, id: crypto.randomUUID() }]);
  };

  const appendToken = (token: string) => {
    setStreamingContent((prev) => prev + token);
  };

  const appendThinking = (token: string) => {
    setStreamingThinking((prev) => prev + token);
  };

  const finalizeToken = () => {
    setStreamingContent((prev) => {
      setStreamingThinking((thinking) => {
        if (prev) {
          setMessages((msgs) => [
            ...msgs,
            {
              id: crypto.randomUUID(),
              role: "assistant",
              content: prev,
              thinking: thinking || undefined,
            },
          ]);
        }
        return "";
      });
      return "";
    });
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
