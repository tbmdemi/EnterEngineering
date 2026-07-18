import React, { useState } from "react";
import { apiFetch } from "../../api";
import { useDemoContext } from "../../demo-context";
import "./style.css";

const CLINICAL_ROLES = new Set(["ASSISTANT", "DENTIST"]);

async function responseBody(response, fallbackMessage) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || fallbackMessage);
  return body;
}

function DocumentationAi() {
  const { encounterId, role, routeHref, tr } = useDemoContext();
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
      const response = await apiFetch("/api/v1/documentation", {
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
      const result = await responseBody(response, tr("Không thể lưu hồ sơ", "Unable to save documentation"));
      setStatus({ type: "success", message: tr(`${result.evidence_codes.length} mục bằng chứng đã được lưu và xác minh.`, `${result.evidence_codes.length} evidence items were saved and verified.`) });
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
      const response = await apiFetch("/api/v1/ai/extract-note", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({ encounter_id: encounterId, note }),
      });
      setRun(await responseBody(response, tr("Không thể trích xuất ghi chú", "Unable to extract note")));
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
      const response = await apiFetch(`/api/v1/ai/runs/${run.ai_run_id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: action === "accept" ? JSON.stringify({ evidence_code }) : undefined,
      });
      const result = await responseBody(response, tr("Không thể cập nhật kết quả AI", "Unable to update AI result"));
      setRun(current => ({ ...current, state: result.state }));
      setStatus({ type: "success", message: action === "accept" ? tr("Nha sĩ đã xác minh dữ kiện AI.", "The dentist verified the AI fact.") : tr("Dữ kiện AI đã bị từ chối.", "The AI fact was rejected.") });
    } catch (error) {
      setStatus({ type: "error", message: error.message });
    } finally {
      setPending("");
    }
  }

  return <section className="documentation-page" aria-labelledby="documentation-title">
    <header className="documentation-hero">
      <div>
        <p className="feature-eyebrow">{tr("Module 02 · Bằng chứng lâm sàng", "Module 02 · Clinical evidence")}</p>
        <h1 id="documentation-title">{tr("Hồ sơ & AI cho nhân viên", "Documentation & Staff AI")}</h1>
        <p>{tr("Ghi nhận biểu mẫu có cấu trúc, sau đó dùng AI để tìm bằng chứng. Mọi dữ kiện AI vẫn cần con người xác minh.", "Capture structured forms, then use AI to find evidence. Every AI fact still requires human verification.")}</p>
      </div>
      <div className="feature-context-card">
        <span>{tr("Ca khám hiện tại", "Active encounter")}</span><strong>#{encounterId.slice(-6).toUpperCase()}</strong><small>{tr("Vai trò", "Acting as")} {role}</small>
      </div>
    </header>

    {!canDocument && <div className="feature-notice is-warning" role="alert"><strong>{tr("Vai trò hiện tại chỉ được xem.", "The current role is read-only.")}</strong><span>{tr("Chọn TRỢ LÝ hoặc NHA SĨ trên thanh ngữ cảnh để nhập hồ sơ.", "Select ASSISTANT or DENTIST in the context bar to enter documentation.")}</span></div>}
    {status.message && <div className={`feature-notice is-${status.type}`} role="status"><strong>{status.type === "success" ? tr("Đã cập nhật", "Updated") : tr("Cần kiểm tra", "Needs attention")}</strong><span>{status.message}</span></div>}

    <div className="documentation-grid">
      <form className="feature-card documentation-form" onSubmit={saveDocumentation}>
        <div className="feature-card-heading"><span>01</span><div><p>{tr("Biểu mẫu có cấu trúc", "Structured form")}</p><h2>{tr("Hồ sơ lâm sàng", "Clinical documentation")}</h2></div><em>{tr("Do con người nhập", "Human authored")}</em></div>
        <div className="documentation-checks">
          <label><input type="checkbox" name="consent_signed" defaultChecked /> <span><strong>{tr("Đã ký đồng thuận", "Consent signed")}</strong><small>{tr("Bắt buộc trước khi đóng ca", "Required before close")}</small></span></label>
          <label><input type="checkbox" name="treatment_plan_signed" defaultChecked /> <span><strong>{tr("Đã ký kế hoạch điều trị", "Treatment plan signed")}</strong><small>{tr("Bắt buộc trước khi đóng ca", "Required before close")}</small></span></label>
        </div>
        <label className="feature-field"><span>{tr("Ghi chú diễn tiến", "Progress note")}</span><textarea name="progress_note" defaultValue="Routine cleaning completed without complication." required /></label>
        <div className="feature-field-row">
          <label className="feature-field"><span>{tr("Răng", "Tooth")}</span><input name="tooth" defaultValue="11" required /></label>
          <label className="feature-field"><span>{tr("Mặt răng", "Surface")}</span><input name="surface" defaultValue="F" required /></label>
        </div>
        <label className="medication-toggle"><input type="checkbox" name="medication_prescribed" checked={medicationPrescribed} onChange={event => setMedicationPrescribed(event.target.checked)} /><span><strong>{tr("Có kê đơn thuốc", "Medication prescribed")}</strong><small>{tr("Bật nếu ca khám có đơn thuốc.", "Enable when the encounter includes a prescription.")}</small></span></label>
        {medicationPrescribed && <label className="feature-field"><span>{tr("Chi tiết thuốc", "Medication details")}</span><input name="medication_detail" placeholder={tr("Tên thuốc, liều dùng và thời gian", "Medication, dose, and duration")} required /></label>}
        <button className="feature-button is-primary" type="submit" disabled={!canDocument || Boolean(pending)}>{pending === "documentation" ? tr("Đang lưu bằng chứng…", "Saving evidence…") : tr("Lưu hồ sơ đã xác minh", "Save verified documentation")}</button>
      </form>

      <section className="feature-card ai-review-card">
        <div className="feature-card-heading"><span>02</span><div><p>{tr("Tìm bằng chứng", "Evidence finder")}</p><h2>{tr("AI trích xuất ghi chú", "AI note extraction")}</h2></div><em>{tr("Chỉ là bản nháp", "Draft only")}</em></div>
        <form onSubmit={extract}>
          <label className="feature-field"><span>{tr("Ghi chú nguồn", "Source note")}</span><textarea value={note} onChange={event => setNote(event.target.value)} required /></label>
          <button className="feature-button is-secondary" type="submit" disabled={!canDocument || Boolean(pending)}>{pending === "extract" ? tr("Đang phân tích…", "Analyzing…") : tr("Trích xuất dữ kiện có trích dẫn", "Extract cited fact")}</button>
        </form>

        <div className="ai-boundary"><span aria-hidden="true">AI</span><p><strong>{tr("Không tự quyết định.", "No autonomous decisions.")}</strong> {tr("Kết quả bắt đầu ở trạng thái CHƯA XÁC MINH và giữ nguyên đoạn nguồn để nha sĩ đối chiếu.", "Output starts as UNVERIFIED and preserves its source span for dentist review.")}</p></div>
        {run && <div className="ai-result" aria-live="polite">
          <div><span className={`state-${run.state.toLowerCase()}`}>{run.state}</span><small>Run #{run.ai_run_id.slice(-6)}</small></div>
          {run.facts?.map((fact, index) => <article key={`${fact.fact}-${index}`}><strong>{fact.fact.replaceAll("_", " ")}</strong><blockquote>“{fact.source_span}”</blockquote>{fact.tooth && <p>{tr("Răng", "Tooth")} {fact.tooth} · {tr("Mặt", "Surface")} {fact.surface}</p>}</article>)}
          {run.state === "UNVERIFIED" && <div className="ai-review-actions">
            <button className="feature-button is-danger-quiet" type="button" onClick={() => review("reject")} disabled={role !== "DENTIST" || Boolean(pending)}>{tr("Từ chối", "Reject")}</button>
            <button className="feature-button is-primary" type="button" onClick={() => review("accept")} disabled={role !== "DENTIST" || Boolean(pending)}>{tr("Chấp nhận và xác minh", "Accept as verified")}</button>
          </div>}
          {role !== "DENTIST" && run.state === "UNVERIFIED" && <small>{tr("Chuyển vai trò sang NHA SĨ để kiểm tra dữ kiện AI.", "Switch to DENTIST to review the AI fact.")}</small>}
        </div>}
      </section>
    </div>

    <aside className="feature-next-step"><div><span>{tr("Bằng chứng tiếp theo", "Next evidence")}</span><strong>{tr("Kiểm tra an toàn trước điều trị", "Pre-treatment safety checks")}</strong></div><a href={routeHref("/pre-treatment")}>{tr("Mở Cổng an toàn →", "Open Safety Gate →")}</a></aside>
  </section>;
}

export const route = { path: "/documentation-ai", label: "Documentation & Staff AI", Component: DocumentationAi };
