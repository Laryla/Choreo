import { createContext, useContext, useState, ReactNode } from "react";

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  streaming?: boolean;
}

interface ChatState {
  messages: Message[];
  streamingContent: string;
  addMessage: (msg: Omit<Message, "id">) => void;
  appendToken: (token: string) => void;
  finalizeToken: () => void;
}

const ChatContext = createContext<ChatState | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState("");

  const addMessage = (msg: Omit<Message, "id">) => {
    setMessages((prev) => [...prev, { ...msg, id: crypto.randomUUID() }]);
  };

  const appendToken = (token: string) => {
    setStreamingContent((prev) => prev + token);
  };

  const finalizeToken = () => {
    setStreamingContent((prev) => {
      if (prev) {
        setMessages((msgs) => [
          ...msgs,
          { id: crypto.randomUUID(), role: "assistant", content: prev },
        ]);
      }
      return "";
    });
  };

  return (
    <ChatContext.Provider value={{ messages, streamingContent, addMessage, appendToken, finalizeToken }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChatStore() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatStore must be inside ChatProvider");
  return ctx;
}
