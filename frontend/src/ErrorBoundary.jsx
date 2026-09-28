import { Component } from "react";

/**
 * Without this, any render-time exception unmounts the whole tree and leaves
 * a blank white page — unrecoverable mid-demo without a reload, and with no
 * indication of what went wrong. This keeps the failure contained and
 * legible, and offers a reload rather than a dead end.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the real stack in the console for whoever is debugging.
    console.error("PRISM UI crashed:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="wrap">
        <div className="content">
          <div className="card err" style={{ marginTop: 40 }}>
            <strong>The interface hit an unexpected error.</strong>
            <p className="muted small">
              The backend and your data are unaffected — this is a display fault
              only. Reload to carry on; the full stack is in the browser console.
            </p>
            <pre className="errtext" style={{ whiteSpace: "pre-wrap", margin: "10px 0 0" }}>
              {String(this.state.error)}
            </pre>
            <button type="button" className="secondary" onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        </div>
      </main>
    );
  }
}
