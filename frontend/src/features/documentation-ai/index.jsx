import React, { useState } from "react";

function DocumentationAi() {
  const [run, setRun] = useState(null);
  const [encounterId, setEncounterId] = useState("00000000-0000-0000-0000-000000000003");
  const [note, setNote] = useState("");
  const [medicationPrescribed, setMedicationPrescribed] = useState(false);
  const [saved, setSaved] = useState(false);

  async function saveDocumentation(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/v1/documentation", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Demo-Role": "DENTIST" },
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
    setSaved(response.ok);
  }

  async function extract(event) {
    event.preventDefault();
    const response = await fetch("/api/v1/ai/extract-note", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Demo-Role": "DENTIST" },
      body: JSON.stringify({ encounter_id: encounterId, note }),
    });
    setRun(await response.json());
  }

  async function review(action) {
    const fact = run.facts[0];
    const evidence_code = fact.fact === "procedure_documented" ? "DOC_TOOTH_SURFACE" : "DOC_PROGRESS_NOTE";
    const response = await fetch(`/api/v1/ai/runs/${run.ai_run_id}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Demo-Role": "DENTIST" },
      body: action === "accept" ? JSON.stringify({ evidence_code }) : undefined,
    });
    const result = await response.json();
    setRun(current => ({ ...current, state: result.state }));
  }

  return <section>
    <h2>Documentation &amp; Staff AI</h2>
    <form onSubmit={saveDocumentation}>
      <h3>Clinical documentation</h3>
      <label>Encounter ID<input value={encounterId} onChange={event => setEncounterId(event.target.value)} required /></label>
      <label><input type="checkbox" name="consent_signed" /> Consent signed</label>
      <label><input type="checkbox" name="treatment_plan_signed" /> Treatment plan signed</label>
      <label>Progress note<textarea name="progress_note" required /></label>
      <label>Tooth<input name="tooth" required /></label>
      <label>Surface<input name="surface" required /></label>
      <label><input type="checkbox" name="medication_prescribed" checked={medicationPrescribed} onChange={event => setMedicationPrescribed(event.target.checked)} /> Medication prescribed</label>
      {medicationPrescribed && <label>Medication details<input name="medication_detail" required /></label>}
      <button type="submit">Save documentation</button>{saved && <span> Saved</span>}
    </form>
    <form onSubmit={extract}>
      <h3>AI note extraction</h3>
      <label>Encounter ID<input value={encounterId} onChange={event => setEncounterId(event.target.value)} required /></label>
      <label>Progress note<textarea name="progress_note" value={note} onChange={event => setNote(event.target.value)} required /></label>
      <button type="submit">Extract note</button>
    </form>
    {run?.facts?.map((fact, index) => <article key={index}><strong>{fact.fact}</strong><blockquote>{fact.source_span}</blockquote></article>)}
    {run?.state === "UNVERIFIED" && <p><button type="button" onClick={() => review("accept")}>Accept</button> <button type="button" onClick={() => review("reject")}>Reject</button></p>}
  </section>;
}

export const route = { path: "/documentation-ai", label: "Documentation & Staff AI", Component: DocumentationAi };
