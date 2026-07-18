import React, { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../../api";
import { DEMO_ROLES as ROLES, SEED_ENCOUNTER_ID, useDemoContext } from "../../demo-context";
import "./style.css";

const ROLE_LABELS = {
  FRONT_DESK: ["Lễ tân", "Front desk"], ASSISTANT: ["Trợ lý", "Assistant"],
  DENTIST: ["Nha sĩ", "Dentist"], PATIENT: ["Bệnh nhân", "Patient"], QA: ["QA / Tuân thủ", "QA / Compliance"],
};
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const STAGES = ["CHECK_IN", "PRE_TREATMENT", "TREATMENT", "POST_TREATMENT", "CLOSED"];
const STAGE_LABELS = {
  CHECK_IN: ["Tiếp nhận", "Check-in"], PRE_TREATMENT: ["Trước điều trị", "Pre-treatment"],
  TREATMENT: ["Điều trị", "Treatment"], POST_TREATMENT: ["Sau điều trị", "Post-treatment"], CLOSED: ["Đã đóng", "Closed"],
};
const STAGE_DESCRIPTIONS = {
  CHECK_IN: ["Xác nhận thông tin và sẵn sàng tiếp nhận", "Confirm information and prepare for intake"],
  PRE_TREATMENT: ["Hoàn tất kiểm tra an toàn trước điều trị", "Complete the pre-treatment safety checks"],
  TREATMENT: ["Thực hiện và ghi nhận điều trị", "Perform and document treatment"],
  POST_TREATMENT: ["Hướng dẫn chăm sóc và theo dõi", "Release after-care and follow-up"],
  CLOSED: ["Ca khám đã hoàn tất", "Encounter completed"],
};

class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

async function requestJson(url, options = {}) {
  const response = await apiFetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body.code ?? "REQUEST_FAILED", body.message ?? "Yêu cầu không thành công");
  }
  return body;
}

function formatAppointmentTime(value, locale) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function formatUpdateTime(value, locale, tr) {
  if (!value) return tr("Chưa đồng bộ", "Not synchronized");
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(value);
}

function getInitials(name) {
  return name.trim().split(/\s+/).slice(-2).map((part) => part[0]).join("").toUpperCase();
}

