import React from "react";
import { createRoot } from "react-dom/client";
import { Activity, Gauge, ScanLine } from "lucide-react";
import "./styles.css";

type RunSummary = {
  runs: string[];
};

function App() {
  const [runs, setRuns] = React.useState<string[]>([]);
  const [status, setStatus] = React.useState("loading");

  React.useEffect(() => {
    fetch("/api/runs")
      .then((response) => response.json())
      .then((data: RunSummary) => {
        setRuns(data.runs ?? []);
        setStatus("ready");
      })
      .catch(() => setStatus("api unavailable"));
  }, []);

  return (
    <main>
      <section className="hero">
        <div>
          <p className="eyebrow">BrowserDelta</p>
          <h1>Browser-state compaction for Browserbase agents.</h1>
          <p className="lede">
            Record browser steps, diff the before/after state, and send the agent only what changed.
          </p>
        </div>
        <div className="status">
          <Activity size={18} />
          <span>{status}</span>
        </div>
      </section>

      <section className="grid">
        <Panel icon={<ScanLine size={18} />} title="Recorder">
          Browserbase or local Playwright writes screenshots and page-state JSON for every step.
        </Panel>
        <Panel icon={<Gauge size={18} />} title="Codec">
          Structural diffs and visual diffs produce compact LLM observations.
        </Panel>
      </section>

      <section className="runs">
        <h2>Runs</h2>
        {runs.length === 0 ? (
          <p>No runs found. Start with `python scripts/record_demo.py --run-id smoke`.</p>
        ) : (
          <ul>
            {runs.map((run) => (
              <li key={run}>{run}</li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

function Panel({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <article className="panel">
      <div className="panel-title">
        {icon}
        <h2>{title}</h2>
      </div>
      <p>{children}</p>
    </article>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
