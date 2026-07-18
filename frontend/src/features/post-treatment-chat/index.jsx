import React, { useState } from "react";

function PostTreatmentChat() {
  const [role, setRole] = useState("DENTIST");
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState(null);
  const [care, setCare] = useState("");
  const [recall, setRecall] = useState("");
  const [monitor, setMonitor] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const request = async (url, body, demoRole) => {
    setPending(true); setError("");
    try {
      const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Demo-Role": demoRole }, body: JSON.stringify(body) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Yêu cầu thất bại");
      setReply(data);
    } catch (failure) { setError(failure.message); } finally { setPending(false); }
  };
  const chat = async (event) => {
    event.preventDefault();
    await request("/api/v1/portal/chat", { message }, "PATIENT");
  };
  const release = async (event) => {
    event.preventDefault();
    await request("/api/v1/encounters/00000000-0000-0000-0000-000000000003/release", { care_instructions: care, recall_at: new Date(recall).toISOString(), monitor_until: new Date(monitor).toISOString() }, "DENTIST");
  };
  return <section><h2>Post-treatment</h2><label>Vai trò <select value={role} onChange={(event) => { setRole(event.target.value); setReply(null); setError(""); }}><option value="DENTIST">Dentist</option><option value="PATIENT">Patient</option></select></label>
    {role === "DENTIST" ? <form onSubmit={release}><label>Hướng dẫn <textarea value={care} onChange={(e) => setCare(e.target.value)} required /></label><label>Tái khám <input type="datetime-local" value={recall} onChange={(e) => setRecall(e.target.value)} required /></label><label>Theo dõi đến <input type="datetime-local" value={monitor} onChange={(e) => setMonitor(e.target.value)} required /></label><button disabled={pending}>{pending ? "Đang phát hành…" : "Phát hành"}</button></form>
      : <form onSubmit={chat}><label>Câu hỏi <input value={message} onChange={(e) => setMessage(e.target.value)} required /></label><button disabled={pending}>{pending ? "Đang gửi…" : "Gửi"}</button></form>}
    {error && <p role="alert">{error}</p>}{reply && <article aria-live="polite"><p>{reply.answer || (reply.released && "Đã phát hành hướng dẫn sau điều trị.")}</p>{reply.citations?.length > 0 && <small>Nguồn: {reply.citations.join(", ")}</small>}</article>}</section>;
}

export const route = { path: "/post-treatment", label: "Post-treatment", Component: PostTreatmentChat };
