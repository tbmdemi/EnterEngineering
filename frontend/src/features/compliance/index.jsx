import React, { useState } from "react";

const ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";

function Component() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function request(path, method = "GET") {
    setError("");
    const response = await fetch(path, {
      method,
      headers: { "X-Demo-Role": "QA" },
    });
    const body = await response.json();
    if (!response.ok) return setError(body.message || "Request failed");
    setResult(body);
  }

  return <section>
    <h2>Compliance & Audit</h2>
    <p>
      <button onClick={() => request(`/api/v1/encounters/${ENCOUNTER_ID}/evaluate`, "POST")}>Evaluate</button>{" "}
      <button onClick={() => request(`/api/v1/encounters/${ENCOUNTER_ID}/readiness`)}>Readiness</button>{" "}
      <button onClick={() => request(`/api/v1/audit-events?encounter_id=${ENCOUNTER_ID}`)}>Audit</button>{" "}
      <button onClick={() => request("/api/v1/dashboard")}>Dashboard</button>
    </p>
    {error && <p role="alert">{error}</p>}
    <pre>{result ? JSON.stringify(result, null, 2) : "Chưa tải"}</pre>
  </section>;
}

export const route = { path: "/compliance", label: "Compliance", Component };
