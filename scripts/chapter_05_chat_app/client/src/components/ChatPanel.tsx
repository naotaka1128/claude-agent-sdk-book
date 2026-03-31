import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AskUserRequest, ChatMessage, Todo, WSMessage } from "../types";
import { useWebSocket } from "../hooks/useWebSocket";
import { AskUserCard } from "./AskUserCard";
import { TodoSidebar } from "./TodoSidebar";

let msgId = 0;
const nextId = () => String(++msgId);

/** ツール名 + input を日本語ラベルに変換 */
function formatToolLabel(name: string, input?: string): string {
  const i = input || "";
  switch (name) {
    case "Read":
      return `${extractPath(i)} を参照中`;
    case "Glob":
      return `${extractField(i, "pattern") || i} を検索中`;
    case "Grep":
      return `'${extractField(i, "pattern") || i}' をファイル内検索中`;
    case "Write":
      return `${extractPath(i)} に書き込み中`;
    case "Edit":
      return `${extractPath(i)} を編集中`;
    case "Bash":
      return "コマンドを実行中";
    case "TodoWrite":
      return "タスクリストを更新中";
    case "ToolSearch":
      return "";
    case "AskUserQuestion":
      return "";
    case "Agent":
      return "サブエージェントを実行中";
    default: {
      const q = extractField(i, "query") || extractField(i, "q");
      if (q) return `「${q}」を検索中`;
      return `${name} を実行中`;
    }
  }
}

function extractPath(input: string): string {
  const m = input.match(/file_path['":\s]+['"]?([^'"}\s,]+)/);
  if (m) {
    const parts = m[1].split("/");
    return parts.length > 2 ? `…/${parts.slice(-2).join("/")}` : m[1];
  }
  return "ファイル";
}

function extractField(input: string, field: string): string {
  const m = input.match(new RegExp(`${field}['"]?\\s*[:=]\\s*['"]([^'"]*)`));
  return m ? m[1] : "";
}

