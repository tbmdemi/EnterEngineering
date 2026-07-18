import React, { useState } from "react";
import { useDemoContext } from "../../demo-context";
import "./style.css";

const CLINICAL_ROLES = new Set(["ASSISTANT", "DENTIST"]);

async function responseBody(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || "Không thể hoàn tất yêu cầu");
  return body;
}

function DocumentationAi() {
  const { encounterId, role, routeHref } = useDemoContext();
  const [run, setRun] = useState(null);
  const [note, setNote] = useState("Procedure documented for tooth 11 surface F.");
  const [medicationPrescribed, setMedicationPrescribed] = useState(false);
  const [status, setStatus] = useState({ type: "", message: "" });
  const [pending, setPending] = useState("");
  const canDocument = CLINICAL_ROLES.has(role);

  async function saveDocumentation(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending("documentation");
    setStatus({ type: "", message: "" });
    try {
      const response = await fetch("/api/v1/documentation", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({
          encounter_id: encounterId,
          consent_signed: form.has("consent_signed"),
          treatment_plan_signed: form.has("treatment_plan_signed"),
          progress_note: form.get("progress_note"),
          medication_prescribed: medicationPrescribed,
          medication_detail: form.get("medication_detail") || null,
          tooth: form.get("tooth"),
          surface: form.get("surface"),
        }),
      });
      const result = await responseBody(response);
      setStatus({ type: "success", message: `${result.evidence_codes.length} evidence items đã được lưu và xác minh.` });
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    } finally {
      setPending("");
    }
  }

  async function extract(event) {
    event.preventDefault();
    setPending("extract");
    setStatus({ type: "", message: "" });
    try {
      const response = await fetch("/api/v1/ai/extract-note", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({ encounter_id: encounterId, note }),
      });
      setRun(await responseBody(response));
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    } finally {
      setPending("");
    }
  }

  async function review(action) {
    const fact = run.facts[0];
    const evidence_code = fact.fact === "procedure_documented" ? "DOC_TOOTH_SURFACE" : "DOC_PROGRESS_NOTE";
    setPending(action);
    setStatus({ type: "", message: "" });
    try {
      const response = await fetch(`/api/v1/ai/runs/${run.ai_run_id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: action === "accept" ? JSON.stringify({ evidence_code }) : undefined,
      });
      const result = await responseBody(response);
      setRun(current => ({ ...current, state: result.state }));
      setStatus({ type: "success", message: action === "accept" ? "Dentist đã xác minh AI fact." : "AI fact đã bị từ chối." });
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    } finally {
      setPending("");
    }
  }

  return <section className="documentation-page" aria-labelledby="documentation-title">
    <header className="documentation-hero">
      <div>
        <p className="feature-eyebrow">Module 02 · Clinical evidence</p>
        <h1 id="documentation-title">Documentation &amp; Staff AI</h1>
        <p>Ghi nhận biểu mẫu có cấu trúc, sau đó dùng AI để tìm evidence. Mọi AI fact vẫn cần con người xác minh.</p>
      </div>
      <div className="feature-context-card">
        <span>Active encounter</span><strong>#{encounterId.slice(-6).toUpperCase()}</strong><small>Acting as {role}</small>
      </div>
    </header>

    {!canDocument && <div className="feature-notice is-warning" role="alert"><strong>Role hiện tại chỉ được xem.</strong><span>Chọn ASSISTANT hoặc DENTIST trên thanh context để nhập documentation.</span></div>}
    {status.message && <div className={`feature-notice is-${status.type}`} role="status"><strong>{status.type === "success" ? "Đã cập nhật" : "Cần kiểm tra"}</strong><span>{status.message}</span></div>}

    <div className="documentation-grid">
      <form className="feature-card documentation-form" onSubmit={saveDocumentation}>
        <div className="feature-card-heading"><span>01</span><div><p>Structured form</p><h2>Clinical documentation</h2></div><em>Human authored</em></div>
        <div className="documentation-checks">
          <label><input type="checkbox" name="consent_signed" defaultChecked /> <span><strong>Consent signed</strong><small>Required before close</small></span></label>
          <label><input type="checkbox" name="treatment_plan_signed" defaultChecked /> <span><strong>Treatment plan signed</strong><small>Required before close</small></span></label>
        </div>
        <label className="feature-field"><span>Progress note</span><textarea name="progress_note" defaultValue="Routine cleaning completed without complication." required /></label>
        <div className="feature-field-row">
          <label className="feature-field"><span>Tooth</span><input name="tooth" defaultValue="11" required /></label>
          <label className="feature-field"><span>Surface</span><input name="surface" defaultValue="F" required /></label>
        </div>
        <label className="medication-toggle"><input type="checkbox" name="medication_prescribed" checked={medicationPrescribed} onChange={event => setMedicationPrescribed(event.target.checked)} /><span><strong>Medication prescribed</strong><small>Bật nếu encounter có đơn thuốc.</small></span></label>
        {medicationPrescribed && <label className="feature-field"><span>Medication details</span><input name="medication_detail" placeholder="Tên thuốc, liều dùng và thời gian" required /></label>}
        <button className="feature-button is-primary" type="submit" disabled={!canDocument || Boolean(pending)}>{pending === "documentation" ? "Đang lưu evidence…" : "Save verified documentation"}</button>
      </form>

      <section className="feature-card ai-review-card">
        <div className="feature-card-heading"><span>02</span><div><p>Evidence finder</p><h2>AI note extraction</h2></div><em>Draft only</em></div>
        <form onSubmit={extract}>
          <label className="feature-field"><span>Source note</span><textarea value={note} onChange={event => setNote(event.target.value)} required /></label>
          <button className="feature-button is-secondary" type="submit" disabled={!canDocument || Boolean(pending)}>{pending === "extract" ? "Đang phân tích…" : "Extract cited fact"}</button>
        </form>

        <div className="ai-boundary"><span aria-hidden="true">AI</span><p><strong>Không tự quyết định.</strong> Output bắt đầu ở trạng thái UNVERIFIED và giữ nguyên source span để nha sĩ đối chiếu.</p></div>
        {run && <div className="ai-result" aria-live="polite">
          <div><span className={`state-${run.state.toLowerCase()}`}>{run.state}</span><small>Run #{run.ai_run_id.slice(-6)}</small></div>
          {run.facts?.map((fact, index) => <article key={`${fact.fact}-${index}`}><strong>{fact.fact.replaceAll("_", " ")}</strong><blockquote>“{fact.source_span}”</blockquote>{fact.tooth && <p>Tooth {fact.tooth} · Surface {fact.surface}</p>}</article>)}
          {run.state === "UNVERIFIED" && <div className="ai-review-actions">
            <button className="feature-button is-danger-quiet" type="button" onClick={() => review("reject")} disabled={role !== "DENTIST" || Boolean(pending)}>Reject</button>
            <button className="feature-button is-primary" type="button" onClick={() => review("accept")} disabled={role !== "DENTIST" || Boolean(pending)}>Accept as verified</button>
          </div>}
          {role !== "DENTIST" && run.state === "UNVERIFIED" && <small>Chuyển role sang DENTIST để review AI fact.</small>}
        </div>}
      </section>
    </div>

    <aside className="feature-next-step"><div><span>Evidence tiếp theo</span><strong>Pre-treatment safety checks</strong></div><a href={routeHref("/pre-treatment")}>Mở Safety Gate →</a></aside>
  </section>;
}

export const route = { path: "/documentation-ai", label: "Documentation & Staff AI", Component: DocumentationAi };
