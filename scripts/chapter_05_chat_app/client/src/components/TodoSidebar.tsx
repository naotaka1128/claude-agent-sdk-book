import type { Todo } from "../types";

interface Props {
  todos: Todo[];
}

const statusIcon: Record<string, string> = {
  completed: "✓",
  in_progress: "●",
  pending: "○",
};

export function TodoSidebar({ todos }: Props) {
  if (todos.length === 0) return null;

  return (
    <aside className="todo-sidebar">
      <div className="todo-header">Tasks</div>
      <ul className="todo-list">
        {todos.map((t, i) => (
          <li key={i} className={`todo-item todo-${t.status}`}>
            <span className="todo-icon">{statusIcon[t.status] || "○"}</span>
            <span className="todo-content">{t.content}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
