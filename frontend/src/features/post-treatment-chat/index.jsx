import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../api";
import { useDemoContext } from "../../demo-context";
import "./style.css";

function localDateTime(daysFromNow) {
  const value = new Date(Date.now() + daysFromNow * 86400000);
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
}

const STAGE_LABELS = {
  CHECK_IN: ["Tiếp nhận", "Check-in"],
  PRE_TREATMENT: ["Trước điều trị", "Pre-treatment"],
  TREATMENT: ["Điều trị", "Treatment"],
  POST_TREATMENT: ["Sau điều trị", "Post-treatment"],
  CLOSED: ["Đã đóng", "Closed"],
};

function requestError(data, tr) {
  if (data.code === "ENCOUNTER_NOT_RELEASABLE") return tr(
    "Ca khám phải chuyển đến giai đoạn Sau điều trị trước khi phát hành.",
    "The encounter must reach Post-treatment before release.",
  );
  if (data.code === "ENCOUNTER_CLOSED") return tr(
    "Ca khám đã đóng nên không thể thay đổi gói phát hành.",
    "The encounter is closed, so its release package cannot be changed.",
  );
  if (data.code === "ROLE_FORBIDDEN") return tr(
    "Chỉ Nha sĩ được phép phát hành nội dung cho bệnh nhân.",
    "Only a Dentist can release content to the patient.",
  );
  return data.message || tr("Yêu cầu thất bại", "Request failed");
}

