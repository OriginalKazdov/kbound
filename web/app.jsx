/* Kazdov Spec — production UI
   Behavioral Specification Recovery for AI Agents.
   In hosted mode, the dashboard serves prebaked outputs from prebakes.json
   for the 7 demo tasks; in local mode it can hit /spec/explain/text on a
   user-run FastAPI backend (see kazdov-spec README for `pip install`). */

const API_BASE = (window.KZ_API_BASE || "http://localhost:8765");
const HOSTED_MODE =
  typeof window !== "undefined" &&
  window.location.hostname !== "localhost" &&
  !window.location.hostname.startsWith("127.");

const Mark = ({ size = 18 }) => (
  <svg className="kz-logo-mark" width={size} height={size}>
    <use href="#kz-mark" />
  </svg>
);

/* ----------------- demo tasks (self-consistent, solvable by backend) ---- */

const DEMO_TASKS = [
  { id: "shard_routing", label: "Customer-shard router", short: "Shard router",
    family: "linear_residual_policy",
    description: "Deployed agent assigning customer_id to one of 7 DB shards via a modular hash. Recover the routing rule.",
    code: "# 8 traces from a deployed shard-routing agent (customer_id → shard)\n17 → 4\n22 → 5\n41 → 6\n92 → 5\n 3 → 4\n55 → 6\n12 → 3\n 9 → 1\n50 → ?" },
  { id: "bucket_assignment", label: "A/B bucket assigner", short: "A/B bucket",
    family: "linear_residual_policy",
    description: "Deployed agent that assigns user_id to one of 11 experiment buckets for staged rollout. Recover the bucket rule.",
    code: "# 8 traces from an A/B bucket assigner (user_id → bucket 0-10)\n10 → 1\n20 → 9\n30 → 6\n40 → 3\n50 → 0\n70 → 5\n80 → 2\n90 → 10\n100 → ?" },
  { id: "dedup_hash", label: "Dedup hash router", short: "Dedup hash",
    family: "polynomial_threshold_rule",
    description: "Content-dedup agent routing record_id to one of 11 dedup partitions via a polynomial hash. Recover the hash function.",
    code: "# 8 traces from a dedup hash router (record_id → partition 0-10)\n0 → 5\n1 → 10\n2 → 8\n3 → 10\n4 → 5\n6 → 7\n7 → 3\n9 → 7\n12 → ?" },
  { id: "modular_hash", label: "Modular shard router (large)", short: "Hash routing",
    family: "linear_residual_policy",
    description: "Hash-based shard routing — same family as customer-shard router, different parameters.",
    code: "# Database shard router (user_id → shard)\n10 → 1\n20 → 9\n30 → 6\n40 → 3\n50 → 0\n70 → 5\n80 → 2\n90 → 10\n100 → ?" },
  { id: "rsa_primitive", label: "RSA-style primitive", short: "RSA primitive",
    family: "exponential_pattern_rule",
    description: "Exponentiation pattern — used in custom signature/encryption primitives.",
    code: "# Modular exponentiation observations (input → output)\n2 → 9\n3 → 5\n4 → 4\n5 → 1\n6 → 3\n8 → 5\n9 → 4\n10 → 1\n7 → ?" },
  { id: "boolean_gate", label: "Binary decision gate", short: "Boolean gate",
    family: "binary_decision_gate",
    description: "Two-input boolean truth-table — feature-flag, allow/deny logic.",
    code: "# Two-feature binary decision\n(0,0) → 0\n(0,1) → 1\n(1,0) → 1\n(1,1) → 0\n(0,0) → 0\n(1,0) → 1\n(0,1) → 1\n(1,1) → 0\n(1,1) → ?" },
  { id: "linear_threshold", label: "Spatial threshold", short: "Threshold",
    family: "spatial",
    description: "Linear threshold rule — agent routed to LLM when no algebraic family fits.",
    code: "# Spatial example — routes to LLM fallback\n42 → 0\n85 → 1\n60 → 1\n50 → 0\n95 → 1\n38 → 0\n70 → 1\n55 → 0\n100 → ?" },
];

/* Static placeholder trace shown on first paint. */
const PLACEHOLDER_STAGES = [
  { step: 1, name: "Geometry Classification", status: "idle", elapsed_ms: null,
    summary: "Press Recover to analyze agent traces.",
    details: { hint: "Edit the traces above or pick a demo, then press Recover (or ⌘/Ctrl + Enter)." }
  },
  { step: 2, name: "Operator Detection",    status: "idle", elapsed_ms: null, summary: "—", details: null },
  { step: 3, name: "Spec Synthesis",        status: "idle", elapsed_ms: null, summary: "—", details: null },
  { step: 4, name: "Support Re-check",      status: "idle", elapsed_ms: null, summary: "—", details: null },
  { step: 5, name: "Recovered Spec",        status: "idle", elapsed_ms: null, summary: "—", details: null },
];

const COMPARISON_ROWS = [
  { model: "Kazdov Spec",       accuracy: "100%", mark: "✓", latency: "—",    cost: "~$0.0004*", verdict: "verified", primary: true },
  { model: "Claude Sonnet 4.6", accuracy: "17%",  mark: "✗", latency: "4.2s", cost: "$0.0210" },
  { model: "Claude Haiku 4.5",  accuracy: "20%",  mark: "✗", latency: "1.8s", cost: "$0.0030" },
];

const FAMILIES = [
  { id: "linear_residual_policy",       name: "Linear Residual Policy" },
  { id: "polynomial_threshold_rule",    name: "Polynomial Threshold Rule" },
  { id: "scaling_residual_rule",        name: "Scaling Residual Rule" },
  { id: "inverse_residual_rule",        name: "Inverse Residual Rule" },
  { id: "exponential_pattern_rule",     name: "Exponential Pattern Rule" },
  { id: "additive_composition_rule",    name: "Additive Composition Rule" },
  { id: "linear_recurrence_policy",     name: "Linear Recurrence Policy" },
  { id: "binary_decision_gate",         name: "Binary Decision Gate" },
  { id: "k_bit_parity_rule",            name: "k-Bit Parity Rule" },
  { id: "cubic_threshold_rule",         name: "Cubic Threshold Rule" },
];
const MODELS = ["Kazdov", "Sonnet 4.6", "Haiku 4.5"];
const HEATMAP = [
  [100,  17,  20],
  [100,  37,  37],
  [100,   7,  17],
  [100,  89,  83],
  [ 97,  67,  70],
  [ 95, null, null],
  [100,  13,  17],
  [100,  40,  20],
  [100,  97, 100],
  [100,  50,  50],
];