function Encounter() {
  // URLSearchParams and careguard.demoRole persistence live in the shared demo context.
  const { encounterId, language, locale, role, routeHref, setRole, tr } = useDemoContext();
  const roleLabel = value => tr(...(ROLE_LABELS[value] || [value, value]));
  const stageLabel = value => tr(...(STAGE_LABELS[value] || [value, value]));
  const stageDescription = value => tr(...(STAGE_DESCRIPTIONS[value] || [value, value]));
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [isLoading, setIsLoading] = useState(Boolean(role));
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [isCloseConfirmOpen, setIsCloseConfirmOpen] = useState(false);
  const isValidEncounterId = UUID_PATTERN.test(encounterId);

  const load = useCallback(async (signal, background = false) => {
    if (!role || !isValidEncounterId) return;
    background ? setIsRefreshing(true) : setIsLoading(true);
    setError("");
    try {
      const headers = { "X-Demo-Role": role };
      const [encounter, transitions] = await Promise.all([
        requestJson(`/api/v1/encounters/${encounterId}`, { headers, signal }),
        requestJson(`/api/v1/encounters/${encounterId}/transitions`, { headers, signal }),
      ]);
      setData(encounter);
      setHistory(transitions);
      setLastUpdated(new Date());
    } catch (reason) {
      if (reason.name !== "AbortError") setError(reason.message || tr("Không tải được ca khám", "Unable to load encounter"));
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [encounterId, isValidEncounterId, role, tr]);

  useEffect(() => {
    if (!role || !isValidEncounterId) return undefined;
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [isValidEncounterId, load, role]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible" && data && role) load(undefined, true);
    };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => document.removeEventListener("visibilitychange", refreshWhenVisible);
  }, [data, load, role]);

  const chooseRole = (event) => {
    const selectedRole = event.target.value;
    setRole(selectedRole);
    setData(null);
    setHistory([]);
    setError("");
    setIsLoading(Boolean(selectedRole));
  };

  const performAdvance = async () => {
    if (!data?.next_stage || !data.can_advance || isAdvancing) return;
    setIsCloseConfirmOpen(false);
    setIsAdvancing(true);
    setError("");
    try {
      await requestJson(`/api/v1/encounters/${encounterId}/stage`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": role },
        body: JSON.stringify({ stage: data.next_stage, version: data.version }),
      });
      await load(undefined, true);
    } catch (reason) {
      if (reason.code === "STALE_ENCOUNTER_VERSION") {
        await load(undefined, true);
        setError(tr("Ca khám vừa được cập nhật ở nơi khác. Dữ liệu mới nhất đã được tải lại.", "The encounter was updated elsewhere. The latest data has been reloaded."));
      } else {
        setError(reason.message || tr("Không thể chuyển bước ca khám", "Unable to advance encounter"));
      }
    } finally {
      setIsAdvancing(false);
    }
  };

  const requestAdvance = () => {
    if (data?.next_stage === "CLOSED") setIsCloseConfirmOpen(true);
    else performAdvance();
  };

  if (!isValidEncounterId) return <section className="encounter-shell encounter-empty" role="alert">
    <div className="encounter-empty-icon" aria-hidden="true">!</div>
    <p className="encounter-eyebrow">{tr("Mã ca khám không hợp lệ", "Invalid Encounter ID")}</p>
    <h2>{tr("Không thể mở ca khám", "Unable to open encounter")}</h2>
    <p>{tr("Kiểm tra tham số", "Check the")} <code>?id=&lt;uuid&gt;</code> {tr("trên URL.", "URL parameter.")}</p>
    <a className="encounter-button encounter-button-primary" href={`/encounter?id=${encodeURIComponent(SEED_ENCOUNTER_ID)}&role=${encodeURIComponent(role)}&lang=${language}`}>{tr("Mở ca demo", "Open demo encounter")}</a>
  </section>;

  if (!role) return <section className="encounter-shell encounter-role-gate" aria-labelledby="role-title">
    <div className="encounter-role-icon" aria-hidden="true">CG</div>
    <p className="encounter-eyebrow">{tr("Ngữ cảnh vai trò CareGuard", "CareGuard role context")}</p>
    <h2 id="role-title">{tr("Chọn vai trò để mở ca khám", "Choose a role to open the encounter")}</h2>
    <p>{tr("Backend kiểm tra quyền đọc và chuyển bước qua", "The backend checks read and transition permissions through")} <code>X-Demo-Role</code>.</p>
    <label htmlFor="encounter-role-gate">{tr("Vai trò demo", "Demo role")}</label>
    <select id="encounter-role-gate" value={role} onChange={chooseRole}>
      <option value="">{tr("Chọn vai trò…", "Choose role…")}</option>
      {ROLES.map((item) => <option key={item} value={item}>{roleLabel(item)}</option>)}
    </select>
  </section>;

  if (!data && isLoading) return <section className="encounter-shell encounter-loading" role="status">
    <span className="encounter-spinner" aria-hidden="true" />
    <div><strong>{tr("Đang tải ca khám", "Loading encounter")}</strong><p>{tr("Đang đồng bộ thông tin bệnh nhân và lịch sử…", "Synchronizing patient details and history…")}</p></div>
  </section>;

  if (!data) return <section className="encounter-shell encounter-empty" aria-labelledby="encounter-error-title">
    <div className="encounter-empty-icon" aria-hidden="true">!</div>
    <p className="encounter-eyebrow">CareGuard Encounter</p>
    <h2 id="encounter-error-title">{tr("Không thể mở ca khám", "Unable to open encounter")}</h2>
    <p role="alert">{error}</p>
    <button className="encounter-button encounter-button-primary" type="button" onClick={() => load()}>{tr("Thử tải lại", "Try again")}</button>
  </section>;

  const currentIndex = STAGES.indexOf(data.stage);
  const progress = Math.round(((currentIndex + 1) / STAGES.length) * 100);

  return <section className="encounter-shell" aria-labelledby="encounter-title">
    <div className="encounter-toolbar">
      <label htmlFor="encounter-role">{tr("Vai trò", "Role")}
        <select id="encounter-role" value={role} onChange={chooseRole} disabled={isAdvancing}>
          {ROLES.map((item) => <option key={item} value={item}>{roleLabel(item)}</option>)}
        </select>
      </label>
      <span>{tr("Cập nhật", "Updated")}: {formatUpdateTime(lastUpdated, locale, tr)}</span>
      <button type="button" onClick={() => load(undefined, true)} disabled={isRefreshing || isAdvancing}>
        {isRefreshing ? tr("Đang làm mới…", "Refreshing…") : tr("Làm mới", "Refresh")}
      </button>
    </div>

    <header className="encounter-hero">
      <div className="encounter-hero-topline">
        <div><p className="encounter-eyebrow">CareGuard · {tr("Ca khám nha khoa", "Dental encounter")}</p><p className="encounter-id">{tr("Ca khám", "Encounter")} #{data.id.slice(-6).toUpperCase()}</p></div>
        <span className="encounter-live-badge"><i aria-hidden="true" /> {data.stage === "CLOSED" ? tr("Đã hoàn tất", "Completed") : tr("Đang hoạt động", "Active")}</span>
      </div>
      <div className="encounter-patient">
        <div className="encounter-avatar" aria-hidden="true">{getInitials(data.patient.full_name)}</div>
        <div className="encounter-patient-copy"><h2 id="encounter-title">{data.patient.full_name}</h2><p>MRN <strong>{data.patient.mrn}</strong></p></div>
        <div className="encounter-stage-chip"><span>{tr("Giai đoạn hiện tại", "Current stage")}</span><strong>{stageLabel(data.stage)}</strong></div>
      </div>
      <dl className="encounter-facts">
        <div><dt>{tr("Lịch hẹn", "Appointment")}</dt><dd>{formatAppointmentTime(data.appointment?.starts_at, locale)}</dd></div>
        <div><dt>{tr("Ghế điều trị", "Chair")}</dt><dd>{data.appointment?.chair ?? "—"}</dd></div>
        <div><dt>{tr("Trạng thái lịch", "Appointment status")}</dt><dd><span className="encounter-status-dot" aria-hidden="true" />{data.appointment?.status ?? tr("Không có lịch hẹn", "No appointment")}</dd></div>
        <div><dt>{tr("Phiên bản ca", "Encounter version")}</dt><dd>v{data.version}</dd></div>
      </dl>
    </header>

    <div className="encounter-content">
      <div className="encounter-section-heading">
        <div><p className="encounter-eyebrow">{tr("Quy trình điều trị", "Treatment workflow")}</p><h3>{tr("Tiến trình ca khám", "Encounter progress")}</h3></div>
        <div className="encounter-progress-copy" aria-label={tr(`Đã hoàn thành ${progress}%`, `${progress}% completed`)}><strong>{currentIndex + 1}/{STAGES.length}</strong><span>{tr("bước", "steps")}</span></div>
      </div>
      <div className="encounter-progress-track" aria-hidden="true"><span style={{ width: `${progress}%` }} /></div>
      <ol className="encounter-stepper" aria-label={tr("Các bước của ca khám", "Encounter stages")}>
        {STAGES.map((stage, index) => {
          const state = index < currentIndex ? "completed" : index === currentIndex ? "current" : "upcoming";
          return <li key={stage} aria-current={state === "current" ? "step" : undefined} data-state={state}>
            <span className="encounter-step-marker" aria-hidden="true">{state === "completed" ? "✓" : index + 1}</span>
            <span className="encounter-step-copy"><strong>{stageLabel(stage)}</strong><small>{stageDescription(stage)}</small></span>
          </li>;
        })}
      </ol>

      {error && <div className="encounter-alert" role="alert"><span aria-hidden="true">!</span><p>{error}</p></div>}

      <footer className="encounter-action-card">
        <div>
          <span className="encounter-action-kicker">{data.next_stage ? tr("Bước tiếp theo", "Next stage") : tr("Trạng thái", "Status")}</span>
          <strong>{data.next_stage ? stageLabel(data.next_stage) : tr("Đã hoàn tất", "Completed")}</strong>
          <p>{data.next_stage ? stageDescription(data.next_stage) : tr("Tất cả các bước trong ca khám đã hoàn thành.", "All encounter stages are complete.")}</p>
        </div>
        {data.can_advance
          ? <button className="encounter-button encounter-button-primary" type="button" onClick={requestAdvance} disabled={isAdvancing || isRefreshing}>
            {isAdvancing ? <><span className="encounter-button-spinner" aria-hidden="true" />{tr("Đang chuyển bước…", "Advancing…")}</> : <>{tr("Tiếp tục", "Continue")} <span aria-hidden="true">→</span></>}
          </button>
          : data.next_stage
            ? <span className="encounter-readonly-badge">{data.readiness && !data.readiness.ready ? tr("Chưa đủ điều kiện chuyển bước", "Requirements are not ready") : tr("Chỉ nha sĩ được chuyển bước này", "Only a dentist can advance this stage")}</span>
            : <span className="encounter-complete-badge" role="status"><span aria-hidden="true">✓</span> {tr("Ca khám đã hoàn tất", "Encounter completed")}</span>}
      </footer>

      {data.readiness && !data.readiness.ready && <section className="encounter-alert" role="alert">
        <span aria-hidden="true">!</span>
        <div>
          <strong>{tr("Chưa thể chuyển sang", "Cannot advance to")} {stageLabel(data.readiness.target_stage)}</strong>
          <p>{data.readiness.blockers.length} {tr("điều kiện bắt buộc cần được xử lý.", "required items need attention.")}</p>
          <p>{data.readiness.blockers.map(item => `${item.code} (${item.state})`).join(", ")}</p>
          <a href={routeHref("/compliance")}>{tr("Mở kiểm tra tuân thủ", "Open compliance readiness")}</a>
        </div>
      </section>}

      <section className="encounter-history" aria-labelledby="history-title">
        <div><p className="encounter-eyebrow">{tr("Dòng thời gian audit an toàn", "Audit-safe timeline")}</p><h3 id="history-title">{tr("Lịch sử chuyển bước", "Stage history")}</h3></div>
        {history.length
          ? <ol>{history.map((item) => <li key={item.id}>
            <span className="encounter-history-dot" aria-hidden="true" />
            <div><strong>{stageLabel(item.from_stage)} → {stageLabel(item.to_stage)}</strong><small>{roleLabel(item.actor_role)} · {formatAppointmentTime(item.occurred_at, locale)} · v{item.to_version}</small></div>
          </li>)}</ol>
          : <p className="encounter-history-empty">{tr("Chưa có lần chuyển bước nào.", "No stage transitions yet.")}</p>}
      </section>
    </div>

    {isCloseConfirmOpen && <div className="encounter-modal-backdrop" role="presentation">
      <section className="encounter-modal" role="dialog" aria-modal="true" aria-labelledby="close-title" aria-describedby="close-description">
        <div className="encounter-modal-icon" aria-hidden="true">✓</div>
        <p className="encounter-eyebrow">{tr("Xác nhận thao tác cuối", "Confirm final action")}</p>
        <h3 id="close-title">{tr("Đóng ca khám?", "Close encounter?")}</h3>
        <p id="close-description">{tr("Sau khi đóng, ca khám không thể quay lại giai đoạn trước trong demo này. Cổng tuân thủ vẫn do module Integration kiểm soát.", "After closing, this demo cannot return to an earlier stage. The Integration module still controls the compliance gate.")}</p>
        <div className="encounter-modal-actions">
          <button className="encounter-button encounter-button-secondary" type="button" onClick={() => setIsCloseConfirmOpen(false)}>{tr("Hủy", "Cancel")}</button>
          <button className="encounter-button encounter-button-primary" type="button" onClick={performAdvance}>{tr("Xác nhận đóng ca", "Confirm close")}</button>
        </div>
      </section>
    </div>}
  </section>;
}

export const route = { path: "/encounter", label: "Encounter", Component: Encounter };
