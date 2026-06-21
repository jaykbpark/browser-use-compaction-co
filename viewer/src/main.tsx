import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type RunSummary = { runs: string[] };

type BrowserAction = {
  type: string;
  target?: string | null;
  text?: string | null;
  key?: string | null;
  amount?: number | null;
  url?: string | null;
};

type StatePointer = { screenshot: string; state: string };

type StepRecord = {
  step: number;
  action: BrowserAction;
  result: { ok: boolean; message?: string; error?: string | null };
  before?: StatePointer;
  after?: StatePointer;
};

type Route = "text_only" | "crop_with_context" | "full_screenshot";

type CompactObservation = {
  step: number;
  summary: string;
  route: Route;
  llm_observation: string;
  crop_paths: string[];
  full_screenshot_path?: string | null;
  tokens_estimate: number;
  baseline_tokens_estimate: number;
  reduction_pct: number;
};

type ReplayStepResult = {
  step: number;
  expected_next_action: BrowserAction;
  predicted_next_action: BrowserAction;
  passed: boolean;
  rationale: string;
};

type ReplayReport = {
  predictor: string;
  evaluated_steps: number;
  passed_steps: number;
  steps: ReplayStepResult[];
};

type EvalComparisonReport = {
  summary: {
    evaluated_steps: number;
    compact_passed_steps: number;
    baseline_passed_steps: number;
    compact_tokens: number;
    baseline_tokens: number;
    token_reduction_pct: number;
  };
};

type RunDetail = {
  run_id: string;
  steps: StepRecord[];
  compact_observations: CompactObservation[];
  eval_report?: ReplayReport | null;
  eval_comparison?: EvalComparisonReport | null;
};

type PageRoute = "setup" | "dashboard";

type InstallMethod = { id: string; label: string; command: string; note: string };

const INSTALL_METHODS: InstallMethod[] = [
  {
    id: "pipx",
    label: "pipx",
    command: "pipx install browserdelta",
    note: "Recommended — installs the browserdelta CLI as an isolated global tool.",
  },
  {
    id: "uvx",
    label: "uvx",
    command: "uvx browserdelta observe <run> --step 3 --format json",
    note: "Zero-install — run it on demand with uv, nothing left behind.",
  },
  {
    id: "pip",
    label: "pip",
    command: "pip install browserdelta",
    note: "Drop it straight into an existing virtualenv.",
  },
  {
    id: "source",
    label: "from source",
    command:
      'git clone https://github.com/your-org/browserdelta\ncd browserdelta && pip install -e ".[dev]"\npython -m playwright install chromium',
    note: "Run it today from this repo — no PyPI release required.",
  },
];

const AGENT_COMMAND = "browserdelta observe local_checkout --step 3 --format json";

const AGENT_OUTPUT = `{
  "step": 3,
  "route": "crop_with_context",
  "summary": "Inventory chart updated.",
  "tokens_estimate": 312,
  "baseline_tokens_estimate": 4200,
  "reduction_pct": 92.6,
  "crop_paths": ["crops/step_003/crop_01.png"]
}`;

