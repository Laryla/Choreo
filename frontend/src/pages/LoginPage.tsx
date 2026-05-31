// frontend/src/pages/LoginPage.tsx
const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0d0d0d] flex items-center justify-center">
      <div className="w-[360px] bg-[#111] rounded-2xl border border-[#222] p-8 flex flex-col items-center gap-6">
        <div className="text-center mb-2">
          <h1 className="text-[20px] font-semibold text-[#e8e8e8]">欢迎使用 Choreo</h1>
          <p className="text-[13px] text-[#666] mt-1">选择登录方式继续</p>
        </div>

        <a
          href={`${API}/auth/github/login`}
          className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl bg-[#1a1a1a] border border-[#2a2a2a] text-[13px] text-[#e8e8e8] hover:border-[#444] transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
          </svg>
          使用 GitHub 登录
        </a>

        <a
          href={`${API}/auth/feishu/login`}
          className="w-full flex items-center justify-center gap-3 px-4 py-2.5 rounded-xl bg-[#1a1a1a] border border-[#2a2a2a] text-[13px] text-[#e8e8e8] hover:border-[#444] transition-colors"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none">
            <rect width="24" height="24" rx="6" fill="#3370FF"/>
            <path d="M7 8l5 3 5-3M7 12l5 3 5-3" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          使用飞书登录
        </a>
      </div>
    </div>
  );
}
