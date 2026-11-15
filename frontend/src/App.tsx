import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api";
import { AppShell } from "./components/AppShell";
import { ChatWidget } from "./components/assistant/ChatWidget";
import { Alert } from "./components/ui";
import Admin from "./pages/Admin";
import Conflicts from "./pages/Conflicts";
import Demand from "./pages/Demand";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Preferences from "./pages/Preferences";
import Schedule from "./pages/Schedule";
import { useAuth } from "./store/auth";
import { useCollab } from "./store/collab";
import { usePlan } from "./store/plan";

export default function App() {
  const loadMeta = usePlan((s) => s.loadMeta);
  const metaError = usePlan((s) => s.metaError);
  const dataVersion = usePlan((s) => s.dataVersion);
  const requireLogin = usePlan((s) => s.meta?.require_login ?? false);
  const user = useAuth((s) => s.user);
  const location = useLocation();
  // Private deployments (REQUIRE_LOGIN=true): everything except the login page needs an account
  const gated = requireLogin && !user && location.pathname !== "/login";

  // Reference data (terms, sequences) reloads when the underlying data changes
  useEffect(() => { loadMeta(); }, [loadMeta, dataVersion]);

  // Live collaboration channel + refresh the cached user (role may have changed)
  useEffect(() => {
    useCollab.getState().connect();
    if (useAuth.getState().token) api.me().then((u) => useAuth.getState().setUser(u)).catch(() => undefined);
    return () => useCollab.getState().disconnect();
  }, []);

  return (
    <AppShell>
      {metaError && <div className="mb-6"><Alert tone="error" title="Can't Reach the Scheduler API">{metaError}</Alert></div>}
      {gated ? <Navigate to="/login" replace state={{ from: location.pathname + location.search }} /> : <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/login" element={<Login />} />
        <Route path="/preferences" element={<Preferences />} />
        <Route path="/demand" element={<Demand />} />
        <Route path="/schedule" element={<Schedule />} />
        <Route path="/conflicts" element={<Conflicts />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>}
      <ChatWidget />
    </AppShell>
  );
}
