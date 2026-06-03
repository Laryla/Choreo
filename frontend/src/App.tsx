import { Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar/Sidebar";
import ChatPage from "./pages/ChatPage";
import TaskListPage from "./pages/TaskListPage";
import TaskRunsPage from "./pages/TaskRunsPage";
import HistoryPage from "./pages/HistoryPage";
import CustomizePage from "./pages/CustomizePage";
import LoginPage from "./pages/LoginPage";
import AuthCallbackPage from "./pages/AuthCallbackPage";
import { ProtectedRoute } from "./components/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      {/* Public routes — no sidebar, no auth */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallbackPage />} />

      {/* Protected routes — require login */}
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <div className="flex h-screen overflow-hidden">
              <Sidebar />
              <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                <Routes>
                  <Route path="/" element={<Navigate to="/chat" replace />} />
                  <Route path="/chat" element={<ChatPage />} />
                  <Route path="/chat/:threadId" element={<ChatPage />} />
                  <Route path="/tasks" element={<TaskListPage />} />
                  <Route path="/tasks/:taskId" element={<TaskRunsPage />} />
                  <Route path="/history" element={<HistoryPage />} />
                  <Route path="/skills" element={<Navigate to="/customize/skills" replace />} />
                  <Route path="/customize/*" element={<CustomizePage />} />
                </Routes>
              </div>
            </div>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