function PostTreatmentChat() {
  const { encounterId, role, routeHref, setRole, tr } = useDemoContext();
  const [message, setMessage] = useState("");
  const [reply, setReply] = useState(null);
  const [care, setCare] = useState(() => tr("Giữ vùng điều trị sạch, tránh thức ăn quá nóng trong 24 giờ đầu.", "Keep the treatment area clean and avoid very hot food for the first 24 hours."));
  const [recall, setRecall] = useState(() => localDateTime(30));
  const [monitor, setMonitor] = useState(() => localDateTime(7));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [encounterStage, setEncounterStage] = useState("");
  const [stageLoading, setStageLoading] = useState(true);
  const [stageError, setStageError] = useState("");
  const isPatient = role === "PATIENT";
  const releaseAllowed = encounterStage === "POST_TREATMENT";
  const earliestDateTime = localDateTime(0);

  const loadEncounterStage = useCallback(async signal => {
    if (role === "PATIENT") {
      setEncounterStage("");
      setStageError("");
      setStageLoading(false);
      return;
    }
    setStageLoading(true);
    setStageError("");
    try {
      const response = await apiFetch(`/api/v1/encounters/${encounterId}`, {
        headers: { "X-Demo-Role": role },
        signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(requestError(data, tr));
      setEncounterStage(data.stage || "");
    } catch (failure) {
      if (failure.name !== "AbortError") {
        setEncounterStage("");
        setStageError(failure.message || tr("Không kiểm tra được giai đoạn ca khám.", "Unable to check the encounter stage."));
      }
    } finally {
      if (!signal?.aborted) setStageLoading(false);
    }
  }, [encounterId, role, tr]);

  useEffect(() => {
    const controller = new AbortController();
    void loadEncounterStage(controller.signal);
    return () => controller.abort();
  }, [loadEncounterStage]);
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
      if (!response.ok) throw new Error(requestError(data, tr));
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
    if (!releaseAllowed) {
      setError(tr("Hãy chuyển ca khám đến giai đoạn Sau điều trị trước khi phát hành.", "Move the encounter to Post-treatment before release."));
      return;
    }
    if (!releaseContract.ready) {
      setError(tr("Hướng dẫn không được để trống; thời gian theo dõi phải ở tương lai và không sau lịch tái khám.", "Care instructions are required; monitoring must be in the future and no later than the recall date."));
      return;
    }
    return request(`/api/v1/encounters/${encounterId}/release`, {
      care_instructions: care.trim(),
      recall_at: new Date(recall).toISOString(),
      monitor_until: new Date(monitor).toISOString(),
    });
  };

  const releaseItems = useMemo(() => [
    [tr("Hướng dẫn chăm sóc", "Care instruction"), releaseContract.careReady ? tr("Sẵn sàng", "Ready") : tr("Thiếu", "Missing"), "POST_CARE_INSTRUCTION"],
    [tr("Lịch tái khám", "Recall date"), releaseContract.recallReady && releaseContract.ordered ? tr("Sẵn sàng", "Ready") : tr("Không hợp lệ", "Invalid"), "POST_RECALL_DATE"],
    [tr("Thời gian theo dõi", "Monitoring window"), releaseContract.monitorReady && releaseContract.ordered ? tr("Sẵn sàng", "Ready") : tr("Không hợp lệ", "Invalid"), "POST_MONITORING_WINDOW"],
  ], [releaseContract, tr]);

  return <section className="post-page" aria-labelledby="post-title">
    <header className="post-hero">
      <div>
        <p className="post-eyebrow">{tr("Module 04 · Chăm sóc liên tục", "Module 04 · Continuity of care")}</p>
        <h1 id="post-title">{tr("Sau điều trị & Chat bệnh nhân", "Post-treatment & Patient Chat")}</h1>
        <p>{tr("Phát hành nội dung đã duyệt cho bệnh nhân, sau đó trả lời từ đúng hồ sơ đã phát hành hoặc thẻ lâm sàng được phê duyệt.", "Release approved content to the patient, then answer only from released records or approved clinical cards.")}</p>
      </div>
      <div className="post-role-switch" aria-label={tr("Chế độ sau điều trị", "Post-treatment view")}>
        <button className={!isPatient ? "is-active" : ""} type="button" onClick={() => setRole("DENTIST")}><span>{tr("Nhân viên", "Staff")}</span><strong>{tr("Phát hành tóm tắt", "Release summary")}</strong></button>
        <button className={isPatient ? "is-active" : ""} type="button" onClick={() => setRole("PATIENT")}><span>{tr("Bệnh nhân", "Patient")}</span><strong>{tr("Chat cổng bệnh nhân", "Portal chat")}</strong></button>
      </div>
    </header>

    {error && <div className="post-notice is-error" role="alert"><strong>{tr("Không thể hoàn tất", "Unable to complete")}</strong><span>{error}</span></div>}
    {!isPatient && !stageLoading && !stageError && !releaseAllowed && <div className="post-notice is-warning" role="status"><strong>{tr("Chưa thể phát hành", "Release is not available yet")}</strong><span>{tr("Giai đoạn hiện tại", "Current stage")}: {tr(...(STAGE_LABELS[encounterStage] || [encounterStage, encounterStage]))}. {encounterStage === "CLOSED" ? tr("Ca đã đóng và chỉ có thể xem dữ liệu đã phát hành.", "The encounter is closed; only previously released data can be viewed.") : tr("Hoàn thành các điều kiện rồi chuyển stage tại màn hình Ca khám.", "Complete the requirements and advance the stage from the Encounter screen.")}</span>{encounterStage !== "CLOSED" && <a href={routeHref("/encounter")}>{tr("Mở Ca khám →", "Open Encounter →")}</a>}</div>}
    {!isPatient && stageError && <div className="post-notice is-warning" role="alert"><strong>{tr("Không kiểm tra được giai đoạn", "Unable to check stage")}</strong><span>{stageError}</span><button type="button" onClick={() => loadEncounterStage()}>{tr("Thử lại", "Retry")}</button></div>}
    {reply?.released && <div className="post-notice is-success" role="status"><strong>{tr("Đã phát hành", "Released")}</strong><span>{tr("Ba mục bằng chứng hiện có thể được cổng bệnh nhân sử dụng.", "Three evidence items are now available to the patient portal.")}</span></div>}

    {!isPatient ? <div className="post-grid">
      <form className="post-card release-card" onSubmit={release}>
        <div className="post-card-heading"><div><span>{tr("Gói phát hành", "Release package")}</span><h2>{tr("Tóm tắt chăm sóc bệnh nhân", "Patient care summary")}</h2></div><small>{tr("Chỉ NHA SĨ", "DENTIST only")}</small></div>
        <label><span>{tr("Hướng dẫn chăm sóc", "Care instructions")}</span><textarea value={care} onChange={event => setCare(event.target.value)} required /></label>
        <div className="post-date-grid">
          <label><span>{tr("Lịch tái khám", "Recall appointment")}</span><input type="datetime-local" value={recall} min={monitor || earliestDateTime} onChange={event => setRecall(event.target.value)} required /></label>
          <label><span>{tr("Theo dõi đến", "Monitor until")}</span><input type="datetime-local" value={monitor} min={earliestDateTime} max={recall || undefined} onChange={event => setMonitor(event.target.value)} required /></label>
        </div>
        <small>{tr("Thời gian theo dõi phải ở tương lai và kết thúc trước hoặc đúng lịch tái khám.", "Monitoring must be in the future and end on or before the recall date.")}</small>
        <div className="release-warning"><span aria-hidden="true">!</span><p><strong>{tr("Ranh giới phát hành", "Release boundary")}</strong>{tr("Chỉ bằng chứng VERIFIED được đánh dấu phát hành. Bản nháp và ghi chú chỉ dành cho nhân viên không xuất hiện ở cổng bệnh nhân.", "Only VERIFIED evidence is marked as released. Drafts and staff-only notes never appear in the patient portal.")}</p></div>
        <button type="submit" disabled={pending || stageLoading || role !== "DENTIST" || !releaseContract.ready || !releaseAllowed}>{stageLoading ? tr("Đang kiểm tra giai đoạn…", "Checking stage…") : pending ? tr("Đang phát hành…", "Releasing…") : tr("Phát hành cho bệnh nhân →", "Release to patient →")}</button>
        {role !== "DENTIST" && <small>{tr("Chọn vai trò NHA SĨ để phát hành.", "Select the DENTIST role to release.")}</small>}
        {role === "DENTIST" && !stageLoading && !releaseAllowed && <small>{tr("Chỉ phát hành được khi ca khám đang ở giai đoạn Sau điều trị.", "Release is available only while the encounter is in Post-treatment.")}</small>}
      </form>

      <aside className="post-card release-readiness">
        <div className="post-card-heading"><div><span>{tr("Kiểm tra trước phát hành", "Pre-flight check")}</span><h2>{tr("Mức sẵn sàng phát hành", "Release readiness")}</h2></div><small>{tr("Ca khám", "Encounter")} #{encounterId.slice(-6)}</small></div>
        <ul>{releaseItems.map(([label, state, code], index) => <li key={code}><i>{index + 1}</i><span><strong>{label}</strong><small>{code}</small></span><b className={state === tr("Sẵn sàng", "Ready") ? "is-ready" : ""}>{state}</b></li>)}</ul>
        <div className="post-stage-note"><span>{tr("Giai đoạn hiện tại", "Current stage")}</span><strong>{stageLoading ? tr("Đang kiểm tra…", "Checking…") : encounterStage ? tr(...(STAGE_LABELS[encounterStage] || [encounterStage, encounterStage])) : tr("Không xác định", "Unknown")}</strong><p>{tr("Yêu cầu: POST_TREATMENT. CLOSED là bất biến; hãy phát hành trước khi đóng ca khám.", "Required: POST_TREATMENT. CLOSED is immutable; release before closing the encounter.")}</p></div>
      </aside>
    </div> : <div className="patient-chat-layout">
      <aside className="patient-portal-card">
        <div className="patient-avatar" aria-hidden="true">PT</div>
        <p>{tr("Cổng bệnh nhân", "Patient portal")}</p><h2>{tr("Trợ lý chăm sóc sau điều trị", "Your after-care assistant")}</h2>
        <dl><div><dt>{tr("Ca khám", "Encounter")}</dt><dd>#{encounterId.slice(-6)}</dd></div><div><dt>{tr("Quy tắc nguồn", "Source rule")}</dt><dd>{tr("Chỉ nội dung đã phát hành", "Released only")}</dd></div><div><dt>{tr("An toàn", "Safety")}</dt><dd>{tr("Trích dẫn hoặc từ chối trả lời", "Citation or abstain")}</dd></div></dl>
        <div className="portal-safety"><strong>{tr("Ranh giới khẩn cấp", "Emergency boundary")}</strong><span>{tr("Triệu chứng cảnh báo luôn trả về thông báo chuyển cấp cố định.", "Red-flag symptoms always return a fixed escalation message.")}</span></div>
      </aside>
      <section className="chat-card">
        <header><div><span className="online-dot" /> CareGuard Assistant</div><small>{tr("Chỉ nguồn được phê duyệt", "Approved sources only")}</small></header>
        <div className="chat-body" aria-live="polite">
          <div className="chat-bubble is-system">{tr("Bạn có thể hỏi về hướng dẫn đã phát hành, lịch tái khám hoặc triệu chứng trong các thẻ đã duyệt.", "Ask about released instructions, recall dates, or symptoms covered by approved cards.")}</div>
          {reply?.answer && <div className={`chat-bubble is-reply ${reply.escalation ? "is-escalation" : ""}`}><p>{reply.answer}</p>{reply.citations?.length > 0 && <small>{tr("Nguồn", "Sources")}: {reply.citations.join(" · ")}</small>}{!reply.citations?.length && <small>{tr("Không có nguồn phù hợp — hệ thống đã từ chối trả lời.", "No suitable source — the system abstained.")}</small>}</div>}
        </div>
        <div className="chat-suggestions">
          {(tr(["Hướng dẫn của tôi là gì?", "Lịch tái khám của tôi?", "Tôi khó thở và sưng lan nhanh"], ["What are my care instructions?", "When is my recall appointment?", "I have trouble breathing and rapidly spreading swelling"])).map(item => <button type="button" key={item} onClick={() => setMessage(item)}>{item}</button>)}
        </div>
        <form onSubmit={chat}><input value={message} onChange={event => setMessage(event.target.value)} placeholder={tr("Nhập câu hỏi của bệnh nhân…", "Enter the patient's question…")} required /><button disabled={pending}>{pending ? "…" : tr("Gửi →", "Send →")}</button></form>
      </section>
    </div>}

    <aside className="post-next"><div><span>{tr("Kiểm soát cuối", "Final control")}</span><strong>{tr("Đánh giá mọi nghĩa vụ trước khi đóng ca", "Evaluate all obligations before close")}</strong></div><a href={routeHref("/compliance")}>{tr("Mở Tuân thủ →", "Open Compliance →")}</a></aside>
  </section>;
}

export const route = { path: "/post-treatment", label: "Post-treatment", Component: PostTreatmentChat };
