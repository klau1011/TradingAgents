import { Link, NavLink, Route, Routes } from "react-router-dom";
import { NewRunPage } from "./routes/NewRun";
import { RunPage } from "./routes/Run";
import { HistoryPage } from "./routes/History";
import { ReportPage } from "./routes/Report";
import { useTheme } from "./hooks/useTheme";

export function App() {
  return (
    <div className="min-h-screen flex flex-col bg-canvas text-fg">
      <Header />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<NewRunPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/reports/:folder" element={<ReportPage />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}

function Header() {
  const link = ({ isActive }: { isActive: boolean }) =>
    `font-display text-nav font-medium transition-opacity ${
      isActive ? "text-fg" : "text-muted hover:text-fg"
    }`;
  return (
    <header className="border-b border-edge bg-canvas">
      <div className="mx-auto max-w-7xl px-32p py-6 flex items-center justify-between">
        <Link to="/" className="font-display text-nav font-medium tracking-tight text-fg">
          TradingAgents
        </Link>
        <nav className="flex items-center gap-32p">
          <NavLink to="/" end className={link}>
            New run
          </NavLink>
          <NavLink to="/history" className={link}>
            History
          </NavLink>
          <ThemeToggle />
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

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="inline-flex items-center justify-center h-10 w-10 rounded-pill border-2 border-edge text-fg hover:opacity-85 transition-opacity focus:outline-none focus-visible:shadow-focus"
    >
      {isDark ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function SunIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}
