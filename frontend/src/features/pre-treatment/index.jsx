import React, { useEffect, useState } from "react";
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
  PRE_MEDICAL_HISTORY: ["Medical History", "Review the cited record and confirm the summary."],
  PRE_ALLERGY: ["Allergy", "Confirm the patient allergy status before treatment."],
  PRE_VITALS: ["Vitals", "Record the current blood pressure and pulse."],
  PRE_STERILIZATION: ["Sterilization", "Confirm the sterile setup and its cycle or tray ID."],
  PRE_IMAGING: ["Imaging", "Confirm the reviewed imaging reference when required."],
};

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : DATE_FORMAT.format(date);
}

function evidenceSummary(item) {
  const value = item.evidence?.value || {};
  if (item.code === "PRE_MEDICAL_HISTORY") return value.summary || "Medical history reviewed";
  if (item.code === "PRE_ALLERGY") return value.status === "PRESENT" ? `Allergy: ${value.allergen}` : "No known allergies";
  if (item.code === "PRE_VITALS") return `${value.systolic}/${value.diastolic} mmHg · pulse ${value.pulse} bpm`;
  if (item.code === "PRE_STERILIZATION") return `Cycle / tray: ${value.cycle_or_tray_id}`;
  if (item.code === "PRE_IMAGING") return value.not_applicable ? "Not applicable" : `Reference: ${value.imaging_reference}`;
  return "Verified";
}