/* ----------------- primitives ---- */

function StatusPill({ kind, label }) {
  const map = {
    ok:    { fg: "var(--ok)",     ch: "✓" },
    warn:  { fg: "var(--warn)",   ch: "⚠" },
    err:   { fg: "var(--err)",    ch: "✗" },
    info:  { fg: "var(--accent)", ch: "•" },
    idle:  { fg: "var(--muted)",  ch: "○" },
    skipped:{fg: "var(--muted)",  ch: "·" },
    failed:{ fg: "var(--err)",    ch: "✗" },
  };
  const v = map[kind] || map.idle;
  return (
    <span className="kz-pill" style={{ color: v.fg }}>
      <span style={{ marginRight: 6 }}>{v.ch}</span>{label}
    </span>
  );
}

/* ----------------- code editor with line gutter ---- */

const EDITOR_PLACEHOLDER = "Paste K-shot rules, one per line:\n  17 → 4\n  22 → 5\n  ...\n  50 → ?\n# lines starting with # are ignored";

function CodeEditor({ value, onChange, onSubmit }) {
  const lines = value.split("\n");
  const taRef = React.useRef(null);
  const gutterRef = React.useRef(null);
  const onScroll = (e) => { if (gutterRef.current) gutterRef.current.scrollTop = e.target.scrollTop; };
  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      onSubmit && onSubmit();
    }
  };
  return (
    <div className="kz-editor">
      <div className="kz-editor-head">
        <span className="kz-editor-tab" id="kz-editor-label">rules.kz</span>
        <span className="kz-editor-meta">rules · {lines.length} {lines.length === 1 ? "line" : "lines"} · UTF-8</span>
      </div>
      <div className="kz-editor-body">
        <div className="kz-gutter" ref={gutterRef} aria-hidden="true">
          {lines.map((_, i) => <div key={i} className="kz-gutter-n">{String(i + 1).padStart(2, " ")}</div>)}
        </div>
        <textarea
          ref={taRef}
          spellCheck={false}
          className="kz-textarea"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onScroll={onScroll}
          onKeyDown={handleKeyDown}
          placeholder={EDITOR_PLACEHOLDER}
          aria-labelledby="kz-editor-label"
          aria-describedby="kz-editor-hint"
        />
      </div>
      <span id="kz-editor-hint" className="kz-sr-only">
        Agent traces editor. Format: one observation per line as "x → y", with the query as "x → ?". Press Cmd or Ctrl + Enter to recover.
      </span>
    </div>
  );
}

/* ----------------- pipeline stage card ---- */

function PipelineCard({ stage, expanded, onToggle, isPending }) {
  const status = stage.status || "idle";
  const time = stage.elapsed_ms != null ? `${Math.round(stage.elapsed_ms)}ms` : "—";
  const detailText = formatDetails(stage.details);
  const detailId = `kz-stage-detail-${stage.step}`;
  const cls = ["kz-stage"];
  if (expanded) cls.push("is-open");
  if (isPending) cls.push("is-pending");
  return (
    <div className={cls.join(" ")} data-status={status}>
      <button
        type="button"
        className="kz-stage-head"
        onClick={onToggle}
        aria-expanded={!!expanded}
        aria-controls={detailText ? detailId : undefined}
      >
        <span className="kz-stage-n" aria-hidden="true">{String(stage.step).padStart(2, "0")}</span>
        <span className="kz-stage-name">{stage.name}</span>
        <span className="kz-stage-spacer" />
        <span className="kz-stage-time" aria-label={time !== "—" ? `elapsed ${time}` : undefined}>{time}</span>
        <StatusPill kind={status} label={status} />
        <span className="kz-stage-caret" aria-hidden="true">{expanded ? "−" : "+"}</span>
      </button>
      <div className="kz-stage-summary">{stage.summary || "—"}</div>
      {expanded && detailText && <pre id={detailId} className="kz-stage-detail">{detailText}</pre>}
    </div>
  );
}

function formatDetails(d) {
  if (!d) return "";
  if (typeof d === "string") return d;
  return JSON.stringify(d, null, 2);
}

/* ----------------- comparison table ---- */

