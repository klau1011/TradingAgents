import { Suspense, lazy } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Skeleton, SkeletonText } from "./components/ui/Skeleton";

const NewRunPage = lazy(() =>
  import("./routes/NewRun").then((m) => ({ default: m.NewRunPage }))
);
const RunPage = lazy(() =>
  import("./routes/Run").then((m) => ({ default: m.RunPage }))
);
const HistoryPage = lazy(() =>
  import("./routes/History").then((m) => ({ default: m.HistoryPage }))
);
const ReportPage = lazy(() =>
  import("./routes/Report").then((m) => ({ default: m.ReportPage }))
);
const TrackRecordPage = lazy(() =>
  import("./routes/TrackRecord").then((m) => ({ default: m.TrackRecordPage }))
);

export function App() {
  const location = useLocation();
  return (
    <div className="min-h-screen flex flex-col bg-canvas text-fg">
      <Header />
      <main className="flex-1">
        <ErrorBoundary resetKey={location.pathname}>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<NewRunPage />} />
              <Route path="/runs/:runId" element={<RunPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/track-record" element={<TrackRecordPage />} />
              <Route path="/reports/:folder" element={<ReportPage />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      <Footer />
    </div>
  );
}

function RouteFallback() {
  return (
    <div className="mx-auto max-w-7xl px-32p py-80p space-y-6">
      <Skeleton className="h-10 w-1/3" rounded="rounded-pill" />
      <SkeletonText lines={4} />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}

function Header() {
  const link = ({ isActive }: { isActive: boolean }) =>
    `font-display text-nav font-medium whitespace-nowrap transition-opacity ${
      isActive ? "text-fg" : "text-muted hover:text-fg"
    }`;
  return (
    <header className="border-b border-edge bg-canvas">
      <div className="mx-auto max-w-7xl px-32p py-6 flex flex-wrap items-center justify-between gap-x-32p gap-y-3">
        <Link to="/" className="font-display text-nav font-medium tracking-tight text-fg">
          TradingAgents
        </Link>
        <nav className="flex items-center gap-6 md:gap-32p">
          <NavLink to="/" end className={link}>
            New run
          </NavLink>
          <NavLink to="/history" className={link}>
            History
          </NavLink>
          <NavLink to="/track-record" className={link}>
            Track record
          </NavLink>
        </nav>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="border-t border-edge bg-canvas">
      <div className="mx-auto max-w-7xl px-32p py-6 text-body text-subtle">
        TradingAgents Dashboard · Local
      </div>
    </footer>
  );
}
