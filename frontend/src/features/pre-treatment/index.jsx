import React, { useEffect, useState } from "react";

const ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";

function PreTreatment() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null);
  const [error, setError] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/encounters/${ENCOUNTER_ID}/pre-treatment`, { headers: { "X-Demo-Role": "ASSISTANT" } });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || "Unable to load checklist");
      setItems(result.items || []);
    } catch (caught) {
      setError(caught.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  const attest = async item => {
    setSaving(item.code);
    setError("");
    try {
      const response = await fetch(`/api/v1/encounters/${ENCOUNTER_ID}/pre-treatment/${item.code}`, {
        method: "PUT", headers: { "Content-Type": "application/json", "X-Demo-Role": "ASSISTANT" },
        body: JSON.stringify({ value: { confirmed: true }, performed_at: new Date().toISOString() }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.message || "Unable to attest checklist item");
      await load();
    } catch (caught) {
      setError(caught.message);
    } finally {
      setSaving(null);
    }
  };

  return <main aria-busy={loading || Boolean(saving)}><h1>Pre-treatment safety</h1>
    {error && <p role="alert">{error}</p>}
    {loading ? <p>Loading checklist…</p> : items.map(item => {
      const verified = item.evidence?.state === "VERIFIED";
      const completed = verified || !item.applicable;
      const performedAt = item.evidence?.value?.performed_at;
      return <label key={item.code}>
        <input type="checkbox" checked={completed} disabled={!item.applicable || completed || Boolean(saving)} onChange={() => attest(item)} />
        {item.code.replace("PRE_", "").replaceAll("_", " ")}{!item.applicable && " — not applicable"}
        {verified && <small> — {item.evidence.actor_role} at {performedAt || item.evidence.updated_at}</small>}
      </label>;
    })}
  </main>;
}

export const route = { path: "/pre-treatment", label: "Pre-treatment", Component: PreTreatment };
