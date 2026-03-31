export type MessageRole = "user" | "assistant" | "system";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  toolCalls?: { name: string; input: unknown }[];
}

export interface AskQuestion {
  question: string;
  header?: string;
  options?: { label: string; description?: string }[];
  multiSelect?: boolean;
}

export interface AskUserRequest {
  requestId: string;
  questions: AskQuestion[];
}

export interface Todo {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

// WebSocket incoming messages
export type WSMessage =
  | { type: "stream_delta"; text: string }
  | { type: "thinking_delta"; text: string }
  | { type: "assistant"; text: string; toolCalls: { name: string; input: unknown }[] }
  | { type: "tool_use"; name: string; input?: string }
  | { type: "ask_user"; requestId: string; questions: AskQuestion[] }
  | { type: "todo_update"; todos: Todo[] }
  | { type: "result"; result: string; cost: number; turns: number; sessionId: string };
