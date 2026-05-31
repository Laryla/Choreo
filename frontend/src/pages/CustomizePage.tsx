// frontend/src/pages/CustomizePage.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import CustomizeNav from "@/components/Customize/CustomizeNav";
import CustomizeSkillsPage from "./CustomizeSkillsPage";
import CustomizeMcpPage from "./CustomizeMcpPage";
import CustomizeCuratorPage from "./CustomizeCuratorPage";

export default function CustomizePage() {
  return (
    <div className="flex h-full overflow-hidden">
      <CustomizeNav />
      <div className="flex-1 min-w-0 overflow-hidden">
        <Routes>
          <Route index element={<Navigate to="skills" replace />} />
          <Route path="skills" element={<CustomizeSkillsPage />} />
          <Route path="mcp" element={<CustomizeMcpPage />} />
          <Route path="curator" element={<CustomizeCuratorPage />} />
        </Routes>
      </div>
    </div>
  );
}
