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
  context_mode: "compact" | "full_state" | "vision_full_state";
  predictor: string;
  evaluated_steps: number;
  passed_steps: number;
  steps: ReplayStepResult[];
};

type EvalComparisonReport = {
  predictor: string;
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
  manifest: { start_url?: string; mode?: string } | null;
  steps: StepRecord[];
  compact_observations: CompactObservation[];
  eval_report?: ReplayReport | null;
  eval_comparison?: EvalComparisonReport | null;
};

function App() {
  const [runs, setRuns] = React.useState<string[]>([]);
  const [selectedRun, setSelectedRun] = React.useState("");
  const [detail, setDetail] = React.useState<RunDetail | null>(null);
  const [selectedStep, setSelectedStep] = React.useState(1);
  const [predictor, setPredictor] = React.useState<"heuristic" | "llm">("heuristic");
  const [status, setStatus] = React.useState<"loading" | "ready" | "offline">("loading");
  const [busy, setBusy] = React.useState<string | null>(null);

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
    if (!selectedRun) return setDetail(null);
    loadRun(selectedRun).then((run) => {
      setDetail(run);
      setSelectedStep(run.compact_observations[0]?.step ?? 1);
    });
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

  const observations = detail?.compact_observations ?? [];
  const totals = summarize(detail);
  const current = observations.find((o) => o.step === selectedStep) ?? observations[0] ?? null;
  const currentRaw = detail?.steps.find((s) => s.step === current?.step) ?? null;
  const currentReplay = detail?.eval_report?.steps.find((s) => s.step === current?.step) ?? null;

  return (
    <main className="page">
      <header className="bar">
        <div className="wordmark">
          <strong>BrowserDelta</strong>
          <span>Less context per step. Same decisions.</span>
        </div>
        <div className="controls">
          <select value={selectedRun} onChange={(e) => setSelectedRun(e.target.value)}>
            {runs.length === 0 ? <option>no runs</option> : null}
            {runs.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <select value={predictor} onChange={(e) => setPredictor(e.target.value as "heuristic" | "llm")}>
            <option value="heuristic">heuristic</option>
            <option value="llm">llm</option>
          </select>
          <button onClick={compact} disabled={!selectedRun || !!busy}>
            {busy === "compact" ? "Compacting…" : "Compact"}
          </button>
          <button onClick={evaluate} disabled={!selectedRun || !!busy}>
            {busy === "evaluate" ? "Checking…" : "Evaluate"}
          </button>
          <button className="primary" onClick={compare} disabled={!selectedRun || !!busy}>
            {busy === "compare" ? "Comparing…" : "Compare to screenshots"}
          </button>
        </div>
      </header>

      {observations.length ? (
        <Headline t={totals} />
      ) : (
        <p className="hint">
          {status === "offline"
            ? "Can't reach the API. Start the backend, then reload."
            : "Pick a run and press Compact to see how much page context BrowserDelta removes."}
        </p>
      )}

      {observations.length ? (
        <div className="layout">
          <nav className="steps">
            {observations.map((o) => {
              const raw = detail?.steps.find((s) => s.step === o.step);
              const replay = detail?.eval_report?.steps.find((s) => s.step === o.step);
              const selected = o.step === current?.step;
              return (
                <button
                  key={o.step}
                  className="step"
                  data-on={selected}
                  onClick={() => setSelectedStep(o.step)}
                >
                  <span className="step-head">
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
              <StepView
                runId={selectedRun}
                obs={current}
                raw={currentRaw}
                replay={currentReplay}
              />
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}

function Headline({ t }: { t: Totals }) {
  const hasEval = t.matched !== null && t.total !== null;
  return (
    <section className="headline">
      <div className="headline-copy">
        <h1>{hasEval ? "Same decisions, far less context." : "Far less context per step."}</h1>
        <p>
          {hasEval ? (
            <>
              The agent chose the correct next move <strong>{t.matched}</strong> of{" "}
              <strong>{t.total}</strong> times reading only BrowserDelta&rsquo;s text
              {t.baselineMatched !== null ? (
                <> — the same as full screenshots ({t.baselineMatched}/{t.total})</>
              ) : null}
              , while sending <strong>{t.reductionPct.toFixed(0)}% fewer tokens</strong>.
            </>
          ) : (
            <>
              Compacting replaces every screenshot with a few lines of text, cutting tokens by{" "}
              <strong>{t.reductionPct.toFixed(0)}%</strong>. Press Evaluate to confirm the agent
              still makes the right moves.
            </>
          )}
        </p>
      </div>
      <div className="headline-stats">
        <Stat
          big={t.reductionPct.toFixed(0) + "%"}
          label="fewer tokens"
          sub={`${t.compactTokens.toLocaleString()} vs ${t.baselineTokens.toLocaleString()}`}
          good
        />
        <Stat
          big={hasEval ? `${t.matched}/${t.total}` : "—"}
          label="correct moves"
          sub={
            hasEval
              ? t.baselineMatched !== null
                ? `screenshots: ${t.baselineMatched}/${t.total}`
                : "next action matched"
              : "run Evaluate"
          }
        />
      </div>
    </section>
  );
}

function Stat({
  big,
  label,
  sub,
  good,
}: {
  big: string;
  label: string;
  sub: string;
  good?: boolean;
}) {
  return (
    <div className="stat" data-good={!!good}>
      <span className="stat-big">{big}</span>
      <span className="stat-label">{label}</span>
      <span className="stat-sub">{sub}</span>
    </div>
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
      <div className="stage-head">
        <h2>{describeAction(raw?.action)}</h2>
        <span className="muted">Step {obs.step}</span>
      </div>

      <div className="compare">
        <article className="pane">
          <header>
            <span className="pane-title">A full screenshot sends this</span>
            <span className="pane-cost">≈ {obs.baseline_tokens_estimate.toLocaleString()} tokens</span>
          </header>
          <div className="pane-body shot">
            {screenshot ? (
              <img src={fileUrl(runId, screenshot)} alt={`Step ${obs.step} page`} loading="lazy" />
            ) : (
              <p className="muted pad">No screenshot recorded for this step.</p>
            )}
          </div>
        </article>

        <article className="pane accent">
          <header>
            <span className="pane-title">BrowserDelta sends this</span>
            <span className="pane-cost good">
              {obs.tokens_estimate.toLocaleString()} tokens · −{Math.round(obs.reduction_pct)}%
            </span>
          </header>
          <div className="pane-body">
            <pre className="obs">{obs.llm_observation}</pre>
            {crops.length ? (
              <div className="crops">
                <span className="muted">plus {crops.length} small crop{crops.length > 1 ? "s" : ""} of what changed:</span>
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

      {replay ? (
        <div className="outcome" data-pass={replay.passed}>
          <div className="outcome-row">
            <div className="move">
              <span className="muted">Correct next move</span>
              <strong>{describeAction(replay.expected_next_action)}</strong>
            </div>
            <span className="arrow">→</span>
            <div className="move">
              <span className="muted">Agent chose, from the text alone</span>
              <strong>{describeAction(replay.predicted_next_action)}</strong>
            </div>
            <span className="result">{replay.passed ? "Match" : "Miss"}</span>
          </div>
          {replay.rationale ? <p className="why">{replay.rationale}</p> : null}
        </div>
      ) : (
        <p className="hint small">Press Evaluate to see whether the agent picks the right next move from this text.</p>
      )}
    </>
  );
}

function Mark({ replay }: { replay?: ReplayStepResult }) {
  if (!replay) return <span className="mark none" title="not evaluated" />;
  return (
    <span className={`mark ${replay.passed ? "pass" : "fail"}`} title={replay.passed ? "correct move" : "wrong move"}>
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
  if (!a) return "unknown action";
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

createRoot(document.getElementById("root")!).render(<App />);
