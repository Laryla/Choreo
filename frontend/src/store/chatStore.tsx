import { createContext, useContext, useState, useRef, useCallback, ReactNode } from "react";

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface SubAgentStep {
  tool_name?: string
  tool_args?: Record<string, unknown>
  content?: string
  event_type: 'start' | 'tool_call' | 'tool_result' | 'done'
}

export interface TaskSteps {
  task_id: string
  subagent_type: string
  description?: string
  status: 'running' | 'done'
  steps: SubAgentStep[]
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  thinking?: string;
  tool_calls?: ToolCall[];   // assistant message 调用了工具
  tool_name?: string;        // tool result: 工具名
  tool_call_id?: string;     // tool result: 对应的调用 id
  taskSteps?: Record<string, TaskSteps>   // task_id → TaskSteps
}

interface ChatState {
  messages: Message[];
  streamingContent: string;
  streamingThinking: string;
  streamingMsgId: string | null;
  addMessage: (msg: Omit<Message, "id">) => void;
  appendToken: (token: string) => void;
  appendThinking: (token: string) => void;
  finalizeToken: () => void;
  resetMessages: (msgs?: Omit<Message, "id">[]) => void;
  upsertTaskStep: (messageId: string, taskId: string, update: Partial<TaskSteps> & { step?: SubAgentStep }) => void;
}

const ChatContext = createContext<ChatState | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingThinking, setStreamingThinking] = useState("");
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null);

  const contentRef = useRef("");
  const thinkingRef = useRef("");

  const addMessage = (msg: Omit<Message, "id">) => {
    const newMsg = { ...msg, id: crypto.randomUUID() };
    setMessages((prev) => [...prev, newMsg]);
    if (msg.role === "assistant") {
      setStreamingMsgId(newMsg.id);
    }
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
    setStreamingMsgId(null);
  };

  const finalizeToken = () => {
    const content = contentRef.current;
    const thinking = thinkingRef.current;

    if (content) {
      const newId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        {
          id: newId,
          role: "assistant",
          content,
          thinking: thinking || undefined,
        },
      ]);
      setStreamingMsgId(newId);
    }

    contentRef.current = "";
    thinkingRef.current = "";
    setStreamingContent("");
    setStreamingThinking("");
  };

  const upsertTaskStep = useCallback(
    (messageId: string, taskId: string, update: Partial<TaskSteps> & { step?: SubAgentStep }) => {
      setMessages(prev =>
        prev.map(msg => {
          if (msg.id !== messageId) return msg
          const existing = msg.taskSteps?.[taskId]
          const { step, ...rest } = update
          const updated: TaskSteps = {
            task_id: taskId,
            subagent_type: rest.subagent_type ?? existing?.subagent_type ?? '',
            description: rest.description ?? existing?.description,
            status: rest.status ?? existing?.status ?? 'running',
            steps: step ? [...(existing?.steps ?? []), step] : (existing?.steps ?? []),
          }
          return {
            ...msg,
            taskSteps: { ...(msg.taskSteps ?? {}), [taskId]: updated },
          }
        })
      )
    },
    []
  )

  return (
    <ChatContext.Provider
      value={{
        messages,
        streamingContent,
        streamingThinking,
        streamingMsgId,
        addMessage,
        appendToken,
        appendThinking,
        finalizeToken,
        resetMessages,
        upsertTaskStep,
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
