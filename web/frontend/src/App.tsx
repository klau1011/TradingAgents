import { Link, NavLink, Route, Routes } from "react-router-dom";
import { NewRunPage } from "./routes/NewRun";
import { RunPage } from "./routes/Run";
import { HistoryPage } from "./routes/History";
import { ReportPage } from "./routes/Report";

export function App() {
  return (
    <div className="min-h-screen flex flex-col">
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
      isActive ? "text-dark" : "text-slate-mid hover:text-dark"
    }`;
  return (
    <header className="border-b border-slate-tone bg-white">
      <div className="mx-auto max-w-7xl px-32p py-6 flex items-center justify-between">
        <Link to="/" className="font-display text-nav font-medium tracking-tight text-dark">
          TradingAgents
        </Link>
        <nav className="flex items-center gap-32p">
          <NavLink to="/" end className={link}>
            New run
          </NavLink>
          <NavLink to="/history" className={link}>
            History
          </NavLink>
        </nav>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-tone bg-white">
      <div className="mx-auto max-w-7xl px-32p py-6 text-body text-slate-cool">
        TradingAgents Dashboard · Local
      </div>
    </footer>
  );
}
