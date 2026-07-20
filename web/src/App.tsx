import { Link, Route, Routes } from "react-router-dom";

import { DevelopPage } from "./develop/DevelopPage";
import { useWorkspace } from "./develop/WorkspaceContext";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<MainMenu />} />
      <Route path="/develop" element={<DevelopPage />} />
      <Route path="/quiz" element={<QuizPlaceholder />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

function MainMenu() {
  const { workspace, loading, error, initialize } = useWorkspace();
  return (
    <main className="menu-page">
      <div className="menu-hero">
        <span className="eyebrow">Local opening workspace</span>
        <h1>Chess Flow</h1>
        {loading && <p>Loading selected flow…</p>}
        {workspace && (
          <div className="selected-flow">
            <span>Selected flow</span>
            <strong>{workspace.rulebook.name}</strong>
            <small>{workspace.rulebook.path} · Opening Rule Engine v{workspace.rulebook.version}</small>
          </div>
        )}
        {error && !workspace && (
          <div className="global-error" role="alert">
            <span>{error.message}</span>
            <button onClick={() => void initialize()}>Try again</button>
          </div>
        )}
      </div>
      <nav className="mode-grid" aria-label="Application modes">
        <Link className="mode-card" to="/quiz">
          <span className="mode-index">01</span>
          <h2>Quiz</h2>
          <p>Practice the flow from memory.</p>
          <span className="mode-state">Web mode coming later</span>
        </Link>
        <Link className={`mode-card primary-mode ${!workspace ? "disabled-link" : ""}`} to="/develop" aria-disabled={!workspace}>
          <span className="mode-index">02</span>
          <h2>Develop</h2>
          <p>Explore moves, inspect the current policy, and evaluate positions.</p>
          <span className="mode-state">Open workspace →</span>
        </Link>
      </nav>
    </main>
  );
}

function QuizPlaceholder() {
  return (
    <main className="center-page">
      <span className="eyebrow">Quiz</span>
      <h1>Web Quiz is not implemented yet.</h1>
      <p>The existing Textual quiz remains available while this browser slice focuses on Development Mode.</p>
      <Link className="button-link" to="/">Return to menu</Link>
    </main>
  );
}

function NotFound() {
  return <main className="center-page"><h1>Page not found</h1><Link to="/">Return home</Link></main>;
}
