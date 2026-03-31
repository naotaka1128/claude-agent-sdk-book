import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ChatPanel } from "./components/ChatPanel";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ChatPanel />
  </StrictMode>,
);
