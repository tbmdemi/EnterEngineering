import React, { useEffect, useState } from "react";
import { apiFetch } from "../../api";
import { useDemoContext } from "../../demo-context";
import "./style.css";

const INITIAL_VALUES = {
  PRE_MEDICAL_HISTORY: { summary: "" },
  PRE_ALLERGY: { status: "NONE_KNOWN", allergen: "" },
  PRE_VITALS: { systolic: "", diastolic: "", pulse: "" },
  PRE_STERILIZATION: { cycle_or_tray_id: "" },
  PRE_IMAGING: { imaging_reference: "" },
};
const COPY = {
  PRE_MEDICAL_HISTORY: [["Tiền sử bệnh", "Medical History"], ["Kiểm tra hồ sơ được trích dẫn và xác nhận bản tóm tắt.", "Review the cited record and confirm the summary."]],
  PRE_ALLERGY: [["Dị ứng", "Allergy"], ["Xác nhận tình trạng dị ứng của bệnh nhân trước điều trị.", "Confirm the patient allergy status before treatment."]],
  PRE_VITALS: [["Sinh hiệu", "Vitals"], ["Ghi nhận huyết áp và mạch hiện tại.", "Record the current blood pressure and pulse."]],
  PRE_STERILIZATION: [["Tiệt khuẩn", "Sterilization"], ["Xác nhận thiết lập vô khuẩn và mã chu trình hoặc khay.", "Confirm the sterile setup and its cycle or tray ID."]],
  PRE_IMAGING: [["Hình ảnh", "Imaging"], ["Xác nhận tham chiếu hình ảnh đã kiểm tra khi được yêu cầu.", "Confirm the reviewed imaging reference when required."]],
};

function formatDate(value, locale, tr) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? tr("Không có thời gian", "Time unavailable") : new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function evidenceSummary(item, tr) {
  const value = item.evidence?.value || {};
  if (item.code === "PRE_MEDICAL_HISTORY") return value.summary || tr("Đã kiểm tra tiền sử bệnh", "Medical history reviewed");
  if (item.code === "PRE_ALLERGY") return value.status === "PRESENT" ? `${tr("Dị ứng", "Allergy")}: ${value.allergen}` : tr("Không có dị ứng đã biết", "No known allergies");
  if (item.code === "PRE_VITALS") return `${value.systolic}/${value.diastolic} mmHg · ${tr("mạch", "pulse")} ${value.pulse} bpm`;
  if (item.code === "PRE_STERILIZATION") return `${tr("Chu trình / khay", "Cycle / tray")}: ${value.cycle_or_tray_id}`;
  if (item.code === "PRE_IMAGING") return value.not_applicable ? tr("Không áp dụng", "Not applicable") : `${tr("Tham chiếu", "Reference")}: ${value.imaging_reference}`;
  return tr("Đã xác minh", "Verified");
}

