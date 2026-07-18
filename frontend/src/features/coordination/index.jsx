import React, { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../api";
import { useDemoContext } from "../../demo-context";
import "./style.css";

const ROLES = [
  { value: "FRONT_DESK", label: "Front Desk" },
  { value: "ASSISTANT", label: "Assistant" },
  { value: "DENTIST", label: "Dentist" },
];

const TASK_LABELS = {
  HANDOFF: "Patient handoff",
  REFERRAL: "Referral ownership",
  REVIEW_SCHEDULE_CONFLICT: "Schedule conflict review",
};

const SCHEDULE_RESOLUTION_REASONS = [
  ["DUPLICATE_BOOKING", "Duplicate booking"],
  ["PATIENT_REQUESTED_CANCELLATION", "Patient requested cancellation"],
  ["REBOOKED_TO_ANOTHER_SLOT", "Rebooked to another slot"],
  ["CREATED_IN_ERROR", "Created in error"],
];

const formatDateTime = value => value
  ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
  : null;

async function parseResponse(response, fallbackMessage) {
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || fallbackMessage);
  return body;
}

function Coordination() {
  const { encounterId, role, setRole } = useDemoContext();
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
      setMessage("Chọn FRONT_DESK, ASSISTANT hoặc DENTIST để mở worklist.");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const response = await apiFetch(`/api/v1/tasks?owner_role=${role}`, {
        headers: { "X-Demo-Role": role },
        signal,
      });
      setTasks(await parseResponse(response, "Không tải được worklist"));
      setTasks(current => current.filter(task => task.encounter_id === encounterId));
    } catch (error) {
      if (error.name !== "AbortError") setMessage(error.message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [encounterId, role]);

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
      await parseResponse(response, "Không cập nhật được task");
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
      setScheduleResult(await parseResponse(response, "Không kiểm tra được lịch"));
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
      setMessage("Select an operational reason before resolving the conflict.");
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
      setScheduleResult(await parseResponse(response, "Không xử lý được xung đột lịch"));
      await load();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setPendingAction("");
    }
  };

  const activeRole = ROLES.find(item => item.value === role) || { label: role };
  const brief = useMemo(() => {
    const acknowledged = tasks.filter(task => task.status === "ACKNOWLEDGED").length;
    return `${tasks.length} việc đang mở${acknowledged ? `, ${acknowledged} đã xác nhận` : ""}`;
  }, [tasks]);

  return <section className="coordination" aria-labelledby="coordination-title">
    <header className="coordination__header">
      <div>
        <p className="coordination__eyebrow">Care team operations</p>
        <h1 id="coordination-title">Coordination worklist</h1>
      </div>
      <div className="coordination__brief" aria-live="polite">
        <span>{activeRole.label}</span>
        <strong>{loading ? "Đang tải" : brief}</strong>
      </div>
    </header>

    <div className="coordination__roles" role="tablist" aria-label="Worklist role">
      {ROLES.map(item => <button
        key={item.value}
        type="button"
        role="tab"
        aria-selected={role === item.value}
        className={role === item.value ? "is-active" : ""}
        onClick={() => setRole(item.value)}
      >{item.label}</button>)}
    </div>

    {message && <p className="coordination__alert" role="alert">{message}</p>}

    <div className="coordination__list" aria-busy={loading}>
      {loading && <div className="coordination__empty">Đang tải worklist...</div>}
      {!loading && !tasks.length && !message && <div className="coordination__empty">Không có việc đang chờ.</div>}
      {!loading && tasks.map(task => {
        const appointmentTime = formatDateTime(task.appointment_starts_at);
        const canAcknowledge = task.task_type === "HANDOFF" && task.status === "OPEN";
        const canComplete = (task.task_type !== "HANDOFF" && task.status === "OPEN")
          || (task.task_type === "HANDOFF" && task.status === "ACKNOWLEDGED");
        const canEvaluate = task.task_type === "REVIEW_SCHEDULE_CONFLICT";

        return <article className="coordination-task" key={task.id}>
          <div className="coordination-task__topline">
            <div>
              <span className={`coordination-task__status status-${task.status.toLowerCase()}`}>{task.status}</span>
              <h2>{TASK_LABELS[task.task_type] || task.task_type}</h2>
            </div>
            {task.due_at && <time dateTime={task.due_at}>Due {formatDateTime(task.due_at)}</time>}
          </div>

          <dl className="coordination-task__meta">
            <div><dt>Evidence</dt><dd><code>{task.obligation_code}</code></dd></div>
            {task.chair && <div><dt>Chair</dt><dd>{task.chair}</dd></div>}
            {appointmentTime && <div><dt>Appointment</dt><dd>{appointmentTime}</dd></div>}
          </dl>

          <div className="coordination-task__actions">
            {canEvaluate && <button
              type="button"
              className="button-secondary"
              disabled={Boolean(pendingAction)}
              onClick={() => evaluateSchedule(task)}
            >{pendingAction === `${task.id}:evaluate` ? "Đang kiểm tra..." : "Check conflict"}</button>}
            {canAcknowledge && <button
              type="button"
              disabled={Boolean(pendingAction)}
              onClick={() => updateTask(task, "acknowledge")}
            >{pendingAction === `${task.id}:acknowledge` ? "Đang xác nhận..." : "Acknowledge"}</button>}
            {canComplete && <button
              type="button"
              disabled={Boolean(pendingAction)}
              onClick={() => updateTask(task, "complete")}
            >{pendingAction === `${task.id}:complete` ? "Đang cập nhật..." : task.task_type === "REVIEW_SCHEDULE_CONFLICT" ? "Mark reviewed" : "Complete"}</button>}
          </div>
        </article>;
      })}
    </div>

    {scheduleResult && <section className={`coordination__schedule ${scheduleResult.schedule_clear ? "is-clear" : "has-conflict"}`} aria-live="polite">
      <div>
        <p className="coordination__eyebrow">Schedule evidence</p>
        <h2>{scheduleResult.schedule_clear ? "Schedule clear" : `${scheduleResult.conflicts.length} conflict detected`}</h2>
      </div>
      {!scheduleResult.schedule_clear && <ul>{scheduleResult.conflicts.map(conflict => <li key={conflict.conflicts_with}>
        <strong>{conflict.chair}</strong>
        <span>{formatDateTime(conflict.starts_at)} – {formatDateTime(conflict.ends_at)}</span>
        {role === "FRONT_DESK" && <div className="coordination__resolution">
          <label>
            <span className="sr-only">Resolution reason</span>
            <select
              value={resolutionReasons[conflict.conflicts_with] || ""}
              onChange={event => setResolutionReasons(current => ({
                ...current,
                [conflict.conflicts_with]: event.target.value,
              }))}
              disabled={Boolean(pendingAction)}
              aria-label="Resolution reason"
            >
              <option value="">Select reason</option>
              {SCHEDULE_RESOLUTION_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <button
            type="button"
            disabled={Boolean(pendingAction) || !resolutionReasons[conflict.conflicts_with]}
            onClick={() => resolveSchedule(conflict)}
          >
            {pendingAction === `resolve:${conflict.conflicts_with}` ? "Đang xử lý..." : "Resolve conflict"}
          </button>
        </div>}
      </li>)}</ul>}
    </section>}
  </section>;
}

export const route = { path: "/coordination", label: "Coordination", Component: Coordination };
