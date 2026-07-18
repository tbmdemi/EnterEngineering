import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../api";
import { useDemoContext } from "../../demo-context";
import "./style.css";

const ROLES = [
  { value: "FRONT_DESK", label: ["Lễ tân", "Front Desk"] },
  { value: "ASSISTANT", label: ["Trợ lý", "Assistant"] },
  { value: "DENTIST", label: ["Nha sĩ", "Dentist"] },
];

const TASK_LABELS = {
  HANDOFF: ["Bàn giao bệnh nhân", "Patient handoff"],
  REFERRAL: ["Phụ trách chuyển tuyến", "Referral ownership"],
  REVIEW_SCHEDULE_CONFLICT: ["Kiểm tra xung đột lịch", "Schedule conflict review"],
};

const SCHEDULE_RESOLUTION_REASONS = [
  ["DUPLICATE_BOOKING", ["Lịch đặt trùng", "Duplicate booking"]],
  ["PATIENT_REQUESTED_CANCELLATION", ["Bệnh nhân yêu cầu hủy", "Patient requested cancellation"]],
  ["REBOOKED_TO_ANOTHER_SLOT", ["Đã đặt lại khung giờ khác", "Rebooked to another slot"]],
  ["CREATED_IN_ERROR", ["Tạo nhầm", "Created in error"]],
];

const formatDateTime = (value, locale) => value
  ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
  : null;

async function parseResponse(response, fallbackMessage) {
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || fallbackMessage);
  return body;
}

