// The app shell: top bar, "How it works" popup and the routes of every screen.
// The router itself is supplied by main.tsx (browser) or by tests (memory router).
import { Route, Routes } from "react-router-dom";
import { HowItWorksDialog, useHowItWorks } from "./components/HowItWorksDialog";
import { TopBar } from "./components/TopBar";
import { AdminPage, NotFoundPage, RunRoute, RunsPage } from "./pages/OtherPages";
import { StartRunPage } from "./pages/StartRunPage";

/** Show the top bar, the current screen and, on a first visit, the "How it works" popup. */
export function App() {
  const howItWorks = useHowItWorks();
  return (
    <>
      <TopBar onOpenHowItWorks={howItWorks.open} />
      <Routes>
        <Route path="/" element={<StartRunPage onOpenHowItWorks={howItWorks.open} />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunRoute />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <HowItWorksDialog isOpen={howItWorks.isOpen} onClose={howItWorks.close} />
    </>
  );
}
