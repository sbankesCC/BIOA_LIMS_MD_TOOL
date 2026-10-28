// The app shell: top bar, "How it works" popup and the routes of every screen.
// The router itself is supplied by main.tsx (browser) or by tests (memory router).
import { Route, Routes } from "react-router-dom";
import { HowItWorksDialog, useHowItWorks } from "./components/HowItWorksDialog";
import { TopBar } from "./components/TopBar";
import { AdminAccessContext, useAdminAccessState } from "./lib/adminAccess";
import { AdminPage } from "./pages/AdminPage";
import { NotFoundPage, ReviewRoute, RunRoute, RunsPage } from "./pages/OtherPages";
import { StartRunPage } from "./pages/StartRunPage";

/** Show the top bar, the current screen and, on a first visit, the "How it works" popup. */
export function App() {
  const howItWorks = useHowItWorks();
  const adminAccess = useAdminAccessState();
  return (
    <AdminAccessContext.Provider value={adminAccess}>
      <TopBar onOpenHowItWorks={howItWorks.open} isAdminShown={adminAccess.hasAccess} />
      <Routes>
        <Route path="/" element={<StartRunPage onOpenHowItWorks={howItWorks.open} />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunRoute />} />
        <Route path="/runs/:runId/review" element={<ReviewRoute />} />
        <Route path="/admin" element={<AdminPage kind="lookup" />} />
        <Route path="/admin/reference-data" element={<AdminPage kind="reference" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <HowItWorksDialog isOpen={howItWorks.isOpen} onClose={howItWorks.close} />
    </AdminAccessContext.Provider>
  );
}
