import { useCallback, useEffect, useRef, useState } from "react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:5000";

const POLL_MS = 12000;

// Keys must match backend TELEMETRY_FIELDS / models.risk.PARAMETERS.
const TELEMETRY_FIELDS = [
  { key: "temperature_c", label: "Temp", unit: "°C", placeholder: "84" },
  { key: "pressure_psi", label: "Pressure", unit: "PSI", placeholder: "42" },
  { key: "runtime_hrs", label: "Runtime", unit: "hrs", placeholder: "1200" },
  { key: "vibration_mm_s", label: "Vibration", unit: "mm/s", placeholder: "3.1" },
];

export default function App() {
  const [tab, setTab] = useState("diagnose");
  const [query, setQuery] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [pipeline, setPipeline] = useState(null);
  const [telemetry, setTelemetry] = useState({});
  const [liveStages, setLiveStages] = useState([]);
  const timer = useRef(null);

  // Polled, not one-shot: if the backend dies mid-demo the header says so
  // within POLL_MS instead of every request just failing silently. Cheap —
  // every stage /health/pipeline reports is a cached lookup, not recomputation.
  const refreshPipeline = useCallback(() => {
    return fetch(`${API}/health/pipeline`)
      .then((r) => r.json())
      .then(setPipeline)
      .catch(() => setPipeline({ unreachable: true }));
  }, []);

  useEffect(() => {
    refreshPipeline();
    const id = setInterval(refreshPipeline, POLL_MS);
    return () => clearInterval(id);
  }, [refreshPipeline]);

  // A diagnosis takes ~8-9s on the demo laptop. Without a running counter that
  // reads as a hang, which is the worst thing that can happen in front of a jury.
  useEffect(() => {
    if (busy) {
      const started = Date.now();
      timer.current = setInterval(() => setElapsed((Date.now() - started) / 1000), 100);
    } else {
      clearInterval(timer.current);
    }
    return () => clearInterval(timer.current);
  }, [busy]);

  function onFile(e) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : null);
  }

  const hasTelemetry = Object.values(telemetry).some((v) => String(v ?? "").trim());

  async function onSubmit(e) {
    e.preventDefault();
    if (!query.trim() && !file && !hasTelemetry) {
      setError("Describe the symptom, attach a photo, enter telemetry — or any combination.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    setLiveStages([]);
    setElapsed(0);

    const fd = new FormData();
    fd.append("query", query);
    if (file) fd.append("image", file);
    for (const { key } of TELEMETRY_FIELDS) {
      const v = String(telemetry[key] ?? "").trim();
      if (v) fd.append(key, v);
    }

    try {
      const res = await fetch(`${API}/diagnose/stream`, { method: "POST", body: fd });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || d.error || `HTTP ${res.status}`);
      }
      if (!res.body) throw new Error("no-stream");

      // Parse SSE off the response body. EventSource can't be used here —
      // it's GET-only and this is a multipart POST.
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let finished = false;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const blocks = buf.split("\n\n");
        buf = blocks.pop() ?? "";           // keep the trailing partial block
        for (const block of blocks) {
          let ev = "message";
          let data = null;
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) ev = line.slice(6).trim();
            else if (line.startsWith("data:")) {
              try { data = JSON.parse(line.slice(5).trim()); } catch { /* ignore */ }
            }
          }
          if (!data) continue;
          if (ev === "stage") setLiveStages((s) => [...s, data]);
          else if (ev === "result") { setResult(data); finished = true; }
          else if (ev === "error") throw new Error(data.detail || data.error);
        }
      }
      if (!finished) throw new Error("The stream ended before a result arrived.");
    } catch (err) {
      // Insurance for a live demo: if streaming fails for any reason, fall
      // back to the plain endpoint rather than showing the user an error.
      try {
        const res2 = await fetch(`${API}/diagnose`, { method: "POST", body: fd });
        const d2 = await res2.json();
        if (!res2.ok) throw new Error(d2.detail || d2.error || `HTTP ${res2.status}`);
        setResult(d2);
      } catch (err2) {
        setError(err2.message || err.message);
      }
    } finally {
      setBusy(false);
    }
  }

  const risk = result?.overall_risk;
  const failedStages = (result?.stages ?? []).filter((s) => !s.ok);
  // No image supplied at all -> don't show a detection card; that's not an
  // empty state, there was simply nothing to detect on.
  const imageSkipped = (result?.stages ?? []).some((s) => s.name === "detection" && s.skipped);

  function reset() {
    setQuery("");
    setFile(null);
    setPreview(null);
    setTelemetry({});
    setResult(null);
    setError(null);
    setElapsed(0);
    const picker = document.getElementById("img");
    if (picker) picker.value = "";
  }

  return (
    <main className="wrap">
      <div className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M12 2 3 7v10l9 5 9-5V7z" stroke="#fff" strokeWidth="1.6"
                      strokeLinejoin="round" fill="rgba(255,255,255,.08)" />
                <path d="M12 2v20M3 7l9 5 9-5" stroke="#fff" strokeWidth="1.2"
                      strokeLinejoin="round" opacity=".75" />
              </svg>
            </span>
            <div>
              <h1>PRISM</h1>
              <p className="sub">Aircraft defect diagnosis, grounded in FAA maintenance manuals</p>
            </div>
          </div>
          <StatusPill p={pipeline} />
        </div>
      </div>

      <div className="content">
        <nav className="tabs" role="tablist">
          {[
            ["diagnose", "Diagnose"],
            ["manuals", "Manuals"],
            ["history", "Case History"],
            ["status", "System Status"],
          ].map(([id, labelText]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={`tab${tab === id ? " active" : ""}`}
              onClick={() => setTab(id)}
            >
              {labelText}
            </button>
          ))}
        </nav>

      {tab === "manuals" && <div className="narrow"><Manuals /></div>}
      {tab === "history" && <div className="narrow"><CaseHistory /></div>}
      {tab === "status" && (
        <div className="narrow"><SystemStatus p={pipeline} onRefresh={refreshPipeline} /></div>
      )}

      {tab === "diagnose" && <>
      {pipeline && <Readiness p={pipeline} />}

      <div className="split">
      <div className="col-input">
      <form onSubmit={onSubmit} className="card">
        <label htmlFor="q">Symptom description</label>
        <textarea
          id="q"
          rows={3}
          value={query}
          placeholder="e.g. Pitting corrosion on the landing gear strut, roughly 2mm deep."
          onChange={(e) => setQuery(e.target.value)}
        />

        <label htmlFor="img">Photo (optional)</label>
        <div className="file-row">
          <input id="img" type="file" accept="image/*" onChange={onFile} className="file-input-native" />
          <label htmlFor="img" className="file-btn">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M4 13.5V15a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 16 15v-1.5M10 13V4m0 0 3 3m-3-3-3 3"
                    stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Choose photo
          </label>
          <span className="file-name muted small">{file ? file.name : "No photo attached"}</span>
        </div>
        {preview && <img className="preview" src={preview} alt="Upload preview" />}
        {file && !query.trim() && (
          <p className="hint">
            A photo alone rarely produces a diagnosis — describe what you are seeing
            as well, so retrieval has something to search the manuals with.
          </p>
        )}

        <label>Live telemetry (optional)</label>
        <div className="telem-grid">
          {TELEMETRY_FIELDS.map(({ key, label: l, unit, placeholder }) => (
            <div className="telem-cell" key={key}>
              <input
                id={key}
                type="number"
                step="any"
                inputMode="decimal"
                value={telemetry[key] ?? ""}
                placeholder={placeholder}
                onChange={(e) => setTelemetry({ ...telemetry, [key]: e.target.value })}
              />
              <label htmlFor={key} className="telem-lbl">{l} <span>{unit}</span></label>
            </div>
          ))}
        </div>

        <button type="submit" disabled={busy}>
          {busy ? `Diagnosing… ${elapsed.toFixed(1)}s` : "Diagnose"}
        </button>
        {(result || error || query || file || hasTelemetry) && !busy && (
          <button type="button" className="secondary ghost full" onClick={reset}>
            Clear and start a new diagnosis
          </button>
        )}
        {busy && (
          <p className="muted small">
            Running detection, retrieval and local generation. Typically 8–10 seconds.
          </p>
        )}
      </form>

      {error && <div className="card err"><strong>Request failed.</strong> {error}</div>}
      </div>

      <div className="col-output">
      {busy && <LiveProgress stages={liveStages} elapsed={elapsed} />}
      {!result && !error && !busy && (
        <div className="card placeholder">
          <p className="muted">
            Results appear here — detected defects, risk score, the grounded
            diagnosis with its cited manual passages, and similar past cases.
          </p>
        </div>
      )}
      {result && (
        <>
          {result.risk_assessment
            ? <RiskPanel a={result.risk_assessment} />
            : risk && (
              <section className={`card risk risk-${risk.level.toLowerCase()}`}>
                <h2>Risk</h2>
                <p className="risk-level">{risk.level}</p>
                <p className="muted">{risk.rationale}</p>
                {risk.needs_human_review && (
                  <p className="review">Requires human review before any action.</p>
                )}
              </section>
            )}

          <section className="card">
            <h2>Diagnosis</h2>
            {result.refused ? (
              <p className="refused">
                The manuals do not cover this query. PRISM declined rather than guessing.
              </p>
            ) : result.needs_input ? (
              // Not a failure — there was simply nothing to work from. Saying so
              // plainly beats "No diagnosis produced", which reads like a crash.
              <p className="needs-input">{result.needs_input}</p>
            ) : (
              <p className="diagnosis">{result.diagnosis || "No diagnosis produced."}</p>
            )}
            {result.grounded === false && !result.refused && (
              <p className="warn">
                Retrieval found no confident passage — treat this answer with caution.
              </p>
            )}
            {result.cited_ok === false && (
              <p className="warn">
                This answer did not cite a retrieved source. Possible hallucination.
              </p>
            )}
            {result.citations?.length > 0 && (
              <p className="cites">
                Cited: {result.citations.map((c) => <code key={c}>{c}</code>)}
              </p>
            )}
            {!result.refused && !result.needs_input && result.diagnosis && (
              <ResolveCase result={result} query={query} />
            )}
          </section>

          <section className="card">
            <h2>Manual passages used</h2>
            {result.sources?.length > 0 ? (
              <ul className="sources">
                {result.sources.map((s, i) => <SourceItem key={i} s={s} />)}
              </ul>
            ) : (
              <p className="muted small">
                No manual passage met the confidence threshold for this query, so
                nothing was handed to the model to reason from.
              </p>
            )}
          </section>

          {!imageSkipped && (
            <section className="card">
              <h2>Detected in image</h2>
              {result.detections?.length > 0 ? (
                <>
                  {result.detections[0].pretrained && (
                    <p className="warn">
                      Pretrained model — generic object classes, not aircraft defects.
                    </p>
                  )}
                  <ul className="dets">
                    {result.detections.map((d, i) => (
                      <li key={i}>
                        <strong>{d.label}</strong>
                        <span className="muted"> {(d.confidence * 100).toFixed(1)}%</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="muted small">
                  Nothing detected in this image. The detector is still the
                  pretrained model, which knows generic objects rather than
                  aircraft defects — the diagnosis below came from your
                  description.
                </p>
              )}
            </section>
          )}

          <section className="card">
            <h2>Similar past cases</h2>
            {result.similar_cases?.length > 0 ? (
              <ul className="cases">
                {result.similar_cases.map((c) => (
                  <li key={c.case_id}>
                    <strong>{c.case_id}</strong> — {c.defect_type}
                    <span className="muted"> ({(c.similarity * 100).toFixed(0)}% similar)</span>
                    <div className="muted">{c.resolution || c.diagnosis}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted small">
                No similar past cases yet. Resolve this diagnosis above and it
                becomes the first one for a symptom like this.
              </p>
            )}
          </section>

          <section className="card">
            <h2>Pipeline</h2>
            <ul className="stages">
              {result.stages.map((s) => (
                <li key={s.name}>
                  <span className={s.ok ? (s.skipped ? "dot skip" : "dot ok") : "dot bad"} />
                  <strong>{s.name}</strong>
                  <span className="muted"> {s.ms.toFixed(0)} ms</span>
                  {s.note && <div className="muted small">{s.note}</div>}
                  {s.error && <div className="errtext">{s.error}</div>}
                </li>
              ))}
            </ul>
            <p className="muted small">Total {result.timing_ms.total.toFixed(0)} ms</p>
            {failedStages.length > 0 && (
              <p className="warn">
                {failedStages.length} stage(s) failed — the rest of the result is still valid.
              </p>
            )}
          </section>
        </>
      )}
      </div>
      </div>
      </>}
      </div>

      <p className="footer-note">
        <strong>PRISM</strong> runs entirely on this machine — Phi-3 Mini (Ollama),
        ChromaDB retrieval and YOLOv8 detection, no cloud calls in the diagnosis path.
      </p>
    </main>
  );
}

const STAGE_SEQUENCE = [
  ["detection", "Vision — scanning the image"],
  ["risk", "Risk — scoring telemetry and defects"],
  ["diagnosis", "Knowledge — retrieving manuals, then generating"],
  ["case_memory", "Case memory — finding similar past repairs"],
];

function LiveProgress({ stages, elapsed }) {
  const doneByName = Object.fromEntries(stages.map((s) => [s.name, s]));
  const nextPending = STAGE_SEQUENCE.find(([n]) => !doneByName[n]);
  return (
    <section className="card">
      <h2>Running · {elapsed.toFixed(1)}s</h2>
      <ul className="progress">
        {STAGE_SEQUENCE.map(([name, labelText]) => {
          const done = doneByName[name];
          const active = nextPending && nextPending[0] === name;
          return (
            <li key={name} className={done ? "done" : active ? "active" : "waiting"}>
              <span className="pmark">
                {done ? (done.skipped ? "–" : "✓") : active ? <span className="spinner" /> : ""}
              </span>
              <div>
                <strong>{labelText}</strong>
                {done && (
                  <span className="muted small">
                    {" "}{done.skipped ? "skipped" : `${done.ms.toFixed(0)} ms`}
                  </span>
                )}
                {done?.note && <div className="muted small">{done.note}</div>}
                {done?.error && <div className="errtext">{done.error}</div>}
              </div>
            </li>
          );
        })}
      </ul>
      <p className="muted small">
        Generation is the slow step — it runs entirely on this machine.
      </p>
    </section>
  );
}

function SourceItem({ s }) {
  const [open, setOpen] = useState(false);
  const text = s.text || "";
  return (
    <li className="source-item">
      <div className="source-head">
        <code>{s.source} p.{s.page}</code>
        <span className="muted small"> similarity {s.score.toFixed(3)}</span>
      </div>
      {text && (
        <>
          <p className={`passage${open ? " open" : ""}`}>{text}</p>
          <button type="button" className="linkish" onClick={() => setOpen(!open)}>
            {open ? "Show less" : "Show full passage"}
          </button>
        </>
      )}
    </li>
  );
}

function RiskPanel({ a }) {
  const band = a.band.toLowerCase();
  return (
    <section className={`card risk risk-${band}`}>
      <h2>Predictive risk score</h2>
      <div className="risk-score-row">
        <span className="risk-num">{a.score}</span>
        <span className="muted">/ 100</span>
        <span className={`tag risk-tag r-${band}`}>{a.band}</span>
      </div>
      <div className="rbar"><div className={`rfill r-${band}`} style={{ width: `${a.score}%` }} /></div>
      <ul className="factors">
        {a.factors.map((f) => (
          <li key={f.parameter}>
            <span className={`fdot ${f.band}`} />
            <strong>{f.label}</strong>
            {f.value != null && <span className="muted"> {f.value}{f.unit}</span>}
            <span className="muted"> — {f.note}</span>
            {f.points > 0 && <span className="fpts">+{f.points}</span>}
          </li>
        ))}
      </ul>
      <p className={a.needs_human_review ? "review" : "muted small"}>{a.advisory}</p>
      <p className="muted small disclaimer">
        Illustrative thresholds for demonstration — not certified airworthiness limits.
      </p>
    </section>
  );
}

function StatusPill({ p }) {
  let cls = "status-pill";
  let text = "Checking…";
  if (p?.unreachable) {
    cls += " down";
    text = "Backend unreachable";
  } else if (p) {
    const notReady = ["llm", "corpus", "detector", "case_memory"]
      .filter((k) => p[k] && !p[k].available).length;
    if (notReady === 0) {
      text = "Local · All systems ready";
    } else {
      cls += " degraded";
      text = `Local · ${notReady} stage${notReady > 1 ? "s" : ""} not ready`;
    }
  }
  return (
    <span className={cls}>
      <span className="blip" aria-hidden="true" />
      {text}
    </span>
  );
}

const STAGE_LABELS = [
  ["llm", "Local LLM"],
  ["corpus", "Manual corpus"],
  ["detector", "Defect detector"],
  ["case_memory", "Case memory"],
];

function SystemStatus({ p, onRefresh }) {
  if (!p) return <div className="card"><p className="muted">Checking backend…</p></div>;
  if (p.unreachable) {
    return (
      <div className="card err">
        <strong>Backend unreachable.</strong> Start it with <code>python app.py</code> in{" "}
        <code>backend/</code>. This view retries automatically every 12 seconds.
      </div>
    );
  }
  return (
    <section className="card">
      <h2>Pipeline stages</h2>
      <ul className="statuses">
        {STAGE_LABELS.map(([key, labelText]) => {
          const v = p[key] || {};
          const detail = v.available
            ? [v.model, v.chunks != null && `${v.chunks} chunks`,
               v.cases != null && `${v.cases} cases`,
               v.device && `on ${v.device}`,
               v.pretrained === true && "pretrained (not fine-tuned)"]
              .filter(Boolean).join(" · ")
            : v.reason;
          return (
            <li key={key}>
              <span className={v.available ? "dot ok" : "dot bad"} />
              <strong>{labelText}</strong>
              <span className="muted"> {v.available ? "ready" : "not ready"}</span>
              {detail && <div className="muted small">{detail}</div>}
            </li>
          );
        })}
      </ul>
      <button type="button" className="secondary" onClick={onRefresh}>Refresh now</button>
    </section>
  );
}

function Manuals() {
  const [docs, setDocs] = useState(null);
  const [err, setErr] = useState(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState(null);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    fetch(`${API}/corpus/documents`)
      .then((r) => r.json())
      .then((d) => (d.error ? setErr(d.detail || d.error) : setDocs(d.documents || [])))
      .catch((e) => setErr(e.message));
  }, []);

  async function search(e) {
    e.preventDefault();
    if (!q.trim()) return;
    setSearching(true);
    try {
      const r = await fetch(`${API}/corpus/search?q=${encodeURIComponent(q)}&k=5`);
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || d.error);
      setHits(d.hits || []);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setSearching(false);
    }
  }

  if (err) return <div className="card err"><strong>Corpus unavailable.</strong> {err}</div>;

  const totalChunks = (docs || []).reduce((n, d) => n + d.chunks, 0);

  return (
    <>
      <section className="card">
        <h2>Indexed manuals{docs ? ` · ${totalChunks.toLocaleString()} passages` : ""}</h2>
        {!docs ? (
          <p className="muted"><span className="spinner" /> Reading the index…</p>
        ) : (
          <ul className="sources">
            {docs.map((d) => (
              <li key={d.source}>
                <code>{d.source}</code>
                <span className="muted small">
                  {" "}{d.chunks.toLocaleString()} passages · {d.max_page} pages
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="muted small disclaimer">
          Public FAA advisory circulars, embedded locally with MiniLM and stored
          in ChromaDB on this machine. Nothing is fetched at query time.
        </p>
      </section>

      <section className="card">
        <h2>Search the manuals directly</h2>
        <p className="muted small" style={{ marginTop: -6, marginBottom: 10 }}>
          Retrieval only — no LLM. This is exactly what the diagnosis step is
          handed before it writes anything.
        </p>
        <form onSubmit={search} className="search-row">
          <input
            className="filter"
            type="search"
            value={q}
            placeholder="e.g. exfoliation corrosion treatment"
            onChange={(e) => setQ(e.target.value)}
          />
          <button type="submit" className="secondary" disabled={searching || !q.trim()}>
            {searching ? "Searching…" : "Search"}
          </button>
        </form>
        {hits && (
          hits.length ? (
            <ul className="sources">
              {hits.map((h, i) => <SourceItem key={i} s={h} />)}
            </ul>
          ) : <p className="muted small">No passages matched.</p>
        )}
      </section>
    </>
  );
}

function CaseHistory() {
  const [cases, setCases] = useState(null);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState(null);

  useEffect(() => {
    fetch(`${API}/memory/cases`)
      .then((r) => r.json())
      .then((d) => setCases(d.cases || []))
      .catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="card err"><strong>Could not load cases.</strong> {err}</div>;
  if (!cases) return <div className="card"><p className="muted">Loading cases…</p></div>;

  const needle = filter.trim().toLowerCase();
  const shown = needle
    ? cases.filter((c) =>
        [c.case_id, c.defect_type, c.symptom_description, c.diagnosis, c.resolution]
          .some((f) => (f || "").toLowerCase().includes(needle)))
    : cases;

  return (
    <section className="card">
      <h2>Case history · {cases.length} cases</h2>
      <input
        className="filter"
        type="search"
        value={filter}
        placeholder="Filter by defect type, symptom, resolution…"
        onChange={(e) => setFilter(e.target.value)}
      />
      {shown.length === 0 && <p className="muted">No cases match “{filter}”.</p>}
      <ul className="cases history">
        {shown.map((c) => (
          <li key={c.case_id}>
            <div className="case-head">
              <strong>{c.case_id}</strong>
              <span className="tag">{c.defect_type}</span>
              {c.risk_score && (
                <span className={`tag risk-tag r-${String(c.risk_score).toLowerCase()}`}>
                  {c.risk_score}
                </span>
              )}
            </div>
            <div>{c.symptom_description}</div>
            {c.diagnosis && <div className="muted small">{c.diagnosis}</div>}
            {c.resolution && <div className="muted small"><em>Fix:</em> {c.resolution}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ResolveCase({ result, query }) {
  const [open, setOpen] = useState(false);
  const [resolution, setResolution] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [err, setErr] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!resolution.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      const res = await fetch(`${API}/memory/log-case`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          defect_type: result.detections?.[0]?.label || "unspecified",
          symptom_description: query,
          diagnosis: result.diagnosis,
          resolution,
          risk_score: result.risk_score || "",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || `HTTP ${res.status}`);
      setSaved(data.case_id);
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <p className="resolved-ok">
        Logged as <strong>{saved}</strong> — it will surface in future similar-case lookups.
      </p>
    );
  }
  if (!open) {
    return (
      <button type="button" className="secondary" onClick={() => setOpen(true)}>
        Mark as resolved
      </button>
    );
  }
  return (
    <form className="resolve-form" onSubmit={submit}>
      <label htmlFor="res">What fix was applied, and what was the outcome?</label>
      <textarea
        id="res"
        rows={2}
        value={resolution}
        placeholder="e.g. Corrosion blended out per AC 43.13-1B, area re-primed and sealed."
        onChange={(e) => setResolution(e.target.value)}
      />
      {err && <p className="warn">{err}</p>}
      <div className="resolve-actions">
        <button type="submit" className="secondary" disabled={saving || !resolution.trim()}>
          {saving ? "Saving…" : "Save to case memory"}
        </button>
        <button type="button" className="secondary ghost" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Readiness({ p }) {
  if (p.unreachable) {
    return (
      <div className="card err">
        <strong>Backend unreachable.</strong> Start it with <code>python app.py</code> in{" "}
        <code>backend/</code>.
      </div>
    );
  }
  const items = [
    ["LLM", p.llm],
    ["Manual corpus", p.corpus],
    ["Detector", p.detector],
    ["Case memory", p.case_memory],
  ];
  const down = items.filter(([, v]) => v && !v.available);
  if (down.length === 0) return null;
  return (
    <div className="card warnbox">
      <strong>Some stages are not ready.</strong>
      <ul>
        {down.map(([name, v]) => (
          <li key={name}>
            <strong>{name}:</strong> <span className="muted">{v.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