const TOOL_PREFIX = "\x00tool:";
const ANSWER_PREFIX = "\x00answer:";

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamText, setStreamText] = useState("");
  const [thinkingText, setThinkingText] = useState("");
  const [askRequests, setAskRequests] = useState<AskUserRequest[]>([]);
  const [todos, setTodos] = useState<Todo[]>([]);
  const [input, setInput] = useState("");
  const [waiting, setWaiting] = useState(false);
  const flowRef = useRef<HTMLDivElement>(null);
  const composing = useRef(false);

  const handleMessage = useCallback((msg: WSMessage) => {
    switch (msg.type) {
      case "thinking_delta":
        setThinkingText((p) => p + msg.text);
        break;
      case "stream_delta":
        setThinkingText("");
        setStreamText((p) => p + msg.text);
        break;
      case "tool_use": {
        const label = formatToolLabel(msg.name, msg.input);
        if (label) {
          setMessages((p) => [
            ...p,
            { id: nextId(), role: "system", text: TOOL_PREFIX + label },
          ]);
        }
        break;
      }
      case "assistant":
        setStreamText("");
        setThinkingText("");
        setMessages((p) => [
          ...p,
          { id: nextId(), role: "assistant", text: msg.text, toolCalls: msg.toolCalls },
        ]);
        break;
      case "ask_user":
        setThinkingText("");
        setAskRequests((p) => [
          ...p,
          { requestId: msg.requestId, questions: msg.questions },
        ]);
        break;
      case "todo_update":
        setTodos(msg.todos);
        break;
      case "result":
        setStreamText("");
        setThinkingText("");
        setWaiting(false);
        setMessages((p) => [
          ...p,
          {
            id: nextId(),
            role: "system",
            text: `完了 — $${msg.cost.toFixed(4)} / ${msg.turns} turns`,
          },
        ]);
        break;
    }
  }, []);

  const { send, connected } = useWebSocket(handleMessage);

  const quickSend = (text: string) => {
    if (!connected) return;
    setMessages((p) => [...p, { id: nextId(), role: "user", text }]);
    send({ type: "message", message: text });
    setWaiting(true);
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text || !connected) return;
    quickSend(text);
    setInput("");
  };

  const handleAskSubmit = (
    requestId: string,
    answers: Record<string, string>,
  ) => {
    send({ type: "ask_response", requestId, answers });
    setAskRequests((p) => p.filter((r) => r.requestId !== requestId));
    const summaries = Object.values(answers).filter(Boolean);
    if (summaries.length > 0) {
      setMessages((p) => [
        ...p,
        { id: nextId(), role: "system", text: ANSWER_PREFIX + summaries.join(" / ") },
      ]);
    }
  };

  useEffect(() => {
    flowRef.current?.scrollTo({
      top: flowRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, streamText, thinkingText, askRequests]);

  const thinkingPreview = thinkingText
    ? thinkingText.replace(/\n/g, " ").trim()
    : "";

  return (
    <div className="app-layout">
      <div className="topbar">
        <div className="topbar-title">Travel Planner</div>
        <div className="topbar-status">
          {connected ? "connected" : "connecting…"}
        </div>
      </div>

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div className="flow-wrap" ref={flowRef}>
          <div className="flow">
            {messages.length === 0 && !waiting && (
              <div className="welcome">
                <h1 className="welcome-title">Travel Planner</h1>
                <p className="welcome-desc">
                  旅行の希望を伝えると、Claude が対話しながらプランを作成します。
                </p>
                <div className="welcome-suggestions">
                  <button className="welcome-chip" onClick={() => quickSend("京都2泊3日の旅行プランを考えてください")}>
                    京都 2泊3日
                  </button>
                  <button className="welcome-chip" onClick={() => quickSend("ローマとフィレンツェを巡る1週間のイタリア旅行")}>
                    イタリア 1週間
                  </button>
                  <button className="welcome-chip" onClick={() => quickSend("子連れで楽しめる沖縄旅行を計画してほしい")}>
                    沖縄 子連れ
                  </button>
                </div>
              </div>
            )}

            {/* メッセージ (全て timeline-item で囲む) */}
            {messages.map((m) => {
              // ツールイベント
              if (m.text.startsWith(TOOL_PREFIX)) {
                return (
                  <div key={m.id} className="timeline-item">
                    <div className="tool-event">
                      <span className="tool-event-icon">🔍</span>
                      <span className="tool-event-label">{m.text.slice(TOOL_PREFIX.length)}</span>
                    </div>
                  </div>
                );
              }
              // 回答サマリー
              if (m.text.startsWith(ANSWER_PREFIX)) {
                return (
                  <div key={m.id} className="timeline-item">
                    <div className="answered-group">
                      {m.text.slice(ANSWER_PREFIX.length).split(" / ").map((s, i) => (
                        <span key={i} className="answered-summary">{s}</span>
                      ))}
                    </div>
                  </div>
                );
              }
              // 完了メッセージ
              if (m.role === "system") {
                return (
                  <div key={m.id} className="timeline-item">
                    <div className="msg-system">{m.text}</div>
                  </div>
                );
              }
              // user / assistant
              return (
                <div key={m.id} className="timeline-item">
                  <div className={`flow-item ${m.role === "user" ? "flow-item-user" : "flow-item-agent"}`}>
                    {m.role === "user" ? (
                      <div className="user-text">{m.text}</div>
                    ) : (
                      <div className="agent-text">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* AskUserQuestion カード */}
            {askRequests.map((req) => (
              <div key={req.requestId} className="timeline-item">
                <div className="flow-item flow-item-agent">
                  <AskUserCard
                    requestId={req.requestId}
                    questions={req.questions}
                    onSubmit={handleAskSubmit}
                  />
                </div>
              </div>
            ))}

            {/* ストリーミングテキスト */}
            {streamText && (
              <div className="timeline-item">
                <div className="flow-item flow-item-agent">
                  <div className="agent-text">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamText}</ReactMarkdown>
                  </div>
                </div>
              </div>
            )}

            {/* スピナー + thinking テキスト */}
            {waiting && !streamText && askRequests.length === 0 && (
              <div className="timeline-item">
                <div className="spinner-row">
                  <div className="spinner-dots">
                    <span /><span /><span />
                  </div>
                  {thinkingPreview && (
                    <span className="spinner-thinking">
                      考えていること：{thinkingPreview.length > 80
                        ? thinkingPreview.slice(0, 80) + "…"
                        : thinkingPreview}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        <TodoSidebar todos={todos} />
      </div>

      <div className="input-dock">
        <div className="input-bar">
          <input
            className="chat-input"
            placeholder={connected ? "メッセージを入力..." : "接続中..."}
            value={input}
            disabled={!connected || waiting}
            onChange={(e) => setInput(e.target.value)}
            onCompositionStart={() => { composing.current = true; }}
            onCompositionEnd={() => { composing.current = false; }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !composing.current) {
                e.preventDefault();
                handleSend();
              }
            }}
          />
          <button
            className="chat-send"
            disabled={!connected || waiting || !input.trim()}
            onClick={handleSend}
          >
            送信
          </button>
        </div>
      </div>
    </div>
  );
}
