import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App";
import { authStore } from "@/store/authStore";

// 全局 fetch 拦截：自动注入 Authorization header
const _originalFetch = window.fetch;
window.fetch = async (input, init = {}) => {
  const token = authStore.getAccessToken();
  if (token) {
    const headers = new Headers(init.headers);
    if (!headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    init = { ...init, headers };
  }
  return _originalFetch(input, init);
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
