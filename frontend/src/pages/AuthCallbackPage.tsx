// frontend/src/pages/AuthCallbackPage.tsx
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { authStore } from "@/store/authStore";

export default function AuthCallbackPage() {
  const navigate = useNavigate();

  useEffect(() => {
    // StrictMode 会执行两次 effect，第一次 navigate 后 URL 已变成 /chat
    // 第二次执行时 search 为空，加守卫防止跳到 /login
    if (!window.location.pathname.includes("/auth/callback")) return;

    const params = new URLSearchParams(window.location.search);
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");

    if (access && refresh) {
      authStore.setTokens(access, refresh);
      navigate("/chat", { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  }, []);

  return (
    <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center">
      <p className="text-[#666] text-[13px]">登录中…</p>
    </div>
  );
}
