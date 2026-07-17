import React, { useEffect, useState } from "react";

const ID = "00000000-0000-0000-0000-000000000003";
const stages = ["CHECK_IN", "PRE_TREATMENT", "TREATMENT", "POST_TREATMENT", "CLOSED"];

function Encounter() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = () => fetch(`/api/v1/encounters/${ID}`, { headers: { "X-Demo-Role": "DENTIST" } })
    .then((response) => response.ok ? response.json() : Promise.reject(new Error("Không tải được ca khám")))
    .then(setData).catch((reason) => setError(reason.message));

  useEffect(load, []);

  const advance = () => fetch(`/api/v1/encounters/${ID}/stage`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Demo-Role": "DENTIST" },
    body: JSON.stringify({ stage: stages[stages.indexOf(data.stage) + 1], version: data.version }),
  }).then((response) => response.ok ? response.json() : response.json().then((body) => Promise.reject(new Error(body.message))))
    .then(setData).catch((reason) => setError(reason.message));

  if (error) return <p role="alert">{error}</p>;
  if (!data) return <p>Đang tải ca khám…</p>;
  const next = stages[stages.indexOf(data.stage) + 1];
  return <section>
    <h2>{data.patient.full_name}</h2>
    <p>MRN: {data.patient.mrn} · Ghế: {data.appointment?.chair ?? "—"}</p>
    <ol>{stages.map((stage) => <li key={stage} aria-current={stage === data.stage ? "step" : undefined}>{stage}</li>)}</ol>
    {next && <button type="button" onClick={advance}>Chuyển sang {next}</button>}
  </section>;
}

export const route = { path: "/encounter", label: "Encounter", Component: Encounter };
