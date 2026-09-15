import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { HomePage } from "./pages/Home/HomePage";

// Route-level code splitting (Phase 7 perf pass, 2026-09-02): App.tsx used to
// statically import every page, so the public/unauthenticated HomePage paid
// the full bundle cost of every other page too - most notably CodeMirror 6
// (codemirror/@codemirror/*/@uiw/react-codemirror), a ~600KB-ish dependency
// used only by the Automata page's editor. `npm run build` was flagging a
// single 792KB (255KB gzip) chunk before this change. HomePage stays a
// static import since it's the one page that should paint with zero extra
// waterfall - everything behind RequireAuth can afford a lazy chunk fetch.
const AutomataPage = lazy(() =>
  import("./pages/Automata/AutomataPage").then((m) => ({ default: m.AutomataPage }))
);
const PlayPage = lazy(() => import("./pages/Play/PlayPage").then((m) => ({ default: m.PlayPage })));
const ProcessingPage = lazy(() =>
  import("./pages/Processing/ProcessingPage").then((m) => ({ default: m.ProcessingPage }))
);
const ResultsPage = lazy(() =>
  import("./pages/Results/ResultsPage").then((m) => ({ default: m.ResultsPage }))
);
const FriendsPage = lazy(() =>
  import("./pages/Friends/FriendsPage").then((m) => ({ default: m.FriendsPage }))
);
const SettingsPage = lazy(() =>
  import("./pages/Settings/SettingsPage").then((m) => ({ default: m.SettingsPage }))
);

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          {/* fallback={null}: matches the "just don't render until ready"
              convention HomePage already uses for its own auth-loading state
              - route chunks are small/cached after first visit, so a blank
              frame during the fetch is preferable to a bespoke spinner here. */}
          <Suspense fallback={null}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route
                path="/automata/:automatonId?"
                element={
                  <RequireAuth>
                    <AutomataPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/play"
                element={
                  <RequireAuth>
                    <PlayPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/processing/:tournamentId"
                element={
                  <RequireAuth>
                    <ProcessingPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/results/:tournamentId"
                element={
                  <RequireAuth>
                    <ResultsPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/friends"
                element={
                  <RequireAuth>
                    <FriendsPage />
                  </RequireAuth>
                }
              />
              <Route
                path="/settings"
                element={
                  <RequireAuth>
                    <SettingsPage />
                  </RequireAuth>
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