function PreTreatment() {
  const { encounterId, role, setRole } = useDemoContext();
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

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/encounters/${encounterId}/pre-treatment`, { headers: { "X-Demo-Role": role } });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || "Unable to load checklist");
      setItems(result.items || []);
      setAudit(result.audit || []);
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
      setFieldErrors(current => ({ ...current, [item.code]: `Complete the ${COPY[item.code][0].toLowerCase()} fields before confirming.` }));
      requestAnimationFrame(() => document.getElementById(`${item.code}-first`)?.focus());
      return;
    }
    setSaving(item.code);
    setError("");
    try {
      const response = await fetch(`/api/v1/encounters/${encounterId}/pre-treatment/${item.code}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({ value, performed_at: new Date().toISOString() }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || "Unable to confirm checklist item");
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
      const response = await fetch(`/api/v1/encounters/${encounterId}/pre-treatment/demo-reset`, { method: "POST", headers: { "X-Demo-Role": role } });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || "Unable to start a fresh demo scenario");
      setItems(result.items || []);
      setAudit(result.audit || []);
      setValues(INITIAL_VALUES);
      setDirty({});
      setFieldErrors({});
      setImagingReviewed(false);
      setAcceptedReviews({});
      setRejectedReviews({});
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
    if (item.code === "PRE_MEDICAL_HISTORY") return <label>Human-Reviewed Summary<textarea id={`${item.code}-first`} name="medical_history_summary" autoComplete="off" value={value.summary} onChange={event => update(item.code, "summary", event.target.value)} placeholder="Summarize relevant medical history from cited records…" rows="3" aria-invalid={invalid} aria-describedby={describedBy} /></label>;
    if (item.code === "PRE_ALLERGY") return <div className="field-group" role="group" aria-labelledby="allergy-status-label"><span id="allergy-status-label">Allergy Status</span><div className="choice-row"><label><input type="radio" name="allergy_status" checked={value.status === "NONE_KNOWN"} onChange={() => update(item.code, "status", "NONE_KNOWN")} /> No Known Allergies</label><label><input type="radio" name="allergy_status" checked={value.status === "PRESENT"} onChange={() => update(item.code, "status", "PRESENT")} /> Allergy Present</label></div>{value.status === "PRESENT" && <label>Allergen<input id={`${item.code}-first`} name="allergen" autoComplete="off" value={value.allergen} onChange={event => update(item.code, "allergen", event.target.value)} placeholder="e.g., penicillin…" aria-invalid={invalid} aria-describedby={describedBy} /></label>}</div>;
    if (item.code === "PRE_VITALS") return <div className="vitals-grid"><label>Systolic<input id={`${item.code}-first`} name="systolic" type="number" inputMode="numeric" autoComplete="off" min="1" value={value.systolic} onChange={event => update(item.code, "systolic", event.target.value)} placeholder="e.g., 120…" aria-invalid={invalid} aria-describedby={describedBy} /></label><label>Diastolic<input name="diastolic" type="number" inputMode="numeric" autoComplete="off" min="1" value={value.diastolic} onChange={event => update(item.code, "diastolic", event.target.value)} placeholder="e.g., 80…" aria-invalid={invalid} aria-describedby={describedBy} /></label><label>Pulse<input name="pulse" type="number" inputMode="numeric" autoComplete="off" min="1" value={value.pulse} onChange={event => update(item.code, "pulse", event.target.value)} placeholder="e.g., 72…" aria-invalid={invalid} aria-describedby={describedBy} /></label></div>;
    if (item.code === "PRE_STERILIZATION") return <label>Cycle / Tray ID<input id={`${item.code}-first`} name="cycle_or_tray_id" autoComplete="off" spellCheck="false" value={value.cycle_or_tray_id} onChange={event => update(item.code, "cycle_or_tray_id", event.target.value)} placeholder="e.g., AUTOCLAVE-2026-0718-A…" aria-invalid={invalid} aria-describedby={describedBy} /></label>;
    return <div className="imaging-review"><div className="xray-mock" role="img" aria-label="Simulated dental X-ray with an AI review marker near tooth 36"><span className="tooth tooth-one" /><span className="tooth tooth-two" /><span className="tooth tooth-three" /><span className="ai-marker">AI</span></div><p><strong>AI support (simulated)</strong> flagged a possible area near tooth 36. This is only a review cue, not a diagnosis.</p><label className="review-check"><input id={`${item.code}-first`} type="checkbox" checked={imagingReviewed} onChange={event => { setImagingReviewed(event.target.checked); setDirty(current => ({ ...current, [item.code]: true })); }} aria-invalid={invalid} aria-describedby={describedBy} /> I reviewed the image and AI cue</label><label>Imaging Reference<input name="imaging_reference" autoComplete="off" spellCheck="false" value={value.imaging_reference} onChange={event => update(item.code, "imaging_reference", event.target.value)} placeholder="e.g., XRAY-2026-001…" aria-invalid={invalid} aria-describedby={describedBy} /></label></div>;
  };

  const remaining = items.filter(item => item.applicable && item.evidence?.state !== "VERIFIED").length;

  return <section className="pre-treatment" aria-busy={loading || Boolean(saving)}>
    <a className="skip-link" href="#safety-checklist">Skip to Safety Checklist</a>
    <header className="safety-header"><div><a href="/" className="back-link">← CareGuard Dental</a><p className="eyebrow">ENCOUNTER <span translate="no">{encounterId.slice(-6)}</span> · PRE-TREATMENT</p><h1>Safety Gate</h1><p>Confirm each required safety check before treatment.</p></div><div className="demo-controls"><label>Acting as<select value={role} onChange={event => setRole(event.target.value)} disabled={Boolean(saving)}><option value="FRONT_DESK">Front Desk</option><option value="ASSISTANT">Assistant</option><option value="DENTIST">Dentist</option><option value="QA">QA</option></select></label><button type="button" className="reset-button" onClick={resetDemo} disabled={role !== "QA" || loading || Boolean(saving)}>{saving === "reset" ? "Starting…" : "Start fresh demo (QA)"}</button><span className={`readiness ${remaining ? "needs-action" : "ready"}`} aria-live="polite"><strong>{remaining ? `${remaining} Required` : "Ready for Review"}</strong><span>{items.length - remaining} of {items.length} checks complete</span></span></div></header>

    {error && <p className="form-error" role="alert">{error} Try again or reload the page.</p>}
    {loading ? <p className="loading" aria-live="polite">Loading Safety Checklist…</p> : items.length === 0 ? <div className="empty-state"><h2>No Safety Checks Found</h2><p>Reload the page or verify the encounter configuration.</p><button type="button" className="confirm-button" onClick={load}>Reload Checklist</button></div> : <div className="safety-layout"><section id="safety-checklist" className="checklist" aria-label="Pre-treatment checklist">{items.map(item => {
      const [title, description] = COPY[item.code];
      const verified = item.evidence?.state === "VERIFIED";
      const notApplicable = !item.applicable;
      return <article className={`check-card ${verified ? "verified" : notApplicable ? "not-applicable" : "pending"}`} key={item.code}>
        <div className="check-icon" aria-hidden="true">{verified ? "✓" : notApplicable ? "—" : "!"}</div>
        <div className="check-content"><div className="check-title"><div><h2>{title}</h2><p>{description}</p></div><span className="status-pill">{verified ? "Verified" : notApplicable ? "Not Applicable" : "Needs Confirmation"}</span></div>
          {verified ? <div className="verified-detail"><strong>{evidenceSummary(item)}</strong><span><span translate="no">{item.evidence.actor_role}</span> · {formatDate(item.evidence.value?.performed_at || item.evidence.updated_at)}</span></div>
              : notApplicable ? <div className="imaging-not-required"><p className="muted">This procedure does not require imaging.</p><div className="xray-mock compact" role="img" aria-label="Simulated dental X-ray preview"><span className="tooth tooth-one" /><span className="tooth tooth-two" /><span className="tooth tooth-three" /><span className="ai-marker">AI</span></div><p className="muted">AI image review is shown here as a demo only; no imaging evidence is created for this encounter.</p></div>
              : <>{!rejectedReviews[item.code] && <section className="ai-review" aria-label={`${title} AI review`}><strong>AI suggestion — unverified</strong><ul>{item.ai_review.citations.map(citation => <li key={citation.ref}><b>{citation.label}</b>: {citation.excerpt}</li>)}</ul><div className="review-actions"><button type="button" className="review-button" onClick={() => useSuggestion(item)}>Use suggestion</button><button type="button" className="reject-button" onClick={() => { setRejectedReviews(current => ({ ...current, [item.code]: true })); setAcceptedReviews(current => ({ ...current, [item.code]: false })); }}>Reject suggestion</button></div>{acceptedReviews[item.code] && <span className="reviewed-status">Cited records selected for review</span>}</section>}<form noValidate onSubmit={event => { event.preventDefault(); attest(item); }}><fieldset disabled={Boolean(saving)}>{fields(item)}{fieldErrors[item.code] && <p id={`${item.code}-error`} className="field-error" role="alert">{fieldErrors[item.code]}</p>}<button type="submit" className="confirm-button" aria-live="polite">{saving === item.code ? "Confirming…" : `Confirm ${title}`}</button></fieldset></form></>}
        </div>
      </article>;
    })}</section><aside className="safety-aside"><p className="eyebrow">HOW IT WORKS</p><h2>Human Decision, Auditable Evidence</h2><ol><li>Choose the staff role.</li><li>Enter the minimum current-check data.</li><li>Confirm the item as staff.</li><li>Store verified evidence, actor, and UTC time.</li></ol><div className="audit-trail"><strong>Audit trail</strong>{audit.length ? <ul>{audit.slice(0, 5).map((event, index) => <li key={`${event.created_at}-${index}`}><b>{event.action === "PRE_TREATMENT_DEMO_RESET" ? "QA started a fresh scenario" : `${event.actor_role} confirmed ${event.metadata?.code?.replace("PRE_", "").replaceAll("_", " ")}`}</b><span>{formatDate(event.created_at)}</span></li>)}</ul> : <p>No pre-treatment activity yet.</p>}</div><div className="ai-boundary"><strong>AI Boundary</strong><p>AI may draft a cited history summary. It never confirms a check or decides treatment readiness.</p></div></aside></div>}
  </section>;
}

export const route = { path: "/pre-treatment", label: "Pre-treatment", Component: PreTreatment };