function App() {
  const [route, setRoute] = React.useState<PageRoute>(readRoute);

  React.useEffect(() => {
    const onHashChange = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return route === "dashboard" ? <DashboardPage /> : <SetupPage />;
}

function SetupPage() {
  const [method, setMethod] = React.useState<InstallMethod>(INSTALL_METHODS[0]);
  const [copied, setCopied] = React.useState(false);

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(method.command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <main className="page setup-page">
      <header className="bar">
        <div className="wordmark">
          BrowserDelta <span>· context compression for browser agents</span>
        </div>
        <nav className="nav-links" aria-label="Pages">
          <a href="#setup" data-on="true">
            Install
          </a>
          <a href="#dashboard">How it works</a>
        </nav>
      </header>

      <section className="install-hero">
        <p className="eyebrow">Drop-in context compressor for browser agents</p>
        <h1>Install BrowserDelta in your CLI.</h1>
        <p className="install-sub">
          Replace repeated full screenshots with compact text diffs, visual crops, and a
          fallback screenshot only when it is actually needed.
        </p>

        <div className="install-card">
          <div className="install-tabs" role="tablist" aria-label="Install method">
            {INSTALL_METHODS.map((m) => (
              <button
                key={m.id}
                role="tab"
                aria-selected={m.id === method.id}
                data-on={m.id === method.id}
                onClick={() => {
                  setMethod(m);
                  setCopied(false);
                }}
              >
                {m.label}
              </button>
            ))}
          </div>
          <div className="install-cmd">
            <pre>
              {method.command.split("\n").map((line, i) => (
                <span key={i}>
                  <span className="prompt">$</span>
                  {line}
                </span>
              ))}
            </pre>
            <button className="copy" onClick={copyCommand}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="install-note">{method.note}</p>
        </div>

        <a className="how-link" href="#dashboard">
          See how it works →
        </a>
      </section>

      <section className="usage">
        <div className="usage-intro">
          <h2>Then your agent calls it each step</h2>
          <p>
            After each browser action your CLI agent shells out instead of attaching a fresh
            screenshot. It gets back the text delta, a token estimate, and any crop screenshots
            of what changed.
          </p>
        </div>
        <div className="usage-io">
          <div className="usage-block">
            <span className="usage-label">call</span>
            <pre>{AGENT_COMMAND}</pre>
          </div>
          <div className="usage-block">
            <span className="usage-label">returns</span>
            <pre>{AGENT_OUTPUT}</pre>
          </div>
        </div>
      </section>

      <section className="setup-strip">
        <div>
          <strong>Record</strong>
          <span>before and after screenshots plus page state</span>
        </div>
        <div>
          <strong>Compact</strong>
          <span>DOM diffs first, visual crops only when needed</span>
        </div>
        <div>
          <strong>Observe</strong>
          <span>JSON or agent text for Codex-style CLI loops</span>
        </div>
      </section>
    </main>
  );
}

function DashboardPage() {
  const [runs, setRuns] = React.useState<string[]>([]);
  const [selectedRun, setSelectedRun] = React.useState("");
  const [detail, setDetail] = React.useState<RunDetail | null>(null);
  const [selectedStep, setSelectedStep] = React.useState(1);
  const [predictor, setPredictor] = React.useState<"heuristic" | "llm">("heuristic");
  const [status, setStatus] = React.useState<"loading" | "ready" | "offline">("loading");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [toolsOpen, setToolsOpen] = React.useState(false);

  React.useEffect(() => {
    fetch("/api/runs")
      .then((r) => r.json())
      .then((data: RunSummary) => {
        const next = data.runs ?? [];
        setRuns(next);
        setSelectedRun((cur) => cur || next[0] || "");
        setStatus("ready");
      })
      .catch(() => setStatus("offline"));
  }, []);

  React.useEffect(() => {
    if (!selectedRun) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    loadRun(selectedRun).then((run) => {
      if (cancelled) return;
      setDetail(run);
      setSelectedStep(run.compact_observations[0]?.step ?? 1);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedRun]);

  async function run(label: string, url: string) {
    if (!selectedRun) return;
    setBusy(label);
    try {
      await fetch(url, { method: "POST" });
      setDetail(await loadRun(selectedRun));
    } finally {
      setBusy(null);
    }
  }

  const enc = encodeURIComponent;
  const compact = () => run("compact", `/api/runs/${enc(selectedRun)}/compact`);
  const evaluate = () =>
    run("evaluate", `/api/runs/${enc(selectedRun)}/eval?predictor=${enc(predictor)}`);
  const compare = () =>
    run(
      "compare",
      `/api/runs/${enc(selectedRun)}/eval/compare?predictor=${enc(predictor)}&baseline_context_mode=vision_full_state`,
    );

  const activeDetail = detail?.run_id === selectedRun ? detail : null;
  const observations = activeDetail?.compact_observations ?? [];
  const totals = summarize(activeDetail);
  const current = observations.find((o) => o.step === selectedStep) ?? observations[0] ?? null;
  const currentRaw = activeDetail?.steps.find((s) => s.step === current?.step) ?? null;
  const currentReplay =
    activeDetail?.eval_report?.steps.find((s) => s.step === current?.step) ?? null;
  const hasEval = totals.matched !== null && totals.total !== null;

  return (
    <main className="page">
      <header className="bar">
        <div className="wordmark">
          BrowserDelta <span>· less context per step, same decisions</span>
        </div>
        <div className="bar-right">
          <nav className="nav-links" aria-label="Pages">
            <a href="#setup">Install</a>
            <a href="#dashboard" data-on="true">
              How it works
            </a>
          </nav>
          {runs.length > 0 ? (
            <label className="run-switch">
              Run
              <select value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}>
                {runs.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div className="tools">
            <button className="ghost" onClick={() => setToolsOpen((v) => !v)} disabled={!selectedRun}>
              Recompute {toolsOpen ? "▴" : "▾"}
            </button>
            {toolsOpen ? (
              <div className="tools-pop" onMouseLeave={() => setToolsOpen(false)}>
                <label>
                  Predictor
                  <select
                    value={predictor}
                    onChange={(e) => setPredictor(e.target.value as "heuristic" | "llm")}
                  >
                    <option value="heuristic">heuristic</option>
                    <option value="llm">llm</option>
                  </select>
                </label>
                <button onClick={compact} disabled={!!busy}>
                  {busy === "compact" ? "Compacting…" : "Compact run"}
                </button>
                <button onClick={evaluate} disabled={!!busy}>
                  {busy === "evaluate" ? "Checking…" : "Check next moves"}
                </button>
                <button onClick={compare} disabled={!!busy}>
                  {busy === "compare" ? "Comparing…" : "Compare to screenshots"}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </header>

      {observations.length ? (
        <section className="hero">
          <h1>Same decisions, far less context.</h1>
          <div className="hero-stats">
            <div className="metric">
              <span className="num good">{totals.reductionPct.toFixed(0)}%</span>
              <span className="cap">
                fewer tokens
                <i>
                  {totals.compactTokens.toLocaleString()} vs {totals.baselineTokens.toLocaleString()}
                </i>
              </span>
            </div>
            <span className="divider" />
            <div className="metric">
              <span className="num">{hasEval ? `${totals.matched}/${totals.total}` : "—"}</span>
              <span className="cap">
                moves match screenshots
                <i>
                  {hasEval
                    ? totals.baselineMatched !== null
                      ? `baseline ${totals.baselineMatched}/${totals.total}`
                      : "next action verified"
                    : "run a check to verify"}
                </i>
              </span>
            </div>
          </div>
        </section>
      ) : (
        <p className="hint">
          {status === "offline"
            ? "Can't reach the API — start the backend and reload."
            : "Pick a run and Recompute → Compact to see how much page context is removed."}
        </p>
      )}

      {observations.length ? (
        <div className="layout">
          <nav className="steps">
            {observations.map((o) => {
              const raw = activeDetail?.steps.find((s) => s.step === o.step);
              const replay = activeDetail?.eval_report?.steps.find((s) => s.step === o.step);
              return (
                <button
                  key={o.step}
                  className="step"
                  data-on={o.step === current?.step}
                  onClick={() => setSelectedStep(o.step)}
                >
                  <span className="step-top">
                    <span className="step-n">Step {o.step}</span>
                    <Mark replay={replay} />
                  </span>
                  <span className="step-act">{describeAction(raw?.action)}</span>
                  <span className="step-save">−{Math.round(o.reduction_pct)}% tokens</span>
                </button>
              );
            })}
          </nav>

          <section className="stage">
            {current ? (
              <StepView runId={selectedRun} obs={current} raw={currentRaw} replay={currentReplay} />
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}

function StepView({
  runId,
  obs,
  raw,
  replay,
}: {
  runId: string;
  obs: CompactObservation;
  raw: StepRecord | null;
  replay: ReplayStepResult | null;
}) {
  const screenshot = raw?.after?.screenshot ?? null;
  const crops = obs.crop_paths ?? [];

  return (
    <>
      <div className="compare">
        <article className="pane">
          <header>
            <span className="pane-title">Full screenshot</span>
            <span className="pane-cost">{obs.baseline_tokens_estimate.toLocaleString()} tokens</span>
          </header>
          <div className="pane-body shot">
            {screenshot ? (
              <img src={fileUrl(runId, screenshot)} alt={`Step ${obs.step}`} loading="lazy" />
            ) : (
              <p className="muted">No screenshot recorded.</p>
            )}
          </div>
        </article>

        <article className="pane">
          <header>
            <span className="pane-title">BrowserDelta</span>
            <span className="pane-cost good">
              {obs.tokens_estimate.toLocaleString()} tokens · −{Math.round(obs.reduction_pct)}%
            </span>
          </header>
          <div className="pane-body">
            <pre className="obs">{obs.llm_observation}</pre>
            {crops.length ? (
              <div className="crops">
                <span className="muted">
                  + {crops.length} crop{crops.length > 1 ? "s" : ""} of what changed
                </span>
                <div className="crop-row">
                  {crops.map((c) => (
                    <img key={c} src={fileUrl(runId, c)} alt="changed region" loading="lazy" />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </article>
      </div>

      <div className="outcome">
        <span className="outcome-label">Next move</span>
        <strong className="outcome-move">{describeAction(replay?.expected_next_action ?? raw?.action)}</strong>
        {replay ? (
          <span className={`outcome-result ${replay.passed ? "pass" : "fail"}`}>
            {replay.passed ? "agent agreed" : "agent differed"}
          </span>
        ) : (
          <span className="muted outcome-result">not checked</span>
        )}
      </div>
    </>
  );
}

function Mark({ replay }: { replay?: ReplayStepResult }) {
  if (!replay) return <span className="mark none" title="not checked" />;
  return (
    <span className={`mark ${replay.passed ? "pass" : "fail"}`} title={replay.passed ? "agreed" : "differed"}>
      {replay.passed ? "✓" : "✗"}
    </span>
  );
}

type Totals = {
  compactTokens: number;
  baselineTokens: number;
  reductionPct: number;
  matched: number | null;
  total: number | null;
  baselineMatched: number | null;
};

function summarize(detail: RunDetail | null): Totals {
  const obs = detail?.compact_observations ?? [];
  const cmp = detail?.eval_comparison?.summary;
  const rep = detail?.eval_report;

  let compactTokens: number;
  let baselineTokens: number;
  let reductionPct: number;
  if (cmp) {
    compactTokens = cmp.compact_tokens;
    baselineTokens = cmp.baseline_tokens;
    reductionPct = cmp.token_reduction_pct;
  } else {
    compactTokens = obs.reduce((a, o) => a + o.tokens_estimate, 0);
    baselineTokens = obs.reduce((a, o) => a + o.baseline_tokens_estimate, 0);
    reductionPct = baselineTokens ? (1 - compactTokens / baselineTokens) * 100 : 0;
  }

  return {
    compactTokens,
    baselineTokens,
    reductionPct,
    matched: cmp?.compact_passed_steps ?? rep?.passed_steps ?? null,
    total: cmp?.evaluated_steps ?? rep?.evaluated_steps ?? null,
    baselineMatched: cmp?.baseline_passed_steps ?? null,
  };
}

function describeAction(a?: BrowserAction | null): string {
  if (!a) return "—";
  const q = (v?: string | null) => (v ? `“${v}”` : "");
  switch (a.type) {
    case "click":
      return `Click ${q(a.target) || "element"}`.trim();
    case "type":
      return `Type ${q(a.text)} into ${a.target ?? "field"}`.trim();
    case "press":
      return `Press ${a.key ?? ""}`.trim();
    case "goto":
      return `Go to ${a.url ?? ""}`.trim();
    case "scroll":
      return "Scroll the page";
    case "wait":
      return "Wait";
    default:
      return a.type;
  }
}

async function loadRun(runId: string): Promise<RunDetail> {
  const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error(`Failed to load ${runId}`);
  return res.json();
}

function fileUrl(runId: string, path: string) {
  const p = path.split("/").map(encodeURIComponent).join("/");
  return `/api/runs/${encodeURIComponent(runId)}/files/${p}`;
}

function readRoute(): PageRoute {
  return window.location.hash === "#dashboard" ? "dashboard" : "setup";
}

createRoot(document.getElementById("root")!).render(<App />);