function PreTreatment() {
  const { encounterId, locale, role, setRole, tr } = useDemoContext();
  const [items, setItems] = useState([]);
  const [audit, setAudit] = useState([]);
  const [values, setValues] = useState(INITIAL_VALUES);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [dirty, setDirty] = useState({});
  const [imagingReviewed, setImagingReviewed] = useState(false);
  const [acceptedReviews, setAcceptedReviews] = useState({});
  const [rejectedReviews, setRejectedReviews] = useState({});
  const [procedureChoice, setProcedureChoice] = useState("");
  const [persistedRequiresImaging, setPersistedRequiresImaging] = useState(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch(`/api/v1/encounters/${encounterId}/pre-treatment`, { headers: { "X-Demo-Role": role } });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || tr("Không thể tải danh sách kiểm tra", "Unable to load checklist"));
      setItems(result.items || []);
      setAudit(result.audit || []);
      const requiresImaging = result.procedure?.requires_imaging;
      setPersistedRequiresImaging(requiresImaging === true ? true : requiresImaging === false ? false : null);
      setProcedureChoice(requiresImaging === true ? "required" : requiresImaging === false ? "not-required" : "");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [encounterId, role]);

  useEffect(() => {
    const warn = event => {
      if (!Object.values(dirty).some(Boolean)) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const update = (code, key, value) => {
    setValues(current => ({ ...current, [code]: { ...current[code], [key]: value } }));
    setDirty(current => ({ ...current, [code]: true }));
    setFieldErrors(current => ({ ...current, [code]: "" }));
  };

  const useSuggestion = item => {
    setValues(current => ({ ...current, [item.code]: { ...current[item.code], ...item.ai_review.suggestion } }));
    setAcceptedReviews(current => ({ ...current, [item.code]: true }));
    setRejectedReviews(current => ({ ...current, [item.code]: false }));
    if (item.code === "PRE_IMAGING") setImagingReviewed(true);
    setDirty(current => ({ ...current, [item.code]: true }));
  };

  const valueFor = item => {
    const { code } = item;
    const value = values[code];
    const withReviewedSources = result => ({ ...result, reviewed_source_refs: acceptedReviews[code] ? item.ai_review?.citations.map(citation => citation.ref) || [] : [] });
    if (code === "PRE_MEDICAL_HISTORY") return value.summary.trim() ? withReviewedSources({ summary: value.summary.trim() }) : null;
    if (code === "PRE_ALLERGY") return value.status === "PRESENT"
      ? value.allergen.trim() ? withReviewedSources({ status: value.status, allergen: value.allergen.trim() }) : null
      : withReviewedSources({ status: value.status });
    if (code === "PRE_VITALS") {
      const readings = [value.systolic, value.diastolic, value.pulse].map(Number);
      return readings.every(reading => Number.isFinite(reading) && reading > 0)
        ? withReviewedSources({ systolic: readings[0], diastolic: readings[1], pulse: readings[2] })
        : null;
    }
    if (code === "PRE_STERILIZATION") return value.cycle_or_tray_id.trim()
      ? withReviewedSources({ confirmed: true, cycle_or_tray_id: value.cycle_or_tray_id.trim() })
      : null;
    if (code === "PRE_IMAGING") return imagingReviewed && value.imaging_reference.trim()
      ? withReviewedSources({ reviewed: true, imaging_reference: value.imaging_reference.trim() })
      : null;
    return null;
  };

  const attest = async item => {
    const value = valueFor(item);
    if (!value) {
      setFieldErrors(current => ({ ...current, [item.code]: tr(`Hoàn thành các trường ${COPY[item.code][0][0].toLowerCase()} trước khi xác nhận.`, `Complete the ${COPY[item.code][0][1].toLowerCase()} fields before confirming.`) }));
      requestAnimationFrame(() => document.getElementById(`${item.code}-first`)?.focus());
      return;
    }
    setSaving(item.code);
    setError("");
    try {
      const response = await apiFetch(`/api/v1/encounters/${encounterId}/pre-treatment/${item.code}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({ value, performed_at: new Date().toISOString() }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || tr("Không thể xác nhận mục kiểm tra", "Unable to confirm checklist item"));
      setDirty(current => ({ ...current, [item.code]: false }));
      await load();
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSaving("");
    }
  };

  const resetDemo = async () => {
    setSaving("reset");
    setError("");
    try {
      const response = await apiFetch(`/api/v1/encounters/${encounterId}/pre-treatment/demo-reset`, { method: "POST", headers: { "X-Demo-Role": role } });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || tr("Không thể bắt đầu kịch bản demo mới", "Unable to start a fresh demo scenario"));
      setItems(result.items || []);
      setAudit(result.audit || []);
      setValues(INITIAL_VALUES);
      setDirty({});
      setFieldErrors({});
      setImagingReviewed(false);
      setAcceptedReviews({});
      setRejectedReviews({});
      const requiresImaging = result.procedure?.requires_imaging;
      setPersistedRequiresImaging(requiresImaging === true ? true : requiresImaging === false ? false : null);
      setProcedureChoice(requiresImaging === true ? "required" : requiresImaging === false ? "not-required" : "");
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSaving("");
    }
  };

  const saveProcedure = async event => {
    event.preventDefault();
    if (!procedureChoice) {
      setError(tr("Chọn yêu cầu hình ảnh trước khi lưu ngữ cảnh thủ thuật.", "Choose whether imaging is required before saving the procedure context."));
      return;
    }
    setSaving("procedure");
    setError("");
    try {
      const response = await apiFetch(`/api/v1/encounters/${encounterId}/pre-treatment/procedure`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({ requires_imaging: procedureChoice === "required", performed_at: new Date().toISOString() }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || tr("Không thể lưu ngữ cảnh thủ thuật", "Unable to save procedure context"));
      await load();
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSaving("");
    }
  };

  const fields = item => {
    const value = values[item.code];
    const invalid = Boolean(fieldErrors[item.code]);
    const describedBy = invalid ? `${item.code}-error` : undefined;
    if (item.code === "PRE_MEDICAL_HISTORY") return <label>{tr("Tóm tắt do con người kiểm tra", "Human-Reviewed Summary")}<textarea id={`${item.code}-first`} name="medical_history_summary" autoComplete="off" value={value.summary} onChange={event => update(item.code, "summary", event.target.value)} placeholder={tr("Tóm tắt tiền sử bệnh liên quan từ hồ sơ được trích dẫn…", "Summarize relevant medical history from cited records…")} rows="3" aria-invalid={invalid} aria-describedby={describedBy} /></label>;
    if (item.code === "PRE_ALLERGY") return <div className="field-group" role="group" aria-labelledby="allergy-status-label"><span id="allergy-status-label">{tr("Tình trạng dị ứng", "Allergy Status")}</span><div className="choice-row"><label><input type="radio" name="allergy_status" checked={value.status === "NONE_KNOWN"} onChange={() => update(item.code, "status", "NONE_KNOWN")} /> {tr("Không có dị ứng đã biết", "No Known Allergies")}</label><label><input type="radio" name="allergy_status" checked={value.status === "PRESENT"} onChange={() => update(item.code, "status", "PRESENT")} /> {tr("Có dị ứng", "Allergy Present")}</label></div>{value.status === "PRESENT" && <label>{tr("Tác nhân dị ứng", "Allergen")}<input id={`${item.code}-first`} name="allergen" autoComplete="off" value={value.allergen} onChange={event => update(item.code, "allergen", event.target.value)} placeholder={tr("ví dụ: penicillin…", "e.g., penicillin…")} aria-invalid={invalid} aria-describedby={describedBy} /></label>}</div>;
    if (item.code === "PRE_VITALS") return <div className="vitals-grid"><label>{tr("Tâm thu", "Systolic")}<input id={`${item.code}-first`} name="systolic" type="number" inputMode="numeric" autoComplete="off" min="1" value={value.systolic} onChange={event => update(item.code, "systolic", event.target.value)} placeholder="120" aria-invalid={invalid} aria-describedby={describedBy} /></label><label>{tr("Tâm trương", "Diastolic")}<input name="diastolic" type="number" inputMode="numeric" autoComplete="off" min="1" value={value.diastolic} onChange={event => update(item.code, "diastolic", event.target.value)} placeholder="80" aria-invalid={invalid} aria-describedby={describedBy} /></label><label>{tr("Mạch", "Pulse")}<input name="pulse" type="number" inputMode="numeric" autoComplete="off" min="1" value={value.pulse} onChange={event => update(item.code, "pulse", event.target.value)} placeholder="72" aria-invalid={invalid} aria-describedby={describedBy} /></label></div>;
    if (item.code === "PRE_STERILIZATION") return <label>{tr("Mã chu trình / khay", "Cycle / Tray ID")}<input id={`${item.code}-first`} name="cycle_or_tray_id" autoComplete="off" spellCheck="false" value={value.cycle_or_tray_id} onChange={event => update(item.code, "cycle_or_tray_id", event.target.value)} placeholder="AUTOCLAVE-2026-0718-A" aria-invalid={invalid} aria-describedby={describedBy} /></label>;
    return <div className="imaging-review"><div className="xray-mock" role="img" aria-label={tr("X-quang nha khoa mô phỏng có dấu kiểm tra AI gần răng 36", "Simulated dental X-ray with an AI review marker near tooth 36")}><span className="tooth tooth-one" /><span className="tooth tooth-two" /><span className="tooth tooth-three" /><span className="ai-marker">AI</span></div><p><strong>{tr("Hỗ trợ AI (mô phỏng)", "AI support (simulated)")}</strong> {tr("đánh dấu vùng có thể cần chú ý gần răng 36. Đây chỉ là gợi ý kiểm tra, không phải chẩn đoán.", "flagged a possible area near tooth 36. This is only a review cue, not a diagnosis.")}</p><label className="review-check"><input id={`${item.code}-first`} type="checkbox" checked={imagingReviewed} onChange={event => { setImagingReviewed(event.target.checked); setDirty(current => ({ ...current, [item.code]: true })); }} aria-invalid={invalid} aria-describedby={describedBy} /> {tr("Tôi đã kiểm tra hình ảnh và gợi ý AI", "I reviewed the image and AI cue")}</label><label>{tr("Tham chiếu hình ảnh", "Imaging Reference")}<input name="imaging_reference" autoComplete="off" spellCheck="false" value={value.imaging_reference} onChange={event => update(item.code, "imaging_reference", event.target.value)} placeholder="XRAY-2026-001" aria-invalid={invalid} aria-describedby={describedBy} /></label></div>;
  };

  const remaining = items.filter(item => item.applicable && item.evidence?.state !== "VERIFIED").length;
  const procedureMissing = persistedRequiresImaging === null;
  const totalRemaining = remaining + (procedureMissing ? 1 : 0);

  return <section className="pre-treatment" aria-busy={loading || Boolean(saving)}>
    <a className="skip-link" href="#safety-checklist">{tr("Đi tới Danh sách an toàn", "Skip to Safety Checklist")}</a>
    <header className="safety-header"><div><a href="/" className="back-link">← CareGuard Dental</a><p className="eyebrow">{tr("CA KHÁM", "ENCOUNTER")} <span translate="no">{encounterId.slice(-6)}</span> · {tr("TRƯỚC ĐIỀU TRỊ", "PRE-TREATMENT")}</p><h1>{tr("Cổng an toàn", "Safety Gate")}</h1><p>{tr("Xác nhận từng kiểm tra an toàn bắt buộc trước điều trị.", "Confirm each required safety check before treatment.")}</p></div><div className="demo-controls"><label>{tr("Vai trò", "Acting as")}<select value={role} onChange={event => setRole(event.target.value)} disabled={Boolean(saving)}><option value="FRONT_DESK">{tr("Lễ tân", "Front Desk")}</option><option value="ASSISTANT">{tr("Trợ lý", "Assistant")}</option><option value="DENTIST">{tr("Nha sĩ", "Dentist")}</option><option value="QA">QA</option></select></label><button type="button" className="reset-button" onClick={resetDemo} disabled={role !== "QA" || loading || Boolean(saving)}>{saving === "reset" ? tr("Đang bắt đầu…", "Starting…") : tr("Tạo demo mới (QA)", "Start fresh demo (QA)")}</button><span className={`readiness ${totalRemaining ? "needs-action" : "ready"}`} aria-live="polite"><strong>{totalRemaining ? tr(`${totalRemaining} mục bắt buộc`, `${totalRemaining} Required`) : tr("Sẵn sàng kiểm tra", "Ready for Review")}</strong><span>{tr(`${items.length - remaining}/${items.length} kiểm tra hoàn tất`, `${items.length - remaining} of ${items.length} checks complete`)}</span></span></div></header>

    {error && <p className="form-error" role="alert">{error} {tr("Hãy thử lại hoặc tải lại trang.", "Try again or reload the page.")}</p>}
    {!loading && <form className={`procedure-context ${procedureMissing ? "missing" : "declared"}`} onSubmit={saveProcedure}>
      <div><p className="eyebrow">{tr("NGỮ CẢNH THỦ THUẬT", "PROCEDURE CONTEXT")}</p><h2>{tr("Thủ thuật này có yêu cầu hình ảnh không?", "Is imaging required for this procedure?")}</h2><p>{tr("Khai báo này quyết định kiểm tra an toàn hình ảnh là bắt buộc hay không áp dụng.", "This declaration controls whether the imaging safety check is required or not applicable.")}</p></div>
      <label>{tr("Yêu cầu hình ảnh", "Imaging requirement")}<select value={procedureChoice} onChange={event => setProcedureChoice(event.target.value)} disabled={Boolean(saving)}><option value="">{tr("Chọn yêu cầu…", "Select requirement…")}</option><option value="required">{tr("Yêu cầu hình ảnh", "Imaging required")}</option><option value="not-required">{tr("Không yêu cầu hình ảnh", "Imaging not required")}</option></select></label>
      <button type="submit" className="confirm-button" disabled={!(["ASSISTANT", "DENTIST"].includes(role)) || Boolean(saving)}>{saving === "procedure" ? tr("Đang lưu…", "Saving…") : procedureMissing ? tr("Xác nhận yêu cầu", "Confirm requirement") : tr("Cập nhật yêu cầu", "Update requirement")}</button>
    </form>}
    {loading ? <p className="loading" aria-live="polite">{tr("Đang tải danh sách an toàn…", "Loading Safety Checklist…")}</p> : items.length === 0 ? <div className="empty-state"><h2>{tr("Không tìm thấy kiểm tra an toàn", "No Safety Checks Found")}</h2><p>{tr("Tải lại trang hoặc kiểm tra cấu hình ca khám.", "Reload the page or verify the encounter configuration.")}</p><button type="button" className="confirm-button" onClick={load}>{tr("Tải lại danh sách", "Reload Checklist")}</button></div> : <div className="safety-layout"><section id="safety-checklist" className="checklist" aria-label={tr("Danh sách trước điều trị", "Pre-treatment checklist")}>{items.map(item => {
      const [titleCopy, descriptionCopy] = COPY[item.code];
      const title = tr(...titleCopy);
      const description = tr(...descriptionCopy);
      const verified = item.evidence?.state === "VERIFIED";
      const notApplicable = !item.applicable;
      return <article className={`check-card ${verified ? "verified" : notApplicable ? "not-applicable" : "pending"}`} key={item.code}>
        <div className="check-icon" aria-hidden="true">{verified ? "✓" : notApplicable ? "—" : "!"}</div>
        <div className="check-content"><div className="check-title"><div><h2>{title}</h2><p>{description}</p></div><span className="status-pill">{verified ? tr("Đã xác minh", "Verified") : notApplicable ? tr("Không áp dụng", "Not Applicable") : tr("Cần xác nhận", "Needs Confirmation")}</span></div>
          {verified ? <div className="verified-detail"><strong>{evidenceSummary(item, tr)}</strong><span><span translate="no">{item.evidence.actor_role}</span> · {formatDate(item.evidence.value?.performed_at || item.evidence.updated_at, locale, tr)}</span></div>
              : notApplicable ? <div className="imaging-not-required"><p className="muted">{tr("Thủ thuật này không yêu cầu hình ảnh.", "This procedure does not require imaging.")}</p><div className="xray-mock compact" role="img" aria-label={tr("Xem trước X-quang nha khoa mô phỏng", "Simulated dental X-ray preview")}><span className="tooth tooth-one" /><span className="tooth tooth-two" /><span className="tooth tooth-three" /><span className="ai-marker">AI</span></div><p className="muted">{tr("Kiểm tra hình ảnh AI chỉ được hiển thị để demo; không có bằng chứng hình ảnh nào được tạo cho ca này.", "AI image review is shown here as a demo only; no imaging evidence is created for this encounter.")}</p></div>
              : <>{!rejectedReviews[item.code] && <section className="ai-review" aria-label={`${title} AI review`}><strong>{tr("Gợi ý AI — chưa xác minh", "AI suggestion — unverified")}</strong><ul>{item.ai_review.citations.map(citation => <li key={citation.ref}><b>{citation.label}</b>: {citation.excerpt}</li>)}</ul><div className="review-actions"><button type="button" className="review-button" onClick={() => useSuggestion(item)}>{tr("Dùng gợi ý", "Use suggestion")}</button><button type="button" className="reject-button" onClick={() => { setRejectedReviews(current => ({ ...current, [item.code]: true })); setAcceptedReviews(current => ({ ...current, [item.code]: false })); }}>{tr("Từ chối gợi ý", "Reject suggestion")}</button></div>{acceptedReviews[item.code] && <span className="reviewed-status">{tr("Đã chọn hồ sơ trích dẫn để kiểm tra", "Cited records selected for review")}</span>}</section>}<form noValidate onSubmit={event => { event.preventDefault(); attest(item); }}><fieldset disabled={Boolean(saving)}>{fields(item)}{fieldErrors[item.code] && <p id={`${item.code}-error`} className="field-error" role="alert">{fieldErrors[item.code]}</p>}<button type="submit" className="confirm-button" aria-live="polite">{saving === item.code ? tr("Đang xác nhận…", "Confirming…") : tr(`Xác nhận ${title}`, `Confirm ${title}`)}</button></fieldset></form></>}
        </div>
      </article>;
    })}</section><aside className="safety-aside"><p className="eyebrow">{tr("CÁCH HOẠT ĐỘNG", "HOW IT WORKS")}</p><h2>{tr("Con người quyết định, bằng chứng có thể kiểm tra", "Human Decision, Auditable Evidence")}</h2><ol><li>{tr("Chọn vai trò nhân viên.", "Choose the staff role.")}</li><li>{tr("Nhập dữ liệu tối thiểu của kiểm tra hiện tại.", "Enter the minimum current-check data.")}</li><li>{tr("Xác nhận mục với vai trò nhân viên.", "Confirm the item as staff.")}</li><li>{tr("Lưu bằng chứng đã xác minh, người thực hiện và thời gian UTC.", "Store verified evidence, actor, and UTC time.")}</li></ol><div className="audit-trail"><strong>{tr("Nhật ký kiểm tra", "Audit trail")}</strong>{audit.length ? <ul>{audit.slice(0, 5).map((event, index) => <li key={`${event.created_at}-${index}`}><b>{event.action === "PRE_TREATMENT_DEMO_RESET" ? tr("QA đã bắt đầu kịch bản mới", "QA started a fresh scenario") : tr(`${event.actor_role} đã xác nhận ${event.metadata?.code?.replace("PRE_", "").replaceAll("_", " ")}`, `${event.actor_role} confirmed ${event.metadata?.code?.replace("PRE_", "").replaceAll("_", " ")}`)}</b><span>{formatDate(event.created_at, locale, tr)}</span></li>)}</ul> : <p>{tr("Chưa có hoạt động trước điều trị.", "No pre-treatment activity yet.")}</p>}</div><div className="ai-boundary"><strong>{tr("Ranh giới AI", "AI Boundary")}</strong><p>{tr("AI có thể soạn bản tóm tắt tiền sử có trích dẫn. AI không bao giờ xác nhận kiểm tra hoặc quyết định mức sẵn sàng điều trị.", "AI may draft a cited history summary. It never confirms a check or decides treatment readiness.")}</p></div></aside></div>}
  </section>;
}

export const route = { path: "/pre-treatment", label: "Pre-treatment", Component: PreTreatment };