function ComparisonTable({ rows, showVerifiedBadge }) {
  return (
    <table className="kz-cmp" aria-label="Kazdov Spec vs frontier LLMs on this task">
      <thead>
        <tr>
          <th style={{ textAlign: "left" }} scope="col">Model</th>
          <th scope="col">Acc</th>
          <th scope="col">Latency</th>
          <th scope="col">$ / call</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.model} className={r.primary ? "is-primary" : ""}>
            <td className="kz-cmp-model">
              <span
                className="kz-cmp-mark"
                aria-label={r.mark === "✓" ? "passes" : "fails"}
                style={{ color: r.mark === "✓" ? "var(--ok)" : "var(--err)" }}
              >{r.mark}</span>
              <span>{r.model}</span>
              {r.primary && showVerifiedBadge && (
                <span className="kz-cmp-badge" title="Recovered formula re-checked against the support set for this task; not a global accuracy claim.">verified</span>
              )}
            </td>
            <td className="kz-num">{r.accuracy}</td>
            <td className="kz-num">{r.latency}</td>
            <td className="kz-num">{r.cost}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ----------------- capability heatmap ---- */

function CapabilityMatrix() {
  const cell = (v, isKazdov) => {
    if (v === null || v === undefined) {
      return {};
    }
    const f = v / 100;
    if (isKazdov) {
      const a = 0.08 + f * 0.85;
      return { background: `rgba(0,82,204,${a.toFixed(3)})`, color: f > 0.6 ? "#fff" : "var(--fg)" };
    }
    const a = 0.04 + f * 0.55;
    return { background: `rgba(10,10,10,${a.toFixed(3)})`, color: f > 0.55 ? "#fff" : "var(--fg)" };
  };
  return (
    <div className="kz-heatmap">
      <div
        className="kz-heatmap-grid"
        role="table"
        aria-label="Capability matrix — accuracy by family and model"
        style={{ gridTemplateColumns: `minmax(220px,1.6fr) repeat(${MODELS.length}, 1fr)` }}
      >
        <div className="kz-heatmap-corner" role="columnheader">family × model</div>
        {MODELS.map(m => <div key={m} role="columnheader" className={"kz-heatmap-colh" + (m === "Kazdov" ? " is-accent" : "")}>{m}</div>)}
        {FAMILIES.map((f, ri) => (
          <React.Fragment key={f.id}>
            <div className="kz-heatmap-rowh" role="rowheader">
              <span>{f.name}</span>
              <span style={{ marginLeft: 8, color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 11 }}>({f.id})</span>
            </div>
            {HEATMAP[ri].map((v, ci) => {
              const isEmpty = v === null || v === undefined;
              return (
                <div
                  key={ci}
                  role="cell"
                  className={"kz-heatmap-cell" + (isEmpty ? " is-empty" : "")}
                  style={cell(v, MODELS[ci] === "Kazdov")}
                  title={isEmpty ? "no measurement" : `${MODELS[ci]} on ${f.name}: ${v}% accuracy`}
                  aria-label={isEmpty ? `${MODELS[ci]} on ${f.name}: no measurement` : `${MODELS[ci]} on ${f.name}: ${v} percent`}
                >
                  {isEmpty ? "—" : v}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
      <div className="kz-heatmap-legend">
        <span>Measured accuracy (%) · n=30 episodes per family</span>
        <span className="kz-heatmap-legend-key">
          <span className="kz-heatmap-legend-swatch" aria-hidden="true" /> = no measurement
        </span>
      </div>
    </div>
  );
}

/* ----------------- cost calculator ---- */

function CostCalculator() {
  const [calls, setCalls] = React.useState(50000);
  const [llmCost, setLlmCost] = React.useState(0.021);
  const kazCost = 0.0004;
  const llmTotal = calls * llmCost;
  const kazTotal = calls * kazCost;
  const saved = llmTotal - kazTotal;
  const pct = saved / llmTotal;
  const callsFill = ((calls - 1000) / (1000000 - 1000)) * 100;
  const costFill = ((llmCost - 0.001) / (0.05 - 0.001)) * 100;
  return (
    <div className="kz-calc">
      <div className="kz-calc-controls">
        <div className="kz-calc-row">
          <label htmlFor="kz-calc-calls">Calls per month</label>
          <div className="kz-calc-slider">
            <input
              id="kz-calc-calls"
              type="range" min="1000" max="1000000" step="1000"
              value={calls} onChange={e => setCalls(+e.target.value)}
              aria-valuetext={`${calls.toLocaleString()} calls per month`}
              style={{ "--kz-fill": `${callsFill}%` }}
            />
            <span className="kz-num">{calls.toLocaleString()}</span>
          </div>
        </div>
        <div className="kz-calc-row">
          <label htmlFor="kz-calc-llmcost">LLM cost / call</label>
          <div className="kz-calc-slider">
            <input
              id="kz-calc-llmcost"
              type="range" min="0.001" max="0.05" step="0.0005"
              value={llmCost} onChange={e => setLlmCost(+e.target.value)}
              aria-valuetext={`$${llmCost.toFixed(4)} per call`}
              style={{ "--kz-fill": `${costFill}%` }}
            />
            <span className="kz-num">${llmCost.toFixed(4)}</span>
          </div>
        </div>
      </div>
      <div className="kz-calc-out">
        <div className="kz-calc-cell">
          <div className="kz-calc-k">LLM-only</div>
          <div className="kz-calc-v kz-num">${llmTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}<span className="kz-calc-u">/mo</span></div>
        </div>
        <div className="kz-calc-cell">
          <div className="kz-calc-k">Kazdov (compute est.)</div>
          <div className="kz-calc-v kz-num">${kazTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}<span className="kz-calc-u">/mo</span></div>
        </div>
        <div className="kz-calc-cell is-accent">
          <div className="kz-calc-k">Saved</div>
          <div className="kz-calc-v kz-num">${saved.toLocaleString(undefined, { maximumFractionDigits: 0 })}<span className="kz-calc-u"> · {(pct * 100).toFixed(1)}%</span></div>
        </div>
      </div>
    </div>
  );
}

/* ----------------- top nav ---- */

const REPO_URL = "https://github.com/OriginalKazdov/kazdov-spec";

function TopNav({ dark, onToggleDark }) {
  return (
    <header className="kz-nav" role="banner">
      <div className="kz-nav-l">
        <span className="kz-logo">
          <Mark size={18} />
          <span className="kz-logo-text">kazdov<span style={{ opacity: 0.5 }}>/spec</span></span>
        </span>
        <span className="kz-nav-tag">v0.1 · research preview</span>
      </div>
      <nav className="kz-nav-c" aria-label="Primary">
        <a href="#dashboard">demo</a>
        <a href="#how">how it works</a>
        <a href="#case-study">12% case</a>
        <a href="#drift">drift diff</a>
        <a href="#pricing">pricing</a>
        <a href="#pilot">pilot</a>
      </nav>
      <div className="kz-nav-r">
        <button
          type="button"
          className="kz-nav-btn"
          onClick={onToggleDark}
          aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
          aria-pressed={dark}
        >
          <span aria-hidden="true">{dark ? "☼ light" : "☾ dark"}</span>
        </button>
      </div>
    </header>
  );
}

/* ----------------- hero ---- */

function Hero() {
  return (
    <div className="kz-hero">
      <div className="kz-hero-kicker">RESEARCH PREVIEW · BEHAVIORAL SPECIFICATION RECOVERY</div>
      <h1 className="kz-hero-h">
        Recover the policy your AI agent is actually following.<br />
        <span className="kz-hero-h-2">K=16 observations in. Executable spec out. Audit-grade.</span>
      </h1>
      <div className="kz-hero-sub">
        Kazdov Spec classifies an agent's decision pattern from observed input/output traces,
        dispatches it to a typed-operator solver, and re-checks the recovered specification
        against the full support set. The output is an executable policy your audit team can
        attach to a model-risk submission — Markdown for humans, YAML for machines.
      </div>
      <div className="kz-hero-ctas">
        <a href="#dashboard">try the demo →</a>
        <a href="#how">how it works ↓</a>
      </div>
    </div>
  );
}

/* ----------------- dashboard (the main thing) ---- */

const DEFAULT_OPEN = { 1: false, 2: false, 3: false, 4: false, 5: false };
const FETCH_TIMEOUT_MS = 20000;

function Dashboard() {
  const [task, setTask] = React.useState(DEMO_TASKS[0]);
  const [code, setCode] = React.useState(DEMO_TASKS[0].code);
  const [open, setOpen] = React.useState(DEFAULT_OPEN);
  const [running, setRunning] = React.useState(false);
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [prebakes, setPrebakes] = React.useState(null);
  const abortRef = React.useRef(null);
  const reqIdRef = React.useRef(0);

  // Load prebakes once on mount (used in hosted mode + as fallback)
  React.useEffect(() => {
    fetch("./prebakes.json")
      .then(r => (r.ok ? r.json() : null))
      .then(setPrebakes)
      .catch(() => setPrebakes(null));
  }, []);

  const stages = result ? result.stages : PLACEHOLDER_STAGES;

  const supportPairCount = React.useMemo(() => (
    code.split("\n").filter(l => {
      const s = l.trim();
      if (!s || s.startsWith("#")) return false;
      if (s.includes("?")) return false;
      return s.includes("→") || s.includes("->") || s.includes("=>") || s.includes("=");
    }).length
  ), [code]);

  const hasQueryLine = React.useMemo(() => code.includes("?"), [code]);
  const canCompile = !running && supportPairCount >= 2 && hasQueryLine;
  const compileBlockedReason = !code.trim()
    ? "editor is empty"
    : supportPairCount < 2
      ? "need at least 2 support pairs (lines like 'x → y')"
      : !hasQueryLine
        ? "need a query line like 'x → ?'"
        : null;

  const pickTask = React.useCallback((t) => {
    if (running) return; // ignore during run
    if (abortRef.current) abortRef.current.abort();
    setTask(t);
    setCode(t.code);
    setResult(null);
    setError(null);
    setOpen(DEFAULT_OPEN);
  }, [running]);

  const clearAll = React.useCallback(() => {
    if (running) return;
    if (abortRef.current) abortRef.current.abort();
    setCode("");
    setResult(null);
    setError(null);
    setOpen(DEFAULT_OPEN);
  }, [running]);

  const compile = React.useCallback(async () => {
    if (!canCompile) return;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const myReqId = ++reqIdRef.current;

    setRunning(true);
    setError(null);

    // Detect if the current code is one of the 7 demo tasks (unmodified).
    const matchedDemo = DEMO_TASKS.find(t => t.code === code);
    const canUsePrebake = matchedDemo && prebakes && prebakes[matchedDemo.id];

    if (HOSTED_MODE || canUsePrebake) {
      // Hosted demo: serve prebaked outputs. Custom traces redirect to install path.
      if (canUsePrebake) {
        // Mimic the engine's actual elapsed time so the rendered "elapsed
        // Xms" stat matches the perceived delay. Floor 200ms (so instant
        // demos feel tangible), ceiling 2500ms (so slow ones don't drag).
        const realMs = prebakes[matchedDemo.id].elapsed_ms || 400;
        const fakeMs = Math.min(2500, Math.max(200, realMs));
        // Cancellable wait — respects user abort or task switch.
        try {
          await new Promise((resolve, reject) => {
            const t = setTimeout(resolve, fakeMs);
            controller.signal.addEventListener("abort", () => {
              clearTimeout(t);
              reject(new DOMException("aborted", "AbortError"));
            });
          });
        } catch (e) {
          if (e && e.name === "AbortError") {
            if (myReqId === reqIdRef.current) setRunning(false);
            return;
          }
          throw e;
        }
        if (myReqId !== reqIdRef.current) return;
        setResult(prebakes[matchedDemo.id]);
        setOpen({ 1: false, 2: false, 3: true, 4: true, 5: true });
      } else {
        if (myReqId !== reqIdRef.current) return;
        setError("hosted-custom-trace");
        setResult(null);
      }
      if (myReqId === reqIdRef.current) setRunning(false);
      return;
    }

    // Local mode: hit the user's running FastAPI.
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, FETCH_TIMEOUT_MS);

    try {
      const res = await fetch(`${API_BASE}/spec/explain/text`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: code }),
        signal: controller.signal,
      });
      if (myReqId !== reqIdRef.current) return;
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      if (myReqId !== reqIdRef.current) return;
      setResult(data);
      setOpen({ 1: false, 2: false, 3: true, 4: true, 5: data.answer != null });
    } catch (e) {
      if (myReqId !== reqIdRef.current) return;
      if (e.name === "AbortError" && timedOut) {
        setError("Request timed out after 20 seconds. The backend may be busy or stuck on a search-heavy family.");
      } else if (e.name === "AbortError") {
        return;
      } else if (e instanceof TypeError && /fetch/i.test(e.message)) {
        setError(`backend-down:${API_BASE}`);
      } else {
        setError(e.message || String(e));
      }
      setResult(null);
    } finally {
      clearTimeout(timeout);
      if (myReqId === reqIdRef.current) setRunning(false);
    }
  }, [code, canCompile, prebakes]);

  // Cmd/Ctrl+Enter shortcut anywhere on the page
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        compile();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [compile]);

  // Cancel in-flight request on unmount
  React.useEffect(() => () => abortRef.current?.abort(), []);

  const finalAnswer = result
    ? (result.answer != null
        ? `answer = ${formatVal(result.answer)}`
        : "answer = null · solver could not satisfy all support pairs")
    : "Press Recover to synthesize the agent's policy and predict the held-out value.";
  const verified = result?.verified;
  const hasAnswer = result && result.answer != null;
  const isFailed = result && !hasAnswer;
  const isWarn = hasAnswer && !verified;
  const finalClass = ["kz-final"];
  if (!result) finalClass.push("is-pending");
  else if (isFailed) finalClass.push("is-failed");
  else if (isWarn) finalClass.push("is-warn");

  const finalSubL = result
    ? `${result.final.geometry || "—"} · ${result.final.family_label || "—"} · ${result.final.solver_used || "—"}`
    : "ready — pipeline not yet run";
  const finalSubR = result
    ? `derived in ${Math.round(result.elapsed_ms)}ms`
    : "—";

  const traceId = result ? mkTraceId(result) : "—";
  const supportCount = supportPairCount;
  const auditValue = result?.verified ? `${supportCount}/${supportCount} ✓` : "—";

  const cmpRows = result
    ? COMPARISON_ROWS.map(r => r.primary
        ? { ...r, latency: `${Math.round(result.elapsed_ms)}ms`, accuracy: result.verified ? "100%" : "—" }
        : r)
    : COMPARISON_ROWS;

  const renderError = () => {
    if (!error) return null;
    const isBackendDown = error.startsWith("backend-down:");
    const isHostedCustom = error === "hosted-custom-trace";
    return (
      <div className="kz-error" role="alert">
        <div className="kz-error-head">
          <span aria-hidden="true">{isHostedCustom ? "ℹ" : "✗"}</span>
          <span>{isHostedCustom ? "Run on your own traces — install locally" : isBackendDown ? "Backend unreachable" : "Recovery failed"}</span>
        </div>
        {isHostedCustom ? (
          <>
            <div>Custom traces require a local backend in this hosted preview.</div>
            <div className="kz-error-hint">
              Install the engine and run on your own JSONL trace logs:<br/>
              <code style={{display:"inline-block",marginTop:6}}>pip install kazdov-spec</code><br/>
              <code style={{display:"inline-block",marginTop:6}}>kazdov-spec recover --logs your_trace.jsonl</code><br/>
              Or apply for the design partner pilot — we run it on your traces for free.
            </div>
          </>
        ) : isBackendDown ? (
          <>
            <div>Could not reach <code>{API_BASE}</code>.</div>
            <div className="kz-error-hint">
              The backend FastAPI server may not be running. Start it with:<br/>
              <code style={{display:"inline-block",marginTop:6}}>uvicorn induction_compiler.kazdov_spec.api.spec_app:app --port 8765</code>
            </div>
          </>
        ) : (
          <div style={{wordBreak:"break-word"}}>{error}</div>
        )}
        <div className="kz-error-actions">
          {!isHostedCustom && <button type="button" onClick={compile} disabled={running}>retry</button>}
          {isHostedCustom && (
            <a href="#pilot" onClick={() => setError(null)} style={{padding:"6px 14px",border:"1px solid currentColor",borderRadius:4,textDecoration:"none"}}>apply for pilot</a>
          )}
          <button type="button" onClick={() => setError(null)}>dismiss</button>
        </div>
      </div>
    );
  };

  return (
    <section id="dashboard" className="kz-dash" aria-label="Spec recovery dashboard">
      <h2 className="kz-sr-only">Spec recovery</h2>
      <div className="kz-dash-bar">
        <div className="kz-dash-bar-l">
          <span className="kz-dash-title">spec</span>
          <span className="kz-crumb">/</span>
          <span className="kz-crumb-mono">{result ? `trace ${traceId}` : "ready"}</span>
        </div>
        <div className="kz-dash-bar-r">
          <span className="kz-stat">elapsed <span className="kz-num">{result ? Math.round(result.elapsed_ms) + "ms" : "—"}</span></span>
          <span className="kz-stat">solver <span className="kz-num">{shortSolver(result?.final?.solver_used)}</span></span>
          <span className="kz-stat">support re-check <span className="kz-num">{auditValue}</span></span>
          <button type="button" className="kz-btn-ghost" onClick={clearAll} disabled={running}>clear</button>
          <button
            type="button"
            className="kz-btn"
            onClick={compile}
            disabled={!canCompile}
            aria-busy={running}
            aria-keyshortcuts="Control+Enter Meta+Enter"
            title={compileBlockedReason || "Recover (⌘/Ctrl + Enter)"}
          >
            {running ? "recovering…" : "recover ▸"}
          </button>
        </div>
      </div>

      {running && <div className="kz-loading-bar" role="progressbar" aria-label="Compiling pipeline" aria-busy="true" />}

      <div className={"kz-grid" + (running ? " is-running" : "")}>
        {/* LEFT — input */}
        <div className="kz-col-l">
          <div className="kz-panel-h">
            <span>01 · agent traces</span>
            <span className="kz-panel-h-r">k-shot rules</span>
          </div>
          <CodeEditor value={code} onChange={setCode} onSubmit={compile} />
          <div className="kz-chips-h">demos</div>
          <div className="kz-chips" role="group" aria-label="Demo tasks">
            {DEMO_TASKS.map(t => (
              <button
                type="button"
                key={t.id}
                className={"kz-chip" + (task.id === t.id ? " is-on" : "")}
                onClick={() => pickTask(t)}
                disabled={running}
                title={t.description}
                aria-pressed={task.id === t.id}
              >
                <span className="kz-chip-d">{t.short || t.label}</span>
                <span className="kz-chip-f"><i>{t.family}</i></span>
              </button>
            ))}
          </div>
          <div className="kz-meta-rows" aria-label="Run summary">
            <div><span>support pairs</span><span className="kz-num">{supportPairCount}</span></div>
            <div><span>geometry</span><span className={"kz-num " + (result?.final?.geometry === "spatial" ? "is-spatial" : "is-algebraic")}>{result?.final?.geometry || "—"}</span></div>
            <div><span>family</span><span className="kz-num">{result?.final?.family || "—"}</span></div>
            <div><span>solver</span><span className="kz-num">{shortSolver(result?.final?.solver_used)}</span></div>
          </div>
        </div>

        {/* CENTER — pipeline */}
        <div className="kz-col-c">
          <div className="kz-panel-h">
            <span>02 · recovery pipeline</span>
            <span className="kz-panel-h-r">5 stages{result ? ` · ${Math.round(result.elapsed_ms)}ms total` : ""}</span>
          </div>
          {renderError()}
          <div className="kz-stages" aria-live="polite" aria-atomic="false">
            {stages.map(s => (
              <PipelineCard
                key={s.step}
                stage={s}
                expanded={!!open[s.step]}
                isPending={!result && s.step > 1}
                onToggle={() => setOpen(o => ({ ...o, [s.step]: !o[s.step] }))}
              />
            ))}
          </div>
          <div className={finalClass.join(" ")} role="status" aria-live="polite">
            <div className="kz-final-h">
              <span>final answer</span>
              <span className="kz-final-h-r">
                {result
                  ? <><StatusPill kind={verified ? "ok" : (hasAnswer ? "warn" : "err")}
                       label={verified ? "verified" : (hasAnswer ? "low-confidence" : "failed")} />
                      <span aria-hidden="true">·</span>
                      <span>{result.final.geometry === "spatial" ? "LLM fallback" : "symbolic solver"}</span></>
                  : <StatusPill kind="idle" label="ready" />}
              </span>
            </div>
            <div className="kz-final-eq">{finalAnswer}</div>
            <div className="kz-final-foot">
              <span>{finalSubL}</span>
              <span>{finalSubR}</span>
            </div>
          </div>
        </div>

        {/* RIGHT — comparison + sticky */}
        <div className="kz-col-r">
          <div className="kz-panel-h">
            <span>03 · vs. frontier LLMs</span>
            <span className="kz-panel-h-r">same task</span>
          </div>
          <ComparisonTable rows={cmpRows} showVerifiedBadge={!!result?.verified} />
          <div className="kz-cmp-caption">
            Numbers shown for the linear residual policy family from <a href={REPO_URL} target="_blank" rel="noopener noreferrer">paper #1</a> (n=30 episodes per model). The Kazdov row's latency updates with the current run.<br/>
            <span style={{opacity: 0.75}}>* Kazdov cost is an order-of-magnitude estimate of local compute. No commercial tier exists.</span>
          </div>
          <div className="kz-sub">
            <div className="kz-sub-h">use the API</div>
            <div className="kz-sub-caption">Run on your own traces locally with the open-source CLI.</div>
            <pre className="kz-codeblock">{`$ pip install kazdov-spec
$ kazdov-spec recover \\
    --logs your_trace.jsonl`}</pre>
            <a href={REPO_URL + "#install"} target="_blank" rel="noopener noreferrer" className="kz-sub-link">→ install locally (README)</a>
          </div>
          <div className="kz-sub">
            <div className="kz-sub-h">routing decision</div>
            <div className="kz-route">
              <span>geometry</span><span className="kz-num">{result?.final?.geometry || "—"}</span>
            </div>
            <div className="kz-route">
              <span>route</span><span className="kz-num kz-accent">
                {result?.final?.geometry === "spatial" ? "LLM" : (result?.final?.geometry === "algebraic" ? "SYMBOLIC" : "—")}
              </span>
            </div>
            <div className="kz-route">
              <span>family</span><span className="kz-num">{result?.final?.family || "—"}</span>
            </div>
            {result?.final?.geometry === "algebraic" && (
              <div className="kz-route">
                <span>fallback</span><span className="kz-num">LLM (not invoked)</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function formatVal(v) {
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return JSON.stringify(v);
  return String(v);
}

function shortSolver(s) {
  if (!s) return "—";
  // "RCE-LCG (symbolic consistency search)" → "rce-lcg"
  // "LLM (claude-haiku-4-5)" → "llm:haiku-4-5"
  const m = s.match(/^([A-Za-z-]+)\s*\(?\s*(?:claude-)?([a-z0-9-]+)?/i);
  if (!m) return s.toLowerCase().split(" ")[0];
  if (m[1].toLowerCase() === "llm" && m[2]) return `llm:${m[2]}`;
  return m[1].toLowerCase();
}

function mkTraceId(result) {
  const ms = Math.round(result.elapsed_ms || 0);
  const fam = result.final?.operator?.key || result.final?.family_label || "x";
  const hex = ms.toString(16).padStart(4, "0");
  return `${fam.slice(0,3)}…${hex}`;
}

/* ----------------- how it works + footer ---- */

function HowItWorks() {
  const steps = [
    { n: "01", t: "Classify the agent's pattern",
      d: "Extract structural features from observed traces — output cardinality, modular-wrap signature, recurrence index, separability — and classify the rule as deterministic-recoverable or stochastic." },
    { n: "02", t: "Detect operator + synthesize spec",
      d: "Identify the typed operator family (linear residual, polynomial threshold, exponential pattern, binary gate, recurrence, etc.) and synthesize the executable specification. Composition search handles depth-2 layered rules." },
    { n: "03", t: "Re-check + emit audit certificate",
      d: "Re-verify the recovered specification against the full support set. Emit a signed certificate (Markdown + YAML) with the recovered rule, parameter values, and the support-set consistency score. The held-out value is then predicted from the recovered spec." },
  ];
  return (
    <section id="how">
      <div className="kz-section-h">
        <span className="kz-section-n">04</span>
        <h2>how it works</h2>
        <span className="kz-section-r">three stages</span>
      </div>
      <div className="kz-how">
        <div className="kz-how-grid">
          {steps.map(s => (
            <div key={s.n} className="kz-how-cell">
              <div className="kz-how-n">{s.n}</div>
              <div className="kz-how-t">{s.t}</div>
              <div className="kz-how-d">{s.d}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ----------------- case study: 12% Claude finding ---- */

function CaseStudy12pct() {
  return (
    <section id="case-study" className="kz-case">
      <div className="kz-section-h">
        <span className="kz-section-n">07</span>
        <h2>case study · vendor compliance verification</h2>
        <span className="kz-section-r">live LLM accountability</span>
      </div>
      <div className="kz-case-grid">
        <div className="kz-case-l">
          <h3 className="kz-case-h">
            We told a frontier LLM to follow a formula.<br />
            <span className="kz-case-h-2">It complied 12.5% of the time.</span>
          </h3>
          <p className="kz-case-p">
            We pointed Kazdov Spec at a real production LLM running under a system
            prompt that explicitly commanded it to compute a fixed arithmetic rule.
            Across 40 trace observations, the model honored the declared rule on
            only 5 outputs.
          </p>
          <p className="kz-case-p">
            The engine returned <code>no_recovery</code> and computed agreement
            against the vendor&apos;s own declared spec. The vendor&apos;s claim
            was empirically falsified, with the trace attached as evidence.
          </p>
          <p className="kz-case-p">
            Every AI vendor contract you renew without behavioral verification is
            an unaudited attestation. The compliance primitive turns trace logs
            into a falsifiable contract artifact.
          </p>
        </div>
        <div className="kz-case-r">
          <div className="kz-case-stat">
            <div className="kz-case-stat-v kz-num">12.5%</div>
            <div className="kz-case-stat-l">claimed-rule compliance</div>
          </div>
          <div className="kz-case-stat">
            <div className="kz-case-stat-v kz-num">5 / 40</div>
            <div className="kz-case-stat-l">observations matching the declared formula</div>
          </div>
          <div className="kz-case-stat">
            <div className="kz-case-stat-v kz-num">0</div>
            <div className="kz-case-stat-l">model-weight access required</div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ----------------- drift detection (kazdov diff) ---- */

function DriftDetection() {
  const [diff, setDiff] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    fetch("./diff_prebake.json")
      .then(r => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then(setDiff)
      .catch(e => setError(String(e)));
  }, []);

  if (error) {
    return (
      <section id="drift" className="kz-drift" style={{ scrollMarginTop: 80 }}>
        <div className="kz-section-h">
          <span className="kz-section-n">08</span>
          <h2>drift detection — kazdov diff</h2>
          <span className="kz-section-r">missing prebake</span>
        </div>
        <div className="kz-error" style={{ margin: "0 32px" }}>
          Could not load <code>diff_prebake.json</code>: {error}
        </div>
      </section>
    );
  }

  if (!diff) {
    return (
      <section id="drift" className="kz-drift" style={{ scrollMarginTop: 80 }}>
        <div className="kz-section-h">
          <span className="kz-section-n">08</span>
          <h2>drift detection — kazdov diff</h2>
          <span className="kz-section-r">loading...</span>
        </div>
      </section>
    );
  }

  const v1 = diff.v1;
  const v2 = diff.v2;
  const div = diff.behavioral_divergence;
  const familyChanged = diff.family_changed;
  const fp = diff.fingerprint;

  return (
    <section id="drift" className="kz-drift" style={{ scrollMarginTop: 80 }}>
      <div className="kz-section-h">
        <span className="kz-section-n">08</span>
        <h2>drift detection — kazdov diff</h2>
        <span className="kz-section-r">git-blame for agent behavior</span>
      </div>
      <div className="kz-section-caption">
        Run <code>kazdov-spec diff --v1 trace_v1.jsonl --v2 trace_v2.jsonl</code> on
        two trace captures of the same agent at different times. The engine
        recovers the behavioral specification on each side and reports what
        changed — at the rule level, not just the metric level. Today no
        observability vendor gives you this output.
      </div>

      <div className="kz-drift-grid">
        {/* v1 vs v2 spec cards */}
        <div className="kz-drift-card">
          <div className="kz-drift-label">v1 trace</div>
          <div className="kz-drift-rule">{v1.decision_rule}</div>
          <div className="kz-drift-meta">
            <span>{v1.n_observations} obs</span>
            <span>·</span>
            <span>K={v1.k_used}</span>
            <span>·</span>
            <span>{v1.proof_status}</span>
          </div>
        </div>
        <div className="kz-drift-arrow" aria-hidden="true">→</div>
        <div className="kz-drift-card is-current">
          <div className="kz-drift-label">v2 trace</div>
          <div className="kz-drift-rule">{v2.decision_rule}</div>
          <div className="kz-drift-meta">
            <span>{v2.n_observations} obs</span>
            <span>·</span>
            <span>K={v2.k_used}</span>
            <span>·</span>
            <span>{v2.proof_status}</span>
          </div>
        </div>
      </div>

      <div className="kz-drift-deltas">
        <div className="kz-drift-deltas-h">parameter deltas</div>
        <table className="kz-drift-table">
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>parameter</th>
              <th>v1</th>
              <th>v2</th>
              <th>changed</th>
            </tr>
          </thead>
          <tbody>
            {(diff.parameter_deltas || []).map(d => (
              <tr key={d.name} className={d.changed ? "is-changed" : ""}>
                <td className="kz-mono">{d.name}</td>
                <td className="kz-num">{String(d.v1_value)}</td>
                <td className="kz-num">{String(d.v2_value)}</td>
                <td className="kz-num">
                  {d.changed
                    ? <span style={{ color: "var(--err)" }}>✗</span>
                    : <span style={{ color: "var(--ok)" }}>✓</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {div && (
        <div className="kz-drift-divergence">
          <div className="kz-drift-deltas-h">behavioral divergence</div>
          <div className="kz-drift-divergence-row">
            <div>
              <div className="kz-drift-stat-v kz-num">
                {div.predictions_diverging}/{div.inputs_compared}
              </div>
              <div className="kz-drift-stat-l">predictions diverging across the union of inputs</div>
            </div>
            <div>
              <div className="kz-drift-stat-v kz-num" style={{ color: "var(--err)" }}>
                {((div.predictions_diverging / Math.max(div.inputs_compared, 1)) * 100).toFixed(1)}%
              </div>
              <div className="kz-drift-stat-l">divergence rate</div>
            </div>
          </div>
        </div>
      )}

      <div className="kz-drift-action">
        <div className="kz-drift-deltas-h">recommended action</div>
        <div className="kz-drift-action-body">
          {familyChanged
            ? "Family changed between trace captures. Investigate model substitution, prompt rewrite, or environment change."
            : (diff.parameter_deltas || []).some(d => d.changed)
              ? "Parameters drifted within the same family. Investigate silent model update, configuration change, or prompt parameter edit."
              : "No structural or parametric drift detected."}
        </div>
        <div className="kz-drift-fp">
          diff fingerprint: <code>{fp}</code>
        </div>
      </div>
    </section>
  );
}

/* ----------------- pricing ---- */

function Pricing() {
  const tiers = [
    {
      name: "Design partner pilot",
      price: "Free",
      tag: "Limited to first 5 customers",
      bullets: [
        "1 production agent · ≤ 2,000 traces",
        "Recovered spec + K-bound certificate",
        "≥ 1 actionable finding delivered",
        "Co-authored case study",
        "Reference call rights",
      ],
      cta: { href: "#pilot", label: "Apply →" },
      featured: false,
    },
    {
      name: "Audit",
      price: "from $45K",
      tag: "One-shot · 4-week delivery",
      bullets: [
        "1 agent · audit-grade artifact",
        "spec.yaml + Markdown report",
        "Coverage report + non-compliance memo",
        "30-day Q&A with founder",
      ],
      cta: { href: "mailto:juandovzak@gmail.com?subject=Kazdov%20Spec%20%E2%80%94%20Audit%20inquiry", label: "Email us →" },
      featured: true,
    },
    {
      name: "Continuous & Enterprise",
      price: "Contact",
      tag: "Drift monitoring · multi-agent · SLAs",
      bullets: [
        "Quarterly / monthly re-runs",
        "Drift alerts + spec deltas",
        "Board-ready compliance pack",
        "On-prem container available",
      ],
      cta: { href: "mailto:juandovzak@gmail.com?subject=Kazdov%20Spec%20%E2%80%94%20Continuous%20%2F%20Enterprise%20inquiry", label: "Email us →" },
      featured: false,
    },
  ];
  return (
    <section id="pricing" className="kz-pricing">
      <div className="kz-section-h">
        <span className="kz-section-n">09</span>
        <h2>pricing</h2>
        <span className="kz-section-r">design partner free · audit anchor from $45K</span>
      </div>
      <div className="kz-pricing-grid">
        {tiers.map(t => (
          <div key={t.name} className={"kz-pricing-card" + (t.featured ? " is-featured" : "")}>
            <div className="kz-pricing-name">{t.name}</div>
            <div className="kz-pricing-price kz-num">{t.price}</div>
            <div className="kz-pricing-tag">{t.tag}</div>
            <ul className="kz-pricing-bullets">
              {t.bullets.map(b => <li key={b}>{b}</li>)}
            </ul>
            <a className="kz-pricing-cta" href={t.cta.href}>{t.cta.label}</a>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ----------------- design partner CTA ---- */

function DesignPartner() {
  const subj = "Kazdov%20Spec%20design%20partner%20pilot";
  const body =
    "Hello%20Juan%2C%0A%0AI%27m%20interested%20in%20the%20Kazdov%20Spec%20design%20partner%20pilot.%0A%0A" +
    "Company%3A%20%0AMy%20role%3A%20%0AAgent%28s%29%20we%27d%20audit%3A%20%0AVolume%20of%20available%20trace%20logs%3A%20%0A" +
    "Regulatory%20context%3A%20%28EU%20AI%20Act%20%2F%20SR%2011-7%20%2F%20NIST%20AI%20RMF%20%2F%20other%29%0A%0AThanks%2C";
  return (
    <section id="pilot" className="kz-pilot">
      <div className="kz-section-h">
        <span className="kz-section-n">10</span>
        <h2>apply for the design partner pilot</h2>
        <span className="kz-section-r">first 5 customers · free</span>
      </div>
      <div className="kz-pilot-card">
        <p>
          We are taking on the first 5 design partners at no cost. You bring
          500&ndash;2,000 anonymized trace logs from one production agent. We
          deliver a recovered spec, a K-bound certificate, a coverage report,
          and at least one actionable finding within four weeks. In exchange we
          ask for a co-authored case study and one reference call.
        </p>
        <p className="kz-pilot-fit">
          <strong>Best fit:</strong> VP of Trust &amp; Safety, Head of AI
          Procurement, or Director of Model Risk Management at a company with
          at least one LLM-powered agent in production exposed to AI Act / SR
          11-7 / NIST AI RMF obligations.
        </p>
        <div className="kz-pilot-actions">
          <a className="kz-pilot-cta" href={`mailto:juandovzak@gmail.com?subject=${subj}&body=${body}`}>
            Apply by email →
          </a>
          <span className="kz-pilot-note">replies within 48 hours</span>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="kz-footer" role="contentinfo">
      <div className="kz-footer-l">
        <Mark size={14} />
        <span>kazdov / spec</span>
        <span className="kz-footer-meta">© 2026 Juan Cruz Dovzak · MIT-licensed core</span>
      </div>
      <div className="kz-footer-r">
        <a href="#pilot">design partner pilot ↗</a>
        <a href={REPO_URL} target="_blank" rel="noopener noreferrer">github ↗</a>
        <a href={REPO_URL + "/blob/main/_research/kbound_framework/main.pdf"} target="_blank" rel="noopener noreferrer">paper ↗</a>
      </div>
    </footer>
  );
}

/* ----------------- root app ---- */

function useDarkMode() {
  const [dark, setDark] = React.useState(() => {
    try {
      const saved = localStorage.getItem("kz-theme");
      if (saved === "dark") return true;
      if (saved === "light") return false;
    } catch (_) {}
    if (typeof window !== "undefined" && window.matchMedia) {
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    return false;
  });
  React.useEffect(() => {
    document.body.classList.toggle("kz-dark", dark);
    try { localStorage.setItem("kz-theme", dark ? "dark" : "light"); } catch (_) {}
  }, [dark]);
  return [dark, () => setDark(d => !d)];
}

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { console.error("ErrorBoundary caught", err, info); }
  render() {
    if (this.state.err) {
      return (
        <div role="alert" style={{ padding: 32, fontFamily: "var(--mono)", fontSize: 13, color: "var(--err)", maxWidth: 720, margin: "48px auto" }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Something went wrong rendering this section.</div>
          <div style={{ wordBreak: "break-word", whiteSpace: "pre-wrap", color: "var(--fg)" }}>{String(this.state.err.message || this.state.err)}</div>
          <button type="button" onClick={() => window.location.reload()} className="kz-btn-ghost" style={{ marginTop: 16 }}>reload page</button>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  const [dark, toggleDark] = useDarkMode();
  return (
    <>
      <a href="#dashboard" className="kz-skip">skip to demo</a>
      <TopNav dark={dark} onToggleDark={toggleDark} />
      <main id="main">
        <Hero />
        <ErrorBoundary>
          <Dashboard />
        </ErrorBoundary>
        <HowItWorks />
        <div id="matrix" />
        <div className="kz-section-h">
          <span className="kz-section-n">05</span>
          <h2>capability matrix</h2>
          <span className="kz-section-r">families × models · accuracy %</span>
        </div>
        <CapabilityMatrix />
        <div id="cost" />
        <div className="kz-section-h">
          <span className="kz-section-n">06</span>
          <h2>cost intuition</h2>
          <span className="kz-section-r">illustrative — not pricing</span>
        </div>
        <div className="kz-section-caption">
          No commercial tier exists. The "Kazdov" cost shown is an order-of-magnitude estimate of
          local compute; the LLM cost uses Anthropic's published Sonnet 4.6 rate as a default.
          This calculator is for cost-model intuition only.
        </div>
        <CostCalculator />
        <ErrorBoundary>
          <CaseStudy12pct />
          <DriftDetection />
          <Pricing />
          <DesignPartner />
        </ErrorBoundary>
      </main>
      <Footer />
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
