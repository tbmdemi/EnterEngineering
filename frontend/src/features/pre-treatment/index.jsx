import React, { useEffect, useState } from "react";

const ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";

function PreTreatment() {
  const [items, setItems] = useState([]);
  const load = () => fetch(`/api/v1/encounters/${ENCOUNTER_ID}/pre-treatment`, { headers: { "X-Demo-Role": "ASSISTANT" } }).then(r => r.json()).then(r => setItems(r.items || []));
  useEffect(load, []);
  const attest = item => fetch(`/api/v1/encounters/${ENCOUNTER_ID}/pre-treatment/${item.code}`, {
    method: "PUT", headers: { "Content-Type": "application/json", "X-Demo-Role": "ASSISTANT" },
    body: JSON.stringify({ value: { confirmed: true }, performed_at: new Date().toISOString() }),
  }).then(load);

  return <main><h1>Pre-treatment safety</h1>{items.map(item => <label key={item.code}>
    <input type="checkbox" checked={Boolean(item.evidence) || !item.applicable} disabled={!item.applicable || Boolean(item.evidence)} onChange={() => attest(item)} />
    {item.code.replace("PRE_", "").replaceAll("_", " ")}{!item.applicable && " — not applicable"}
  </label>)}</main>;
}

export const route = { path: "/pre-treatment", label: "Pre-treatment", Component: PreTreatment };
