import React, { useCallback, useEffect, useMemo, useState } from "react";
import "./style.css";

const ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";
const DEMO_ROLE = "DENTIST";

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

function formatAppointmentTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function getInitials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function Encounter() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isAdvancing, setIsAdvancing] = useState(false);

  const load = useCallback(async (signal) => {
    setIsLoading(true);
    setError("");
    try {
      const encounter = await requestJson(`/api/v1/encounters/${ENCOUNTER_ID}`, {
        headers: { "X-Demo-Role": DEMO_ROLE },
        signal,
      });
      setData(encounter);
    } catch (reason) {
      if (reason.name !== "AbortError") {
        setError(reason.message || "Không tải được ca khám");
      }
    } finally {
      if (!signal?.aborted) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const nextStage = useMemo(() => {
    if (!data) return null;
    const currentIndex = STAGES.indexOf(data.stage);
    return currentIndex >= 0 ? (STAGES[currentIndex + 1] ?? null) : null;
  }, [data]);

  const advance = async () => {
    if (!data || !nextStage || isAdvancing) return;

    setIsAdvancing(true);
    setError("");
    try {
      const updated = await requestJson(`/api/v1/encounters/${ENCOUNTER_ID}/stage`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Demo-Role": DEMO_ROLE },
        body: JSON.stringify({ stage: nextStage, version: data.version }),
      });
      setData(updated);
    } catch (reason) {
      if (reason.code === "STALE_ENCOUNTER_VERSION") {
        await load();
        setError("Ca khám vừa được cập nhật ở nơi khác. Dữ liệu mới nhất đã được tải lại.");
      } else {
        setError(reason.message || "Không thể chuyển bước ca khám");
      }
    } finally {
      setIsAdvancing(false);
    }
  };

  if (!data && isLoading) return <section className="encounter-shell encounter-loading" role="status">
    <span className="encounter-spinner" aria-hidden="true" />
    <div>
      <strong>Đang tải ca khám</strong>
      <p>Đang đồng bộ thông tin bệnh nhân và lịch hẹn…</p>
    </div>
  </section>;
  if (!data) return <section className="encounter-shell encounter-empty" aria-labelledby="encounter-error-title">
    <div className="encounter-empty-icon" aria-hidden="true">!</div>
    <p className="encounter-eyebrow">CareGuard Encounter</p>
    <h2 id="encounter-error-title">Không thể mở ca khám</h2>
    <p role="alert">{error}</p>
    <button className="encounter-button encounter-button-primary" type="button" onClick={() => load()}>
      Thử tải lại
    </button>
  </section>;

  const currentIndex = STAGES.indexOf(data.stage);

  const progress = Math.round(((currentIndex + 1) / STAGES.length) * 100);

  return <section className="encounter-shell" aria-labelledby="encounter-title">
    <header className="encounter-hero">
      <div className="encounter-hero-topline">
        <div>
          <p className="encounter-eyebrow">CareGuard · Dental encounter</p>
          <p className="encounter-id">Ca khám #{data.id.slice(-6).toUpperCase()}</p>
        </div>
        <span className="encounter-live-badge"><i aria-hidden="true" /> Đang hoạt động</span>
      </div>

      <div className="encounter-patient">
        <div className="encounter-avatar" aria-hidden="true">{getInitials(data.patient.full_name)}</div>
        <div className="encounter-patient-copy">
          <h2 id="encounter-title">{data.patient.full_name}</h2>
          <p>MRN <strong>{data.patient.mrn}</strong></p>
        </div>
        <div className="encounter-stage-chip">
          <span>Giai đoạn hiện tại</span>
          <strong>{STAGE_LABELS[data.stage]}</strong>
        </div>
      </div>

      <dl className="encounter-facts">
        <div>
          <dt>Lịch hẹn</dt>
          <dd>{formatAppointmentTime(data.appointment?.starts_at)}</dd>
        </div>
        <div>
          <dt>Ghế điều trị</dt>
          <dd>{data.appointment?.chair ?? "—"}</dd>
        </div>
        <div>
          <dt>Trạng thái lịch</dt>
          <dd><span className="encounter-status-dot" aria-hidden="true" />{data.appointment?.status ?? "Không có lịch hẹn"}</dd>
        </div>
        <div>
          <dt>Phiên bản ca</dt>
          <dd>v{data.version}</dd>
        </div>
      </dl>
    </header>

    <div className="encounter-content">
      <div className="encounter-section-heading">
        <div>
          <p className="encounter-eyebrow">Quy trình điều trị</p>
          <h3>Tiến trình ca khám</h3>
        </div>
        <div className="encounter-progress-copy" aria-label={`Đã hoàn thành ${progress}%`}>
          <strong>{currentIndex + 1}/{STAGES.length}</strong>
          <span>bước</span>
        </div>
      </div>

      <div className="encounter-progress-track" aria-hidden="true">
        <span style={{ width: `${progress}%` }} />
      </div>

      <ol className="encounter-stepper" aria-label="Các bước của ca khám">
      {STAGES.map((stage, index) => {
        const state = index < currentIndex ? "completed" : index === currentIndex ? "current" : "upcoming";
        return <li key={stage} aria-current={state === "current" ? "step" : undefined} data-state={state}>
          <span className="encounter-step-marker" aria-hidden="true">
            {state === "completed" ? "✓" : index + 1}
          </span>
          <span className="encounter-step-copy">
            <strong>{STAGE_LABELS[stage]}</strong>
            <small>{STAGE_DESCRIPTIONS[stage]}</small>
          </span>
        </li>;
      })}
      </ol>

      {error && <div className="encounter-alert" role="alert">
        <span aria-hidden="true">!</span>
        <p>{error}</p>
      </div>}

      <footer className="encounter-action-card">
        <div>
          <span className="encounter-action-kicker">{nextStage ? "Bước tiếp theo" : "Trạng thái"}</span>
          <strong>{nextStage ? STAGE_LABELS[nextStage] : "Đã hoàn tất"}</strong>
          <p>{nextStage ? STAGE_DESCRIPTIONS[nextStage] : "Tất cả các bước trong ca khám đã hoàn thành."}</p>
        </div>
        {nextStage
          ? <button className="encounter-button encounter-button-primary" type="button" onClick={advance} disabled={isAdvancing}>
            {isAdvancing ? <><span className="encounter-button-spinner" aria-hidden="true" />Đang chuyển bước…</> : <>Tiếp tục <span aria-hidden="true">→</span></>}
          </button>
          : <span className="encounter-complete-badge" role="status"><span aria-hidden="true">✓</span> Ca khám đã hoàn tất</span>}
      </footer>
    </div>
  </section>;
}

export const route = { path: "/encounter", label: "Encounter", Component: Encounter };
