import React, { useState } from "react";

function DocumentationAi() {
  const [medicationUsed, setMedicationUsed] = useState(false);
  return <section>
    <h2>Documentation &amp; Staff AI</h2>
    <form>
      <label><input type="checkbox" name="consent_signed" /> Consent signed</label>
      <label><input type="checkbox" name="treatment_plan_signed" /> Treatment plan signed</label>
      <label>Progress note<textarea name="progress_note" required /></label>
      <label>Tooth<input name="tooth" required /></label>
      <label>Surface<input name="surface" required /></label>
      <label><input type="checkbox" checked={medicationUsed} onChange={event => setMedicationUsed(event.target.checked)} /> Medication used</label>
      {medicationUsed && <label>Medication detail<input name="medication_detail" required /></label>}
      <button type="submit">Save documentation</button>
    </form>
  </section>;
}

export const route = { path: "/documentation-ai", label: "Documentation & Staff AI", Component: DocumentationAi };
