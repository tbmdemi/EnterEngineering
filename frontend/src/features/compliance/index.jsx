import React, { useMemo, useState } from "react";
import { apiFetch } from "../../api";
import { useDemoContext } from "../../demo-context";
import "./style.css";

const ACTIONS = [
  { key: "evaluate", label: ["Đánh giá", "Evaluate"], description: ["Đối soát nghĩa vụ và task review", "Reconcile obligations and review tasks"], icon: "EV" },
  { key: "readiness", label: ["Sẵn sàng", "Readiness"], description: ["Kiểm tra điều kiện đóng ca", "Check whether encounter can close"], icon: "RD" },
  { key: "audit", label: ["Nhật ký audit", "Audit trail"], description: ["Xem lịch sử sự kiện chỉ-ghi-thêm", "Review append-only event history"], icon: "AU" },
  { key: "dashboard", label: ["Tổng quan", "Dashboard"], description: ["Tổng hợp không chứa PHI", "Aggregate findings without PHI"], icon: "DB" },
];

const STATE_LABELS = {
  SATISFIED: ["Đạt", "Satisfied"], NOT_APPLICABLE: ["Không áp dụng", "N/A"],
  MISSING: ["Thiếu", "Missing"], UNVERIFIED: ["Chưa xác minh", "Unverified"], PENDING: ["Đang chờ", "Pending"],
};