function Coordination() {
  const { encounterId, locale, role, setRole, tr } = useDemoContext();
  const [tasks, setTasks] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState("");
  const [scheduleResult, setScheduleResult] = useState(null);
  const [resolutionReasons, setResolutionReasons] = useState({});

  const load = useCallback(async signal => {
    if (!ROLES.some(item => item.value === role)) {
      setTasks([]);
      setLoading(false);
      setMessage(tr("Chọn LỄ TÂN, TRỢ LÝ hoặc NHA SĨ để mở danh sách việc.", "Select FRONT_DESK, ASSISTANT, or DENTIST to open a worklist."));
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`/api/v1/tasks?owner_role=${role}`, {
        headers: { "X-Demo-Role": role },
        signal,
      });
      setTasks(await parseResponse(response, tr("Không tải được danh sách việc", "Unable to load worklist")));
      setTasks(current => current.filter(task => task.encounter_id === encounterId));
    } catch (error) {
      if (error.name !== "AbortError") setMessage(error.message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [encounterId, role, tr]);

  useEffect(() => {
    const controller = new AbortController();
    setScheduleResult(null);
    setResolutionReasons({});
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const updateTask = async (task, action) => {
    const actionKey = `${task.id}:${action}`;
    setPendingAction(actionKey);
    setMessage("");
    try {
      const response = await apiFetch(`/api/v1/tasks/${task.id}/${action}`, {
        method: "POST",
        headers: { "X-Demo-Role": role },
      });
      await parseResponse(response, tr("Không cập nhật được tác vụ", "Unable to update task"));
      await load();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setPendingAction("");
    }
  };

  const evaluateSchedule = async task => {
    const actionKey = `${task.id}:evaluate`;
    setPendingAction(actionKey);
    setMessage("");
    try {
      const response = await apiFetch(`/api/v1/encounters/${task.encounter_id}/coordination/evaluate`, {
        method: "POST",
        headers: { "X-Demo-Role": role },
      });
      setScheduleResult(await parseResponse(response, tr("Không kiểm tra được lịch", "Unable to check schedule")));
    } catch (error) {
      setMessage(error.message);
    } finally {
      setPendingAction("");
    }
  };

  const resolveSchedule = async conflict => {
    const appointmentId = conflict.conflicts_with;
    const reason = resolutionReasons[appointmentId];
    if (!reason) {
      setMessage(tr("Chọn lý do nghiệp vụ trước khi xử lý xung đột.", "Select an operational reason before resolving the conflict."));
      return;
    }
    setPendingAction(`resolve:${appointmentId}`);
    setMessage("");
    try {
      const response = await apiFetch(`/api/v1/encounters/${encounterId}/coordination/resolve-schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({
          appointment_id: appointmentId,
          expected_status: conflict.appointment_status,
          reason,
        }),
      });
      setScheduleResult(await parseResponse(response, tr("Không xử lý được xung đột lịch", "Unable to resolve schedule conflict")));
      await load();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setPendingAction("");
    }
  };

  const activeRole = ROLES.find(item => item.value === role) || { label: [role, role] };
  const brief = useMemo(() => {
    const acknowledged = tasks.filter(task => task.status === "ACKNOWLEDGED").length;
    return tr(`${tasks.length} việc đang mở${acknowledged ? `, ${acknowledged} đã xác nhận` : ""}`, `${tasks.length} open tasks${acknowledged ? `, ${acknowledged} acknowledged` : ""}`);
  }, [tasks, tr]);

  return <section className="coordination" aria-labelledby="coordination-title">
    <header className="coordination__header">
      <div>
        <p className="coordination__eyebrow">{tr("Vận hành đội ngũ chăm sóc", "Care team operations")}</p>
        <h1 id="coordination-title">{tr("Danh sách điều phối", "Coordination worklist")}</h1>
      </div>
      <div className="coordination__brief" aria-live="polite">
        <span>{tr(...activeRole.label)}</span>
        <strong>{loading ? tr("Đang tải", "Loading") : brief}</strong>
      </div>
    </header>

    <div className="coordination__roles" role="tablist" aria-label={tr("Vai trò danh sách việc", "Worklist role")}>
      {ROLES.map(item => <button
        key={item.value}
        type="button"
        role="tab"
        aria-selected={role === item.value}
        className={role === item.value ? "is-active" : ""}
        onClick={() => setRole(item.value)}
      >{tr(...item.label)}</button>)}
    </div>

    {message && <p className="coordination__alert" role="alert">{message}</p>}

    <div className="coordination__list" aria-busy={loading}>
      {loading && <div className="coordination__empty">{tr("Đang tải danh sách việc...", "Loading worklist...")}</div>}
      {!loading && !tasks.length && !message && <div className="coordination__empty">{tr("Không có việc đang chờ.", "No pending work.")}</div>}
      {!loading && tasks.map(task => {
        const appointmentTime = formatDateTime(task.appointment_starts_at, locale);
        const canAcknowledge = task.task_type === "HANDOFF" && task.status === "OPEN";
        const canComplete = (task.task_type !== "HANDOFF" && task.status === "OPEN")
          || (task.task_type === "HANDOFF" && task.status === "ACKNOWLEDGED");
        const canEvaluate = task.task_type === "REVIEW_SCHEDULE_CONFLICT";

        return <article className="coordination-task" key={task.id}>
          <div className="coordination-task__topline">
            <div>
              <span className={`coordination-task__status status-${task.status.toLowerCase()}`}>{task.status}</span>
              <h2>{tr(...(TASK_LABELS[task.task_type] || [task.task_type, task.task_type]))}</h2>
            </div>
            {task.due_at && <time dateTime={task.due_at}>{tr("Hạn", "Due")} {formatDateTime(task.due_at, locale)}</time>}
          </div>

          <dl className="coordination-task__meta">
            <div><dt>{tr("Bằng chứng", "Evidence")}</dt><dd><code>{task.obligation_code}</code></dd></div>
            {task.chair && <div><dt>{tr("Ghế", "Chair")}</dt><dd>{task.chair}</dd></div>}
            {appointmentTime && <div><dt>{tr("Lịch hẹn", "Appointment")}</dt><dd>{appointmentTime}</dd></div>}
          </dl>

          <div className="coordination-task__actions">
            {canEvaluate && <button
              type="button"
              className="button-secondary"
              disabled={Boolean(pendingAction)}
              onClick={() => evaluateSchedule(task)}
            >{pendingAction === `${task.id}:evaluate` ? tr("Đang kiểm tra...", "Checking...") : tr("Kiểm tra xung đột", "Check conflict")}</button>}
            {canAcknowledge && <button
              type="button"
              disabled={Boolean(pendingAction)}
              onClick={() => updateTask(task, "acknowledge")}
            >{pendingAction === `${task.id}:acknowledge` ? tr("Đang xác nhận...", "Acknowledging...") : tr("Xác nhận", "Acknowledge")}</button>}
            {canComplete && <button
              type="button"
              disabled={Boolean(pendingAction)}
              onClick={() => updateTask(task, "complete")}
            >{pendingAction === `${task.id}:complete` ? tr("Đang cập nhật...", "Updating...") : task.task_type === "REVIEW_SCHEDULE_CONFLICT" ? tr("Đánh dấu đã kiểm tra", "Mark reviewed") : tr("Hoàn tất", "Complete")}</button>}
          </div>
        </article>;
      })}
    </div>

    {scheduleResult && <section className={`coordination__schedule ${scheduleResult.schedule_clear ? "is-clear" : "has-conflict"}`} aria-live="polite">
      <div>
        <p className="coordination__eyebrow">{tr("Bằng chứng lịch", "Schedule evidence")}</p>
        <h2>{scheduleResult.schedule_clear ? tr("Lịch không xung đột", "Schedule clear") : tr(`Phát hiện ${scheduleResult.conflicts.length} xung đột`, `${scheduleResult.conflicts.length} conflict detected`)}</h2>
      </div>
      {!scheduleResult.schedule_clear && <ul>{scheduleResult.conflicts.map(conflict => <li key={conflict.conflicts_with}>
        <strong>{conflict.chair}</strong>
        <span>{formatDateTime(conflict.starts_at, locale)} – {formatDateTime(conflict.ends_at, locale)}</span>
        {role === "FRONT_DESK" && <div className="coordination__resolution">
          <label>
            <span className="sr-only">{tr("Lý do xử lý", "Resolution reason")}</span>
            <select
              value={resolutionReasons[conflict.conflicts_with] || ""}
              onChange={event => setResolutionReasons(current => ({
                ...current,
                [conflict.conflicts_with]: event.target.value,
              }))}
              disabled={Boolean(pendingAction)}
              aria-label={tr("Lý do xử lý", "Resolution reason")}
            >
              <option value="">{tr("Chọn lý do", "Select reason")}</option>
              {SCHEDULE_RESOLUTION_REASONS.map(([value, label]) => <option key={value} value={value}>{tr(...label)}</option>)}
            </select>
          </label>
          <button
            type="button"
            disabled={Boolean(pendingAction) || !resolutionReasons[conflict.conflicts_with]}
            onClick={() => resolveSchedule(conflict)}
          >
            {pendingAction === `resolve:${conflict.conflicts_with}` ? tr("Đang xử lý...", "Resolving...") : tr("Xử lý xung đột", "Resolve conflict")}
          </button>
        </div>}
      </li>)}</ul>}
    </section>}
  </section>;
}

export const route = { path: "/coordination", label: "Coordination", Component: Coordination };
