import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:5000";

/**
 * Day 1 placeholder UI.
 * Its only job is to prove the React dev server can reach the Flask backend
 * across origins — the CORS path that D9-02 depends on.
 * Day 9 replaces this with the real upload + diagnosis form.
 */
export default function App() {
  const [status, setStatus] = useState({ state: "checking" });

  useEffect(() => {
    fetch(`${API}/health`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => setStatus({ state: "ok", data }))
      .catch((err) => setStatus({ state: "error", message: err.message }));
  }, []);

  return (
    <main className="wrap">
      <h1>PRISM</h1>
      <p className="sub">Predictive Reasoning for In-Service Maintenance — Stage 2 build</p>

      <section className="card">
        <h2>Backend connection</h2>
        {status.state === "checking" && <p className="muted">Checking {API}/health …</p>}
        {status.state === "ok" && (
          <p className="ok">
            Connected — <code>{JSON.stringify(status.data)}</code>
          </p>
        )}
        {status.state === "error" && (
          <div className="err">
            <p>Cannot reach the backend ({status.message}).</p>
            <ol>
              <li>Is Flask running? <code>cd backend &amp;&amp; python app.py</code></li>
              <li>Is it on port 5000? Check <code>backend/.env</code></li>
              <li>Is <code>CORS(app)</code> still in <code>app.py</code>?</li>
            </ol>
          </div>
        )}
      </section>

      <p className="muted small">
        Day 9 replaces this page with the image upload + symptom query form.
      </p>
    </main>
  );
}