function Component() {
  const { encounterId, locale, role, routeHref, tr } = useDemoContext();
  const stateLabel = state => tr(...(STATE_LABELS[state] || [state, state]));
  const [result, setResult] = useState(null);
  const [view, setView] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState("");

  async function request(path, method = "GET", key = "") {
    setError("");
    setPending(key);
    try {
      const response = await apiFetch(path, { method, headers: { "X-Demo-Role": role } });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.message || tr("Yêu cầu thất bại", "Request failed"));
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
        <p className="compliance-eyebrow">{tr("Module 06 · Kiểm soát tất định", "Module 06 · Deterministic control")}</p>
        <h1 id="compliance-title">{tr("Tuân thủ & Nhật ký", "Compliance & Audit")}</h1>
        <p>{tr("Biến bằng chứng từ các module thành trạng thái nghĩa vụ, tác vụ đúng người phụ trách và quyết định sẵn sàng có thể kiểm tra.", "Turn evidence from every module into obligation states, correctly owned tasks, and auditable readiness decisions.")}</p>
      </div>
      <div className="policy-badge"><span>{tr("Chính sách hiện hành", "Active policy")}</span><strong>dental-policy.v1</strong><small>{tr("Tất định · cố định phiên bản", "Deterministic · version pinned")}</small></div>
    </header>

    {!isStaff && <div className="compliance-notice is-info"><strong>{tr("Vai trò", "Role")} {role}</strong><span>{tr("Bệnh nhân không được đọc kết quả tuân thủ. Hãy chọn vai trò nhân viên trên thanh ngữ cảnh.", "Patients cannot read compliance findings. Select a staff role in the context bar.")}</span></div>}
    {isStaff && !isAuditor && <div className="compliance-notice is-info"><strong>{tr("Vai trò", "Role")} {role}</strong><span>{tr("Bạn có thể Đánh giá/Kiểm tra sẵn sàng; Nhật ký và Tổng quan yêu cầu NHA SĨ hoặc QA.", "You can use Evaluate/Readiness; Audit and Dashboard require DENTIST or QA.")}</span></div>}
    {error && <div className="compliance-notice is-error" role="alert"><strong>{tr("Không tải được dữ liệu", "Unable to load data")}</strong><span>{error}</span></div>}

    <div className="compliance-actions">
      {ACTIONS.map(action => <button type="button" key={action.key} className={view === action.key ? "is-active" : ""} onClick={() => actionRequest(action.key)} disabled={Boolean(pending) || !isStaff || (["audit", "dashboard"].includes(action.key) && !isAuditor)}>
        <i>{pending === action.key ? "…" : action.icon}</i><span><strong>{tr(...action.label)}</strong><small>{tr(...action.description)}</small></span><b>→</b>
      </button>)}
    </div>

    {!result ? <section className="compliance-empty">
      <div aria-hidden="true">✓</div><p>{tr("Sẵn sàng đánh giá", "Ready for evaluation")}</p><h2>{tr("Chọn một chế độ tuân thủ ở trên", "Choose a compliance view above")}</h2><span>{tr("Đánh giá sẽ lưu các kiểm tra hiện tại và đồng bộ tác vụ. Kiểm tra sẵn sàng chỉ tính trạng thái trực tiếp, không tạo tác dụng phụ.", "Evaluate persists current checks and reconciles tasks. Readiness computes live state without side effects.")}</span>
    </section> : <div className="compliance-results">
      {(view === "evaluate" || view === "readiness") && <>
        <section className={`readiness-banner ${ready ? "is-ready" : "is-blocked"}`}>
          <div className="readiness-icon" aria-hidden="true">{ready ? "✓" : "!"}</div>
          <div><span>{isCloseReadiness ? tr("Cổng đóng ca", "Close gate") : `${tr("Phạm vi hiện tại", "Active scope")} · ${result.stage || tr("giai đoạn hiện tại", "current stage")}`}</span><h2>{ready ? (isCloseReadiness ? tr("Ca khám đã sẵn sàng đóng", "Encounter is ready to close") : tr("Nghĩa vụ của giai đoạn hiện tại đã sẵn sàng", "Current-stage obligations are ready")) : (isCloseReadiness ? tr("Ca khám còn nghĩa vụ cản trở", "Encounter has blocking obligations") : tr("Giai đoạn hiện tại còn việc bắt buộc", "Current stage still has required work"))}</h2><p>{ready ? tr("Mọi nghĩa vụ trong phạm vi đều Đạt hoặc Không áp dụng.", "Every obligation in scope is Satisfied or Not applicable.") : `${result.blockers?.length ?? checks.filter(item => !["SATISFIED", "NOT_APPLICABLE"].includes(item.state)).length} ${tr("mục cần được xử lý trong phạm vi này.", "items need attention in this scope.")}`}</p></div>
          <a href={routeHref("/encounter")}>{ready ? tr("Quay lại Ca khám →", "Return to Encounter →") : tr("Xem Ca khám", "View Encounter")}</a>
        </section>
        <section className="compliance-summary">
          {["SATISFIED", "NOT_APPLICABLE", "MISSING", "UNVERIFIED", "PENDING"].map(state => <article key={state}><span>{stateLabel(state)}</span><strong>{summary[state] || 0}</strong><i className={`state-${state.toLowerCase()}`} /></article>)}
        </section>
        <section className="obligation-board">
          <header><div><span>{tr("Đánh giá chính sách", "Policy evaluation")}</span><h2>{tr("Kết quả nghĩa vụ", "Obligation findings")}</h2></div><small>{checks.length} {tr("quy tắc", "policy rules")}</small></header>
          <div>{checks.map(item => <article key={item.code}>
            <span className={`obligation-state state-${item.state.toLowerCase()}`}>{stateLabel(item.state)}</span>
            <div><strong>{item.code}</strong><small>{tr("Phụ trách", "Owner")} · {item.owner_role}</small></div>
            <a href={routeHref(item.code.startsWith("DOC_") ? "/documentation-ai" : item.code.startsWith("PRE_") ? "/pre-treatment" : item.code.startsWith("COORD_") ? "/coordination" : "/post-treatment")}>{tr("Mở module →", "Open module →")}</a>
          </article>)}</div>
        </section>
        {result.tasks?.length > 0 && <section className="compliance-task-strip"><div><span>{tr("Công việc được tạo", "Generated work")}</span><strong>{result.tasks.filter(task => ["OPEN", "ACKNOWLEDGED"].includes(task.status)).length} {tr("tác vụ review đang hoạt động", "active review tasks")}</strong></div><a href={routeHref("/coordination")}>{tr("Mở danh sách việc →", "Open worklists →")}</a></section>}
      </>}

      {view === "audit" && <section className="audit-panel">
        <header><div><span>{tr("Dòng thời gian chỉ ghi thêm", "Append-only timeline")}</span><h2>{tr("Sự kiện kiểm tra ca khám", "Encounter audit events")}</h2></div><small>{result.items?.length || 0} {tr("sự kiện", "events")}</small></header>
        {result.items?.length ? <ol>{result.items.map((item, index) => <li key={`${item.correlation_id}-${index}`}><i /><div><strong>{item.action.replaceAll("_", " ")}</strong><span>{item.actor_role} · {item.object_type}</span><small>{new Date(item.created_at).toLocaleString(locale)}</small></div><code>{item.correlation_id?.slice(0, 8)}</code></li>)}</ol> : <p className="panel-empty">{tr("Chưa có sự kiện audit cho ca khám này.", "No audit events exist for this encounter.")}</p>}
      </section>}

      {view === "dashboard" && <section className="dashboard-panel">
        <header><div><span>{tr("Tổng hợp không chứa PHI", "Non-PHI aggregate")}</span><h2>{tr("Bảng điều khiển tuân thủ", "Compliance dashboard")}</h2></div><small>{tr("Tất cả ca khám", "All encounters")}</small></header>
        <div>{result.items?.map((item, index) => <article key={`${item.pain_point}-${item.state}-${index}`}><span>{item.pain_point}</span><strong>{item.count}</strong><small>{stateLabel(item.state)}</small></article>)}</div>
        {!result.items?.length && <p className="panel-empty">{tr("Đánh giá một ca khám để tạo dữ liệu tổng quan.", "Evaluate an encounter to create dashboard findings.")}</p>}
      </section>}

      <details className="compliance-raw"><summary>{tr("Phản hồi JSON cho lập trình viên", "Developer JSON response")}</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
    </div>}
  </section>;
}

export const route = { path: "/compliance", label: "Compliance", Component };
