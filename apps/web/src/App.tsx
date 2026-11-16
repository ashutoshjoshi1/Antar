import { lazy, Suspense } from "react";
import { Link, Route, Routes } from "react-router";

import { AppShell } from "./components/AppShell";
import { Deployments } from "./pages/Deployments";
import { Hardware } from "./pages/Hardware";
import { Models } from "./pages/Models";
import { Optimization } from "./pages/Optimization";
import { Overview } from "./pages/Overview";
import { Playground } from "./pages/Playground";
import { Settings } from "./pages/Settings";
import { VisionStudio } from "./pages/VisionStudio";

const Benchmarks = lazy(() =>
  import("./pages/Benchmarks").then((module) => ({ default: module.Benchmarks })),
);

function NotFound() {
  return (
    <p className="text-muted">
      This page doesn't exist.{" "}
      <Link to="/" className="text-ink underline">
        Go to the overview
      </Link>
    </p>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Overview />} />
        <Route path="playground" element={<Playground />} />
        <Route path="vision" element={<VisionStudio />} />
        <Route path="models" element={<Models />} />
        <Route path="hardware" element={<Hardware />} />
        <Route path="optimization" element={<Optimization />} />
        <Route
          path="benchmarks"
          element={
            <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
              <Benchmarks />
            </Suspense>
          }
        />
        <Route path="deployments" element={<Deployments />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
