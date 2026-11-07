import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./lib/api/queryClient";
import { AppProvider } from "./context/AppContext";
import { Shell } from "./components/layout/Shell";

// Lazy-loaded routes for optimal initial bundle splitting
const AskPage = lazy(() => import("./pages/AskPage"));
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const DocumentsPage = lazy(() => import("./pages/DocumentsPage"));
const GraphPage = lazy(() => import("./pages/GraphPage"));
const TracesPage = lazy(() => import("./pages/TracesPage"));
const RetrievalPage = lazy(() => import("./pages/RetrievalPage"));
const CachePage = lazy(() => import("./pages/CachePage"));
const ExperimentsPage = lazy(() => import("./pages/ExperimentsPage"));
const GoldenSetPage = lazy(() => import("./pages/GoldenSetPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function PageLoader() {
  return (
    <div className="flex-1 flex items-center justify-center p-12 text-zinc-500 font-mono text-xs select-none">
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-amber-400 animate-ping" />
        <span>Loading Grant Module...</span>
      </div>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppProvider>
          <Routes>
          <Route element={<Shell />}>
            <Route
              index
              element={
                <Suspense fallback={<PageLoader />}>
                  <AskPage />
                </Suspense>
              }
            />
            <Route
              path="ask"
              element={
                <Suspense fallback={<PageLoader />}>
                  <AskPage />
                </Suspense>
              }
            />
            <Route
              path="overview"
              element={
                <Suspense fallback={<PageLoader />}>
                  <OverviewPage />
                </Suspense>
              }
            />
            <Route
              path="documents"
              element={
                <Suspense fallback={<PageLoader />}>
                  <DocumentsPage />
                </Suspense>
              }
            />
            <Route
              path="graph"
              element={
                <Suspense fallback={<PageLoader />}>
                  <GraphPage />
                </Suspense>
              }
            />
            <Route
              path="traces"
              element={
                <Suspense fallback={<PageLoader />}>
                  <TracesPage />
                </Suspense>
              }
            />
            <Route
              path="retrieval"
              element={
                <Suspense fallback={<PageLoader />}>
                  <RetrievalPage />
                </Suspense>
              }
            />
            <Route
              path="cache"
              element={
                <Suspense fallback={<PageLoader />}>
                  <CachePage />
                </Suspense>
              }
            />
            <Route
              path="experiments"
              element={
                <Suspense fallback={<PageLoader />}>
                  <ExperimentsPage />
                </Suspense>
              }
            />
            <Route
              path="golden-set"
              element={
                <Suspense fallback={<PageLoader />}>
                  <GoldenSetPage />
                </Suspense>
              }
            />
            <Route
              path="settings"
              element={
                <Suspense fallback={<PageLoader />}>
                  <SettingsPage />
                </Suspense>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AppProvider>
    </BrowserRouter>
  </QueryClientProvider>
);
}

export default App;
