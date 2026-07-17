import React, { useState } from "react";

function DocumentationAi() {
  const [run, setRun] = useState(null);
  const [encounterId, setEncounterId] = useState("");
  const [note, setNote] = useState("");

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
    <form onSubmit={extract}>
      <label>Encounter ID<input value={encounterId} onChange={event => setEncounterId(event.target.value)} required /></label>
      <label>Progress note<textarea name="progress_note" value={note} onChange={event => setNote(event.target.value)} required /></label>
      <button type="submit">Extract note</button>
    </form>
    {run?.facts?.map((fact, index) => <article key={index}><strong>{fact.fact}</strong><blockquote>{fact.source_span}</blockquote></article>)}
    {run?.state === "UNVERIFIED" && <p><button type="button" onClick={() => review("accept")}>Accept</button> <button type="button" onClick={() => review("reject")}>Reject</button></p>}
  </section>;
}

export const route = { path: "/documentation-ai", label: "Documentation & Staff AI", Component: DocumentationAi };
