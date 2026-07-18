import React, { useMemo, useState } from "react";
import { apiFetch } from "../../api";
import { useDemoContext } from "../../demo-context";
import "./style.css";

function localDateTime(daysFromNow) {
  const value = new Date(Date.now() + daysFromNow * 86400000);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
}

function PostTreatmentChat() {
  const { encounterId, role, routeHref, setRole } = useDemoContext();
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState(null);
  const [care, setCare] = useState("Giữ vùng điều trị sạch, tránh thức ăn quá nóng trong 24 giờ đầu.");
  const [recall, setRecall] = useState(() => localDateTime(30));
  const [monitor, setMonitor] = useState(() => localDateTime(7));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const isPatient = role === "PATIENT";
  const earliestDateTime = localDateTime(0);
  const releaseContract = useMemo(() => {
    const now = Date.now();
    const recallAt = Date.parse(recall);
    const monitorUntil = Date.parse(monitor);
    const careReady = care.trim().length > 0;
    const monitorReady = Number.isFinite(monitorUntil) && monitorUntil > now;
    const recallReady = Number.isFinite(recallAt) && recallAt > now;
    const ordered = monitorReady && recallReady && monitorUntil <= recallAt;
    return { careReady, monitorReady, recallReady, ordered, ready: careReady && ordered };
  }, [care, monitor, recall]);

  const request = async (url, body) => {
    setPending(true);
    setError("");
    setReply(null);
    try {
      const response = await apiFetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || "Yêu cầu thất bại");
      setReply(data);
    } catch (failure) {
      setError(failure.message);
    } finally {
      setPending(false);
    }
  };

  const chat = event => {
    event.preventDefault();
    return request("/api/v1/portal/chat", { message, encounter_id: encounterId });
  };

  const release = event => {
    event.preventDefault();
    if (!releaseContract.ready) {
      setError("Hướng dẫn không được để trống; thời gian theo dõi phải ở tương lai và không sau lịch tái khám.");
      return;
    }
    return request(`/api/v1/encounters/${encounterId}/release`, {
      care_instructions: care.trim(),
      recall_at: new Date(recall).toISOString(),
      monitor_until: new Date(monitor).toISOString(),
    });
  };

  const releaseItems = useMemo(() => [
    ["Care instruction", releaseContract.careReady ? "Ready" : "Missing"],
    ["Recall date", releaseContract.recallReady && releaseContract.ordered ? "Ready" : "Invalid"],
    ["Monitoring window", releaseContract.monitorReady && releaseContract.ordered ? "Ready" : "Invalid"],
  ], [releaseContract]);

  return <section className="post-page" aria-labelledby="post-title">
    <header className="post-hero">
      <div>
        <p className="post-eyebrow">Module 05 · Continuity of care</p>
        <h1 id="post-title">Post-treatment &amp; Patient Chat</h1>
        <p>Phát hành nội dung đã duyệt cho bệnh nhân, sau đó trả lời từ đúng released record hoặc approved clinical card.</p>
      </div>
      <div className="post-role-switch" aria-label="Post-treatment view">
        <button className={!isPatient ? "is-active" : ""} type="button" onClick={() => setRole("DENTIST")}><span>Staff</span><strong>Release summary</strong></button>
        <button className={isPatient ? "is-active" : ""} type="button" onClick={() => setRole("PATIENT")}><span>Patient</span><strong>Portal chat</strong></button>
      </div>
    </header>

    {error && <div className="post-notice is-error" role="alert"><strong>Không thể hoàn tất</strong><span>{error}</span></div>}
    {reply?.released && <div className="post-notice is-success" role="status"><strong>Đã phát hành</strong><span>Ba evidence items hiện có thể được patient portal sử dụng.</span></div>}

    {!isPatient ? <div className="post-grid">
      <form className="post-card release-card" onSubmit={release}>
        <div className="post-card-heading"><div><span>Release package</span><h2>Patient care summary</h2></div><small>DENTIST only</small></div>
        <label><span>Care instructions</span><textarea value={care} onChange={event => setCare(event.target.value)} required /></label>
        <div className="post-date-grid">
          <label><span>Recall appointment</span><input type="datetime-local" value={recall} min={monitor || earliestDateTime} onChange={event => setRecall(event.target.value)} required /></label>
          <label><span>Monitor until</span><input type="datetime-local" value={monitor} min={earliestDateTime} max={recall || undefined} onChange={event => setMonitor(event.target.value)} required /></label>
        </div>
        <small>Thời gian theo dõi phải ở tương lai và kết thúc trước hoặc đúng lịch tái khám.</small>
        <div className="release-warning"><span aria-hidden="true">!</span><p><strong>Release boundary</strong>Chỉ VERIFIED evidence được đánh dấu released. Draft và staff-only note không xuất hiện ở patient portal.</p></div>
        <button type="submit" disabled={pending || role !== "DENTIST" || !releaseContract.ready}>{pending ? "Đang phát hành…" : "Release to patient →"}</button>
        {role !== "DENTIST" && <small>Chọn role DENTIST để phát hành.</small>}
      </form>

      <aside className="post-card release-readiness">
        <div className="post-card-heading"><div><span>Pre-flight check</span><h2>Release readiness</h2></div><small>Encounter #{encounterId.slice(-6)}</small></div>
        <ul>{releaseItems.map(([label, state], index) => <li key={label}><i>{index + 1}</i><span><strong>{label}</strong><small>POST_{label.toUpperCase().replaceAll(" ", "_")}</small></span><b className={state === "Ready" ? "is-ready" : ""}>{state}</b></li>)}</ul>
        <div className="post-stage-note"><span>Required stage</span><strong>POST_TREATMENT only</strong><p>CLOSED là bất biến; hãy phát hành trước khi đóng encounter.</p></div>
      </aside>
    </div> : <div className="patient-chat-layout">
      <aside className="patient-portal-card">
        <div className="patient-avatar" aria-hidden="true">PT</div>
        <p>Patient portal</p><h2>Your after-care assistant</h2>
        <dl><div><dt>Encounter</dt><dd>#{encounterId.slice(-6)}</dd></div><div><dt>Source rule</dt><dd>Released only</dd></div><div><dt>Safety</dt><dd>Citation or abstain</dd></div></dl>
        <div className="portal-safety"><strong>Emergency boundary</strong><span>Red-flag symptoms always return a fixed escalation message.</span></div>
      </aside>
      <section className="chat-card">
        <header><div><span className="online-dot" /> CareGuard Assistant</div><small>Approved sources only</small></header>
        <div className="chat-body" aria-live="polite">
          <div className="chat-bubble is-system">Bạn có thể hỏi về hướng dẫn đã phát hành, lịch tái khám hoặc triệu chứng trong approved cards.</div>
          {reply?.answer && <div className={`chat-bubble is-reply ${reply.escalation ? "is-escalation" : ""}`}><p>{reply.answer}</p>{reply.citations?.length > 0 && <small>Nguồn: {reply.citations.join(" · ")}</small>}{!reply.citations?.length && <small>Không có nguồn phù hợp — hệ thống đã abstain.</small>}</div>}
        </div>
        <div className="chat-suggestions">
          {["Hướng dẫn của tôi là gì?", "Lịch tái khám của tôi?", "Tôi khó thở và sưng lan nhanh"].map(item => <button type="button" key={item} onClick={() => setMessage(item)}>{item}</button>)}
        </div>
        <form onSubmit={chat}><input value={message} onChange={event => setMessage(event.target.value)} placeholder="Nhập câu hỏi của bệnh nhân…" required /><button disabled={pending}>{pending ? "…" : "Gửi →"}</button></form>
      </section>
    </div>}

    <aside className="post-next"><div><span>Final control</span><strong>Evaluate all obligations before close</strong></div><a href={routeHref("/compliance")}>Mở Compliance →</a></aside>
  </section>;
}

export const route = { path: "/post-treatment", label: "Post-treatment", Component: PostTreatmentChat };
