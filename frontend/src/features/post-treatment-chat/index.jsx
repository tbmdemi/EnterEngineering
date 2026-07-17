import React, { useState } from "react";

function PostTreatmentChat() {
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    const response = await fetch("/api/v1/portal/chat", { method: "POST", headers: { "Content-Type": "application/json", "X-Demo-Role": "PATIENT" }, body: JSON.stringify({ message }) });
    setReply(await response.json());
  };
  return <section><h2>Patient chat</h2><form onSubmit={submit}><label>Câu hỏi <input value={message} onChange={(e) => setMessage(e.target.value)} required /></label><button>Gửi</button></form>{reply && <article aria-live="polite"><p>{reply.answer}</p>{reply.citations?.length > 0 && <small>Nguồn: {reply.citations.join(", ")}</small>}</article>}</section>;
}

export const route = { path: "/patient-chat", label: "Patient chat", Component: PostTreatmentChat };
