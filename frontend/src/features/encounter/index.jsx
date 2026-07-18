import React, { useCallback, useEffect, useMemo, useState } from "react";
import "./style.css";

const SEED_ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";
const ROLES = ["FRONT_DESK", "ASSISTANT", "DENTIST", "PATIENT", "QA"];
const ROLE_LABELS = {
  FRONT_DESK: "Lễ tân",
  ASSISTANT: "Trợ thủ",
  DENTIST: "Nha sĩ",
  PATIENT: "Bệnh nhân",
  QA: "QA / Compliance",
};
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const STAGES = ["CHECK_IN", "PRE_TREATMENT", "TREATMENT", "POST_TREATMENT", "CLOSED"];
const STAGE_LABELS = {
  CHECK_IN: "Tiếp nhận",
  PRE_TREATMENT: "Trước điều trị",
  TREATMENT: "Điều trị",
  POST_TREATMENT: "Sau điều trị",
  CLOSED: "Đã đóng",
};
const STAGE_DESCRIPTIONS = {
  CHECK_IN: "Xác nhận thông tin và sẵn sàng tiếp nhận",
  PRE_TREATMENT: "Hoàn tất kiểm tra an toàn trước điều trị",
  TREATMENT: "Thực hiện và ghi nhận điều trị",
  POST_TREATMENT: "Hướng dẫn chăm sóc và theo dõi",
  CLOSED: "Ca khám đã hoàn tất",
};

class ApiError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body.code ?? "REQUEST_FAILED", body.message ?? "Yêu cầu không thành công");
  }
  return body;
}

function getInitialContext() {
  const params = new URLSearchParams(window.location.search);
  const storedRole = window.sessionStorage.getItem("careguard.demoRole");
  const requestedRole = params.get("role") ?? storedRole;
  return {
    encounterId: params.get("id") ?? SEED_ENCOUNTER_ID,
    role: ROLES.includes(requestedRole) ? requestedRole : "",
  };
}

function updateContextUrl(encounterId, role) {
  const url = new URL(window.location.href);
  url.searchParams.set("id", encounterId);
  if (role) url.searchParams.set("role", role);
  else url.searchParams.delete("role");
  window.history.replaceState({}, "", url);
}

function formatAppointmentTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function formatUpdateTime(value) {
  if (!value) return "Chưa đồng bộ";
  return new Intl.DateTimeFormat("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(value);
}

function getInitials(name) {
  return name.trim().split(/\s+/).slice(-2).map((part) => part[0]).join("").toUpperCase();
}

function Encounter() {
  const initialContext = useMemo(getInitialContext, []);
  const [encounterId] = useState(initialContext.encounterId);
  const [role, setRole] = useState(initialContext.role);
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [isLoading, setIsLoading] = useState(Boolean(initialContext.role));
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
      if (reason.name !== "AbortError") setError(reason.message || "Không tải được ca khám");
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, [encounterId, isValidEncounterId, role]);

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
    if (selectedRole) window.sessionStorage.setItem("careguard.demoRole", selectedRole);
    else window.sessionStorage.removeItem("careguard.demoRole");
    updateContextUrl(encounterId, selectedRole);
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
        setError("Ca khám vừa được cập nhật ở nơi khác. Dữ liệu mới nhất đã được tải lại.");
      } else {
        setError(reason.message || "Không thể chuyển bước ca khám");
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
    <p className="encounter-eyebrow">Encounter ID không hợp lệ</p>
    <h2>Không thể mở ca khám</h2>
    <p>Kiểm tra tham số <code>?id=&lt;uuid&gt;</code> trên URL.</p>
    <a className="encounter-button encounter-button-primary" href={`/encounter?id=${SEED_ENCOUNTER_ID}`}>Mở ca demo</a>
  </section>;

  if (!role) return <section className="encounter-shell encounter-role-gate" aria-labelledby="role-title">
    <div className="encounter-role-icon" aria-hidden="true">CG</div>
    <p className="encounter-eyebrow">CareGuard role context</p>
    <h2 id="role-title">Chọn vai trò để mở ca khám</h2>
    <p>Quyền đọc và chuyển bước được backend kiểm tra qua <code>X-Demo-Role</code>.</p>
    <label htmlFor="encounter-role-gate">Vai trò demo</label>
    <select id="encounter-role-gate" value={role} onChange={chooseRole}>
      <option value="">Chọn vai trò…</option>
      {ROLES.map((item) => <option key={item} value={item}>{ROLE_LABELS[item]}</option>)}
    </select>
  </section>;

  if (!data && isLoading) return <section className="encounter-shell encounter-loading" role="status">
    <span className="encounter-spinner" aria-hidden="true" />
    <div><strong>Đang tải ca khám</strong><p>Đang đồng bộ thông tin bệnh nhân và lịch sử…</p></div>
  </section>;

  if (!data) return <section className="encounter-shell encounter-empty" aria-labelledby="encounter-error-title">
    <div className="encounter-empty-icon" aria-hidden="true">!</div>
    <p className="encounter-eyebrow">CareGuard Encounter</p>
    <h2 id="encounter-error-title">Không thể mở ca khám</h2>
    <p role="alert">{error}</p>
    <button className="encounter-button encounter-button-primary" type="button" onClick={() => load()}>Thử tải lại</button>
  </section>;

  const currentIndex = STAGES.indexOf(data.stage);
  const progress = Math.round(((currentIndex + 1) / STAGES.length) * 100);

  return <section className="encounter-shell" aria-labelledby="encounter-title">
    <div className="encounter-toolbar">
      <label htmlFor="encounter-role">Vai trò
        <select id="encounter-role" value={role} onChange={chooseRole} disabled={isAdvancing}>
          {ROLES.map((item) => <option key={item} value={item}>{ROLE_LABELS[item]}</option>)}
        </select>
      </label>
      <span>Cập nhật: {formatUpdateTime(lastUpdated)}</span>
      <button type="button" onClick={() => load(undefined, true)} disabled={isRefreshing || isAdvancing}>
        {isRefreshing ? "Đang làm mới…" : "Làm mới"}
      </button>
    </div>

    <header className="encounter-hero">
      <div className="encounter-hero-topline">
        <div><p className="encounter-eyebrow">CareGuard · Dental encounter</p><p className="encounter-id">Ca khám #{data.id.slice(-6).toUpperCase()}</p></div>
        <span className="encounter-live-badge"><i aria-hidden="true" /> {data.stage === "CLOSED" ? "Đã hoàn tất" : "Đang hoạt động"}</span>
      </div>
      <div className="encounter-patient">
        <div className="encounter-avatar" aria-hidden="true">{getInitials(data.patient.full_name)}</div>
        <div className="encounter-patient-copy"><h2 id="encounter-title">{data.patient.full_name}</h2><p>MRN <strong>{data.patient.mrn}</strong></p></div>
        <div className="encounter-stage-chip"><span>Giai đoạn hiện tại</span><strong>{STAGE_LABELS[data.stage]}</strong></div>
      </div>
      <dl className="encounter-facts">
        <div><dt>Lịch hẹn</dt><dd>{formatAppointmentTime(data.appointment?.starts_at)}</dd></div>
        <div><dt>Ghế điều trị</dt><dd>{data.appointment?.chair ?? "—"}</dd></div>
        <div><dt>Trạng thái lịch</dt><dd><span className="encounter-status-dot" aria-hidden="true" />{data.appointment?.status ?? "Không có lịch hẹn"}</dd></div>
        <div><dt>Phiên bản ca</dt><dd>v{data.version}</dd></div>
      </dl>
    </header>

    <div className="encounter-content">
      <div className="encounter-section-heading">
        <div><p className="encounter-eyebrow">Quy trình điều trị</p><h3>Tiến trình ca khám</h3></div>
        <div className="encounter-progress-copy" aria-label={`Đã hoàn thành ${progress}%`}><strong>{currentIndex + 1}/{STAGES.length}</strong><span>bước</span></div>
      </div>
      <div className="encounter-progress-track" aria-hidden="true"><span style={{ width: `${progress}%` }} /></div>
      <ol className="encounter-stepper" aria-label="Các bước của ca khám">
        {STAGES.map((stage, index) => {
          const state = index < currentIndex ? "completed" : index === currentIndex ? "current" : "upcoming";
          return <li key={stage} aria-current={state === "current" ? "step" : undefined} data-state={state}>
            <span className="encounter-step-marker" aria-hidden="true">{state === "completed" ? "✓" : index + 1}</span>
            <span className="encounter-step-copy"><strong>{STAGE_LABELS[stage]}</strong><small>{STAGE_DESCRIPTIONS[stage]}</small></span>
          </li>;
        })}
      </ol>

      {error && <div className="encounter-alert" role="alert"><span aria-hidden="true">!</span><p>{error}</p></div>}

      <footer className="encounter-action-card">
        <div>
          <span className="encounter-action-kicker">{data.next_stage ? "Bước tiếp theo" : "Trạng thái"}</span>
          <strong>{data.next_stage ? STAGE_LABELS[data.next_stage] : "Đã hoàn tất"}</strong>
          <p>{data.next_stage ? STAGE_DESCRIPTIONS[data.next_stage] : "Tất cả các bước trong ca khám đã hoàn thành."}</p>
        </div>
        {data.can_advance
          ? <button className="encounter-button encounter-button-primary" type="button" onClick={requestAdvance} disabled={isAdvancing || isRefreshing}>
            {isAdvancing ? <><span className="encounter-button-spinner" aria-hidden="true" />Đang chuyển bước…</> : <>Tiếp tục <span aria-hidden="true">→</span></>}
          </button>
          : data.next_stage
            ? <span className="encounter-readonly-badge">Vai trò này chỉ được xem</span>
            : <span className="encounter-complete-badge" role="status"><span aria-hidden="true">✓</span> Ca khám đã hoàn tất</span>}
      </footer>

      <section className="encounter-history" aria-labelledby="history-title">
        <div><p className="encounter-eyebrow">Audit-safe timeline</p><h3 id="history-title">Lịch sử chuyển bước</h3></div>
        {history.length
          ? <ol>{history.map((item) => <li key={item.id}>
            <span className="encounter-history-dot" aria-hidden="true" />
            <div><strong>{STAGE_LABELS[item.from_stage]} → {STAGE_LABELS[item.to_stage]}</strong><small>{ROLE_LABELS[item.actor_role]} · {formatAppointmentTime(item.occurred_at)} · v{item.to_version}</small></div>
          </li>)}</ol>
          : <p className="encounter-history-empty">Chưa có lần chuyển bước nào.</p>}
      </section>
    </div>

    {isCloseConfirmOpen && <div className="encounter-modal-backdrop" role="presentation">
      <section className="encounter-modal" role="dialog" aria-modal="true" aria-labelledby="close-title" aria-describedby="close-description">
        <div className="encounter-modal-icon" aria-hidden="true">✓</div>
        <p className="encounter-eyebrow">Xác nhận thao tác cuối</p>
        <h3 id="close-title">Đóng ca khám?</h3>
        <p id="close-description">Sau khi đóng, Encounter không thể quay lại stage trước trong demo này. Compliance gate vẫn do module Integration kiểm soát.</p>
        <div className="encounter-modal-actions">
          <button className="encounter-button encounter-button-secondary" type="button" onClick={() => setIsCloseConfirmOpen(false)}>Hủy</button>
          <button className="encounter-button encounter-button-primary" type="button" onClick={performAdvance}>Xác nhận đóng ca</button>
        </div>
      </section>
    </div>}
  </section>;
}

export const route = { path: "/encounter", label: "Encounter", Component: Encounter };
