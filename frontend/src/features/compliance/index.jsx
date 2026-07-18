import React, { useMemo, useState } from "react";
import { useDemoContext } from "../../demo-context";
import "./style.css";

const ACTIONS = [
  { key: "evaluate", label: "Evaluate", description: "Reconcile obligations and review tasks", method: "POST", icon: "EV" },
  { key: "readiness", label: "Readiness", description: "Check whether encounter can close", method: "GET", icon: "RD" },
  { key: "audit", label: "Audit trail", description: "Review append-only event history", method: "GET", icon: "AU" },
  { key: "dashboard", label: "Dashboard", description: "Aggregate findings without PHI", method: "GET", icon: "DB" },
];

const STATE_LABELS = {
  SATISFIED: "Satisfied",
  NOT_APPLICABLE: "N/A",
  MISSING: "Missing",
  UNVERIFIED: "Unverified",
  PENDING: "Pending",
};

function Component() {
  const { encounterId, role, routeHref } = useDemoContext();
  const [result, setResult] = useState(null);
  const [view, setView] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState("");

  async function request(path, method = "GET", key = "") {
    setError("");
    setPending(key);
    try {
      const response = await fetch(path, { method, headers: { "X-Demo-Role": role } });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.message || "Request failed");
      setResult(body);
      setView(key);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setPending("");
    }
  }

  const actionRequest = key => {
    if (key === "evaluate") return request(`/api/v1/encounters/${encounterId}/evaluate`, "POST", key);
    if (key === "readiness") return request(`/api/v1/encounters/${encounterId}/readiness`, "GET", key);
    if (key === "audit") return request(`/api/v1/audit-events?encounter_id=${encounterId}`, "GET", key);
    return request("/api/v1/dashboard", "GET", key);
  };

  const checks = result?.checks || [];
  const summary = useMemo(() => checks.reduce((counts, item) => {
    counts[item.state] = (counts[item.state] || 0) + 1;
    return counts;
  }, {}), [checks]);
  const ready = result?.ready_to_close ?? (Boolean(result) && checks.every(item => ["SATISFIED", "NOT_APPLICABLE"].includes(item.state)));
  const isCloseReadiness = view === "readiness";
  const isStaff = ["FRONT_DESK", "ASSISTANT", "DENTIST", "QA"].includes(role);
  const isAuditor = ["DENTIST", "QA"].includes(role);

  return <section className="compliance-page" aria-labelledby="compliance-title">
    <header className="compliance-hero">
      <div>
        <p className="compliance-eyebrow">Module 06 · Deterministic control</p>
        <h1 id="compliance-title">Compliance &amp; Audit</h1>
        <p>Biến evidence từ các module thành obligation state, task đúng owner và quyết định readiness có thể audit.</p>
      </div>
      <div className="policy-badge"><span>Active policy</span><strong>dental-policy.v1</strong><small>Deterministic · version pinned</small></div>
    </header>

    {!isStaff && <div className="compliance-notice is-info"><strong>Role {role}</strong><span>Patient không được đọc compliance findings. Chọn staff role trên thanh context.</span></div>}
    {isStaff && !isAuditor && <div className="compliance-notice is-info"><strong>Role {role}</strong><span>Bạn có thể Evaluate/Readiness; Audit và Dashboard yêu cầu DENTIST hoặc QA.</span></div>}
    {error && <div className="compliance-notice is-error" role="alert"><strong>Không tải được dữ liệu</strong><span>{error}</span></div>}

    <div className="compliance-actions">
      {ACTIONS.map(action => <button type="button" key={action.key} className={view === action.key ? "is-active" : ""} onClick={() => actionRequest(action.key)} disabled={Boolean(pending) || !isStaff || (["audit", "dashboard"].includes(action.key) && !isAuditor)}>
        <i>{pending === action.key ? "…" : action.icon}</i><span><strong>{action.label}</strong><small>{action.description}</small></span><b>→</b>
      </button>)}
    </div>

    {!result ? <section className="compliance-empty">
      <div aria-hidden="true">✓</div><p>Ready for evaluation</p><h2>Chọn một compliance view ở trên</h2><span>Evaluate sẽ lưu current checks và reconcile task. Readiness chỉ tính trạng thái live, không tạo side effect.</span>
    </section> : <div className="compliance-results">
      {(view === "evaluate" || view === "readiness") && <>
        <section className={`readiness-banner ${ready ? "is-ready" : "is-blocked"}`}>
          <div className="readiness-icon" aria-hidden="true">{ready ? "✓" : "!"}</div>
          <div><span>{isCloseReadiness ? "Close gate" : `Active scope · ${result.stage || "current stage"}`}</span><h2>{ready ? (isCloseReadiness ? "Encounter is ready to close" : "Current-stage obligations are ready") : (isCloseReadiness ? "Encounter has blocking obligations" : "Current stage still has required work")}</h2><p>{ready ? "Mọi obligation trong scope đều Satisfied hoặc Not applicable." : `${result.blockers?.length ?? checks.filter(item => !["SATISFIED", "NOT_APPLICABLE"].includes(item.state)).length} items cần được xử lý trong scope này.`}</p></div>
          <a href={routeHref("/encounter")}>{ready ? "Return to Encounter →" : "View Encounter"}</a>
        </section>
        <section className="compliance-summary">
          {["SATISFIED", "NOT_APPLICABLE", "MISSING", "UNVERIFIED", "PENDING"].map(state => <article key={state}><span>{STATE_LABELS[state]}</span><strong>{summary[state] || 0}</strong><i className={`state-${state.toLowerCase()}`} /></article>)}
        </section>
        <section className="obligation-board">
          <header><div><span>Policy evaluation</span><h2>Obligation findings</h2></div><small>{checks.length} policy rules</small></header>
          <div>{checks.map(item => <article key={item.code}>
            <span className={`obligation-state state-${item.state.toLowerCase()}`}>{STATE_LABELS[item.state] || item.state}</span>
            <div><strong>{item.code}</strong><small>Owner · {item.owner_role}</small></div>
            <a href={routeHref(item.code.startsWith("DOC_") ? "/documentation-ai" : item.code.startsWith("PRE_") ? "/pre-treatment" : item.code.startsWith("COORD_") ? "/coordination" : "/post-treatment")}>Open module →</a>
          </article>)}</div>
        </section>
        {result.tasks?.length > 0 && <section className="compliance-task-strip"><div><span>Generated work</span><strong>{result.tasks.filter(task => ["OPEN", "ACKNOWLEDGED"].includes(task.status)).length} active review tasks</strong></div><a href={routeHref("/coordination")}>Mở worklists →</a></section>}
      </>}

      {view === "audit" && <section className="audit-panel">
        <header><div><span>Append-only timeline</span><h2>Encounter audit events</h2></div><small>{result.items?.length || 0} events</small></header>
        {result.items?.length ? <ol>{result.items.map((item, index) => <li key={`${item.correlation_id}-${index}`}><i /><div><strong>{item.action.replaceAll("_", " ")}</strong><span>{item.actor_role} · {item.object_type}</span><small>{new Date(item.created_at).toLocaleString("vi-VN")}</small></div><code>{item.correlation_id?.slice(0, 8)}</code></li>)}</ol> : <p className="panel-empty">Chưa có audit event cho encounter này.</p>}
      </section>}

      {view === "dashboard" && <section className="dashboard-panel">
        <header><div><span>Non-PHI aggregate</span><h2>Compliance dashboard</h2></div><small>All encounters</small></header>
        <div>{result.items?.map((item, index) => <article key={`${item.pain_point}-${item.state}-${index}`}><span>{item.pain_point}</span><strong>{item.count}</strong><small>{STATE_LABELS[item.state] || item.state}</small></article>)}</div>
        {!result.items?.length && <p className="panel-empty">Evaluate một encounter để tạo dashboard findings.</p>}
      </section>}

      <details className="compliance-raw"><summary>Developer JSON response</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
    </div>}
  </section>;
}

export const route = { path: "/compliance", label: "Compliance", Component };
