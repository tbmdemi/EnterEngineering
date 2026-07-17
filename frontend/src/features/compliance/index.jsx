import React, { useState } from "react";

const ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";

function Component() {
  const [readiness, setReadiness] = useState(null);

  async function load() {
    const response = await fetch(`/api/v1/encounters/${ENCOUNTER_ID}/readiness`, {
      headers: { "X-Demo-Role": "QA" },
    });
    setReadiness(await response.json());
  }

  return <section><h2>Compliance & Audit</h2><button onClick={load}>Load readiness</button><pre>{readiness ? JSON.stringify(readiness, null, 2) : "Chưa tải"}</pre></section>;
}

export const route = { path: "/compliance", label: "Compliance", Component };
