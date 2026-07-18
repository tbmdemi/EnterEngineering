import React, { useEffect, useMemo, useRef, useState } from "react";

import "./index.css";

const DEMO_ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";

const QUICK_PROMPTS = [
  "Hồ sơ của tôi",
  "Giờ mở cửa phòng khám?",
  "Đau nhẹ sau nhổ răng có bình thường không?",
  "Tôi bị sưng tăng nhanh và khó nuốt",
];

const PROCEDURES = [
  { code: "EXTRACTION", label: "Nhổ răng" },
  { code: "ROOT_CANAL", label: "Điều trị tủy" },
  { code: "IMPLANT", label: "Cấy ghép implant" },
  { code: "FILLING", label: "Trám răng" },
  { code: "CLEANING", label: "Vệ sinh răng" },
];

const CALLBACK_REASONS = [
  { code: "PAIN_OR_DISCOMFORT", label: "Đau hoặc khó chịu" },
  { code: "SWELLING_OR_BLEEDING", label: "Sưng hoặc chảy máu" },
  { code: "INSTRUCTIONS_QUESTION", label: "Cần giải thích hướng dẫn" },
  { code: "APPOINTMENT_QUESTION", label: "Câu hỏi về lịch hẹn" },
  { code: "OTHER_NON_CLINICAL", label: "Lý do không lâm sàng khác" },
];

const SESSION_RED_FLAG_GUIDANCE = {
  escalation: true,
  answer:
    "Nếu bạn khó thở, khó nuốt, sưng lan nhanh, chảy máu không kiểm soát hoặc bị chấn thương nặng, đừng chờ chat hay cuộc gọi lại. Hãy tìm trợ giúp khẩn cấp ngay.",
  citations: [
    "NHS urgent dental guidance — https://www.england.nhs.uk/long-read/clinical-guidance-unscheduled-urgent-and-non-urgent-dental-care/",
  ],
};

const API_ERROR_MESSAGES = {
  DEMO_ROLE_REQUIRED: "Không xác định được vai trò dùng thử. Hãy tải lại trang.",
  DEMO_ROLE_INVALID: "Vai trò dùng thử không hợp lệ. Hãy tải lại trang.",
  ROLE_FORBIDDEN: "Vai trò hiện tại không được phép thực hiện thao tác này.",
  ENCOUNTER_NOT_FOUND: "Không tìm thấy lượt điều trị dùng thử.",
  ENCOUNTER_NOT_RELEASABLE:
    "Lượt điều trị phải ở giai đoạn sau điều trị trước khi phát hành.",
  RELEASE_ALREADY_EXISTS:
    "Lượt điều trị này đã có nội dung phát hành. Bản demo hiện không cung cấp thao tác cập nhật hoặc sửa đổi.",
  RELEASE_STATE_INVALID:
    "Dữ liệu đã phát hành đang thiếu công việc theo dõi. Vui lòng liên hệ quản trị viên.",
  VALIDATION_ERROR: "Dữ liệu gửi lên không hợp lệ. Hãy kiểm tra lại các trường.",
  INTERNAL_ERROR: "Máy chủ gặp lỗi ngoài dự kiến. Vui lòng thử lại sau.",
};

class RequestError extends Error {
  constructor(code, message, status = null) {
    super(message);
    this.name = "RequestError";
    this.code = code;
    this.status = status;
  }
}

function citationDetails(citation) {
  const value = String(citation);

  if (value.startsWith("RELEASED_RECORD#")) {
    return {
      id: value,
      label: "Hồ sơ sau điều trị đã phát hành",
      url: null,
    };
  }

  const urlMatch = value.match(/https?:\/\/\S+/);
  const url = urlMatch?.[0] ?? null;
  const withoutUrl = url
    ? value.replace(url, "").replace(/\s*[—-]\s*$/, "").trim()
    : value;
  const separator = withoutUrl.indexOf(":");

  return {
    id: separator >= 0 ? withoutUrl.slice(0, separator).trim() : withoutUrl,
    label:
      separator >= 0 ? withoutUrl.slice(separator + 1).trim() : withoutUrl,
    url,
  };
}

function Citations({ citations }) {
  if (!citations?.length) return null;

  return (
    <section className="citations" aria-label="Nguồn của câu trả lời">
      <h4>Nguồn</h4>
      <ul>
        {citations.map((citation, index) => {
          const details = citationDetails(citation);
          return (
            <li key={`${citation}-${index}`}>
              {details.url ? (
                <a href={details.url} target="_blank" rel="noreferrer">
                  {details.label || "Mở nguồn tham khảo"}
                  <span className="visually-hidden"> (mở trong thẻ mới)</span>
                </a>
              ) : (
                <span>{details.label}</span>
              )}
              {details.id && <small className="citation-id">Mã: {details.id}</small>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function formatDateTime(value) {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function offsetLabel(date) {
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const absoluteMinutes = Math.abs(offsetMinutes);
  const hours = String(Math.floor(absoluteMinutes / 60)).padStart(2, "0");
  const minutes = String(absoluteMinutes % 60).padStart(2, "0");
  return `UTC${sign}${hours}:${minutes}`;
}

function localTimeZoneLabel(date = new Date()) {
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return `${zone || "Múi giờ thiết bị"} (${offsetLabel(date)})`;
}

function parseLocalDateTime(value) {
  const match = value.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/,
  );
  if (!match) return null;

  const [, yearText, monthText, dayText, hourText, minuteText, secondText] =
    match;
  const parts = [
    yearText,
    monthText,
    dayText,
    hourText,
    minuteText,
    secondText ?? "0",
  ].map(Number);
  const [year, month, day, hour, minute, second] = parts;
  const date = new Date(year, month - 1, day, hour, minute, second, 0);

  if (
    Number.isNaN(date.getTime()) ||
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day ||
    date.getHours() !== hour ||
    date.getMinutes() !== minute ||
    date.getSeconds() !== second
  ) {
    return null;
  }

  const apiValue = `${yearText}-${monthText}-${dayText}T${hourText}:${minuteText}:${String(
    second,
  ).padStart(2, "0")}${offsetLabel(date).replace("UTC", "")}`;

  return { apiValue, date };
}

function releaseDetails(data) {
  const summary =
    data.release_summary ?? data.released_summary ?? data.summary ?? {};
  const evidence = Object.fromEntries(
    (data.evidence ?? []).map((item) => [item.code, item.value ?? {}]),
  );

  return {
    careInstructions:
      summary.care_instructions ??
      data.care_instructions ??
      evidence.POST_CARE_INSTRUCTIONS?.text,
    recallAt:
      summary.recall_at ?? data.recall_at ?? evidence.POST_RECALL?.recall_at,
    monitorUntil:
      summary.monitor_until ??
      data.monitor_until ??
      evidence.POST_COMPLICATION_MONITORING?.monitor_until,
    task: data.follow_up_task ?? data.task ?? null,
    citations: summary.citations ?? data.citations,
  };
}

function ReleasedValues({
  careInstructions,
  recallAt,
  monitorUntil,
  showTimeZone = false,
}) {
  return (
    <dl className="released-values">
      {careInstructions && (
        <>
          <dt>Hướng dẫn chăm sóc</dt>
          <dd className="preserve-lines">{careInstructions}</dd>
        </>
      )}
      {recallAt && (
        <>
          <dt>Tái khám</dt>
          <dd>
            <time dateTime={recallAt}>{formatDateTime(recallAt)}</time>
            {showTimeZone && (
              <small className="date-zone">
                {localTimeZoneLabel(new Date(recallAt))}
              </small>
            )}
          </dd>
        </>
      )}
      {monitorUntil && (
        <>
          <dt>Theo dõi biến chứng đến</dt>
          <dd>
            <time dateTime={monitorUntil}>{formatDateTime(monitorUntil)}</time>
            {showTimeZone && (
              <small className="date-zone">
                {localTimeZoneLabel(new Date(monitorUntil))}
              </small>
            )}
          </dd>
        </>
      )}
    </dl>
  );
}

function ReleaseReply({ data }) {
  const { careInstructions, recallAt, monitorUntil, task, citations } =
    releaseDetails(data);
  const hasSummary = careInstructions || recallAt || monitorUntil;
  const taskOwner = task?.owner ?? task?.owner_role;
  const hasTask = task && (taskOwner || task.status || task.due_at);

  return (
    <article className="reply-card release-result" aria-live="polite">
      <p>{data.answer || "Đã phát hành hướng dẫn sau điều trị."}</p>

      {hasSummary && (
        <section aria-labelledby="released-summary-title">
          <h3 id="released-summary-title">Nội dung đã phát hành</h3>
          <ReleasedValues
            careInstructions={careInstructions}
            recallAt={recallAt}
            monitorUntil={monitorUntil}
          />
        </section>
      )}

      {hasTask && (
        <section aria-labelledby="follow-up-task-title">
          <h3 id="follow-up-task-title">Công việc theo dõi</h3>
          <dl>
            {taskOwner && (
              <>
                <dt>Phụ trách</dt>
                <dd>{taskOwner}</dd>
              </>
            )}
            {task.status && (
              <>
                <dt>Trạng thái</dt>
                <dd>{task.status}</dd>
              </>
            )}
            {task.due_at && (
              <>
                <dt>Hạn xử lý</dt>
                <dd>
                  <time dateTime={task.due_at}>{formatDateTime(task.due_at)}</time>
                </dd>
              </>
            )}
          </dl>
        </section>
      )}

      <Citations citations={citations} />
    </article>
  );
}

function PatientRecord({ record }) {
  if (!record) return null;

  return (
    <section className="patient-record" aria-labelledby="patient-record-title">
      <h3 id="patient-record-title">Hồ sơ sau điều trị đã phát hành</h3>
      <ReleasedValues
        careInstructions={record.care_instructions}
        recallAt={record.recall_at}
        monitorUntil={record.monitor_until}
      />
    </section>
  );
}

function ChatReply({ data }) {
  return (
    <article className="reply-card" aria-live="polite">
      {data.record ? (
        <PatientRecord record={data.record} />
      ) : (
        <p>{data.answer}</p>
      )}
      <Citations citations={data.citations} />
    </article>
  );
}

function EscalationReply({ data, onAcknowledge }) {
  return (
    <aside
      className="urgent-reply"
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <h3>Cần trợ giúp khẩn cấp</h3>
      <p>{data.answer}</p>
      <Citations citations={data.citations} />
      <button type="button" className="button-danger" onClick={onAcknowledge}>
        Tôi đã hiểu hướng dẫn khẩn cấp
      </button>
    </aside>
  );
}

function errorMessage(failure) {
  if (failure instanceof RequestError) return failure.message;
  if (failure instanceof TypeError) {
    return "Không thể kết nối với máy chủ. Kiểm tra dịch vụ rồi thử lại.";
  }
  return "Không thể hoàn tất yêu cầu. Vui lòng thử lại.";
}

async function responseData(response) {
  const body = await response.text();
  let data = null;

  if (body) {
    try {
      data = JSON.parse(body);
    } catch {
      throw new RequestError(
        "INVALID_RESPONSE",
        "Máy chủ trả về dữ liệu không đọc được. Vui lòng thử lại sau.",
      );
    }
  }

  if (!response.ok) {
    const code = data?.code;
    const fallback =
      response.status >= 500
        ? "Máy chủ gặp lỗi ngoài dự kiến. Vui lòng thử lại sau."
        : "Yêu cầu không được chấp nhận. Vui lòng kiểm tra và thử lại.";
    throw new RequestError(
      code,
      API_ERROR_MESSAGES[code] ?? data?.message ?? fallback,
      response.status,
    );
  }

  if (!data || typeof data !== "object") {
    throw new RequestError(
      "EMPTY_RESPONSE",
      "Máy chủ không trả về kết quả hợp lệ. Vui lòng thử lại.",
    );
  }

  return data;
}

async function apiRequest(url, { method = "GET", body, role } = {}) {
  const headers = {};
  if (role) headers["X-Demo-Role"] = role;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(url, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return responseData(response);
}

function unavailableFeatureMessage(failure, featureLabel) {
  if (
    failure instanceof RequestError &&
    ([405, 501].includes(failure.status) ||
      (failure.status === 404 && !failure.code))
  ) {
    return `${featureLabel} đang chờ API của nhánh tích hợp. Các chức năng hiện có vẫn sử dụng được.`;
  }
  return errorMessage(failure);
}

function createRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();

  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex
    .slice(6, 8)
    .join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

function normalizeTemplates(data) {
  const items = Array.isArray(data)
    ? data
    : data.templates ?? data.items ?? data.results ?? [];

  return items
    .map((item) => ({
      ref: item.template_ref ?? item.ref ?? item.template_id ?? item.id,
      title: item.title ?? item.name ?? item.label ?? "Hướng dẫn đã duyệt",
      procedureCode: item.procedure_code ?? item.procedure ?? "",
      locale: item.locale ?? "vi",
      version:
        item.version ??
        item.template_version ??
        item.version_no ??
        item.content_version ??
        1,
      contentVersion:
        item.content_version ?? item.version ?? item.template_version ?? null,
      status: item.approval_status ?? item.status ?? "APPROVED",
      active: item.active ?? true,
      instructions:
        item.care_instructions ?? item.content ?? item.instructions ?? item.text ?? "",
      approvedBy: item.approved_by ?? item.reviewer ?? null,
      source: item.source ?? null,
      sourceUrl: item.source_url ?? null,
    }))
    .filter(
      (item) =>
        item.ref &&
        item.instructions &&
        item.active &&
        item.status.toUpperCase() === "APPROVED",
    );
}

function createSessionCheckIns(startedAt = Date.now()) {
  return [24, 72, 168].map((offsetHours) => ({
    ref: `session-${offsetHours}h`,
    offsetHours,
    dueAt: new Date(startedAt + offsetHours * 60 * 60 * 1000).toISOString(),
    status: "PENDING",
  }));
}

function ReleaseStepper({ currentStep }) {
  const steps = [
    { number: 1, label: "Soạn thảo" },
    { number: 2, label: "Xem lại" },
    { number: 3, label: "Đã phát hành" },
  ];

  return (
    <ol className="release-stepper" aria-label="Tiến trình phát hành">
      {steps.map((step) => {
        const state =
          step.number < currentStep
            ? "complete"
            : step.number === currentStep
              ? "current"
              : "upcoming";
        return (
          <li
            key={step.number}
            className={`step-${state}`}
            aria-current={state === "current" ? "step" : undefined}
          >
            <span aria-hidden="true">
              {state === "complete" ? "✓" : step.number}
            </span>
            <strong>{step.label}</strong>
          </li>
        );
      })}
    </ol>
  );
}

function TemplateSelector({
  locale,
  onLocaleChange,
  procedure,
  onProcedureChange,
  templates,
  selectedTemplate,
  onTemplateChange,
  onApply,
  loading,
  notice,
}) {
  return (
    <section className="template-selector" aria-labelledby="template-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Nội dung được kiểm duyệt</p>
          <h3 id="template-title">Chọn mẫu chăm sóc theo điều trị</h3>
        </div>
        <span className="approved-badge">Chỉ mẫu APPROVED</span>
      </div>

      <div className="selector-grid">
        <label htmlFor="template-locale">
          Ngôn ngữ
          <select
            id="template-locale"
            value={locale}
            onChange={onLocaleChange}
            disabled={loading}
          >
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
          </select>
        </label>

        <label htmlFor="procedure-code">
          Loại điều trị
          <select
            id="procedure-code"
            value={procedure}
            onChange={onProcedureChange}
            disabled={loading}
          >
            {PROCEDURES.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label htmlFor="approved-template">
          Mẫu đã duyệt
          <select
            id="approved-template"
            value={selectedTemplate?.ref ?? ""}
            onChange={onTemplateChange}
            disabled={loading || !templates.length}
          >
            <option value="">
              {loading ? "Đang tải mẫu…" : "Chọn một mẫu"}
            </option>
            {templates.map((item) => (
              <option key={`${item.ref}-${item.version}`} value={item.ref}>
                {item.title} · v{item.version}
              </option>
            ))}
          </select>
        </label>
      </div>

      {notice && <p className="feature-notice">{notice}</p>}
      {selectedTemplate && (
        <div className="template-provenance">
          <p>
            <strong>{selectedTemplate.title}</strong> · phiên bản {selectedTemplate.version} ·{" "}
            {selectedTemplate.locale.toUpperCase()}
            {selectedTemplate.approvedBy
              ? ` · duyệt bởi ${selectedTemplate.approvedBy}`
              : ""}
          </p>
          {selectedTemplate.source && (
            <p>
              <strong>Nguồn:</strong>{" "}
              {selectedTemplate.sourceUrl ? (
                <a
                  href={selectedTemplate.sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {selectedTemplate.source}
                </a>
              ) : (
                selectedTemplate.source
              )}
            </p>
          )}
          <p>
            Mẫu chỉ hỗ trợ soạn thảo trên màn hình. Chỉ nội dung hướng dẫn cuối cùng được gửi trong yêu cầu phát hành; lựa chọn mẫu và trạng thái tùy chỉnh không được lưu riêng.
          </p>
          <button type="button" className="button-secondary" onClick={onApply}>
            Áp dụng mẫu này
          </button>
        </div>
      )}
    </section>
  );
}

function JourneyTimeline({ releaseData, acknowledged, checkIns }) {
  const details = releaseData ? releaseDetails(releaseData) : {};
  const nextCheckIn = checkIns.find((item) => item.status !== "COMPLETED");
  const completedCheckIns = checkIns.filter((item) => item.status === "COMPLETED");
  const steps = [
    {
      key: "treatment",
      title: "Điều trị hoàn tất",
      detail: "Lượt điều trị đang ở giai đoạn sau điều trị",
      status: "complete",
    },
    {
      key: "release",
      title: "Hướng dẫn được phát hành",
      detail: releaseData
        ? "Đã phát hành trong phiên dùng thử hiện tại"
        : "Chưa phát hành trong phiên này",
      status: releaseData ? "complete" : "upcoming",
    },
    {
      key: "acknowledgement",
      title: "Bệnh nhân xác nhận đã đọc",
      detail: acknowledged
        ? "Đã đánh dấu trong phiên này (không lưu)"
        : "Đang chờ thao tác trong phiên",
      status: acknowledged ? "complete" : releaseData ? "current" : "upcoming",
    },
    {
      key: "monitoring",
      title: "Theo dõi hồi phục",
      detail: !releaseData
        ? "Mốc minh họa bắt đầu sau khi phát hành trong phiên"
        : nextCheckIn?.dueAt
        ? `Check-in kế tiếp: ${formatDateTime(nextCheckIn.dueAt)}`
        : completedCheckIns.length
          ? `Đã hoàn tất ${completedCheckIns.length} check-in`
          : details.monitorUntil
            ? `Theo dõi đến ${formatDateTime(details.monitorUntil)}`
            : "Chưa có lịch check-in",
      status:
        releaseData && nextCheckIn
          ? "current"
          : completedCheckIns.length
            ? "complete"
            : "upcoming",
    },
    {
      key: "recall",
      title: "Tái khám",
      detail: details.recallAt
        ? formatDateTime(details.recallAt)
        : "Chưa có lịch tái khám",
      status: details.recallAt ? "upcoming" : "upcoming",
    },
  ];

  return (
    <section className="journey-panel" aria-labelledby="journey-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Release thật · journey minh họa trong phiên</p>
          <h3 id="journey-title">Các bước tiếp theo của bạn</h3>
        </div>
      </div>
      <p className="session-only-note">
        Hướng dẫn đã phát hành đến từ API hiện có. Chỉ trạng thái xác nhận và check-in trên timeline là minh họa: chúng không được gửi đến máy chủ và sẽ mất khi tải lại trang.
      </p>
      <ol className="journey-timeline">
        {steps.map((step) => (
          <li key={step.key} className={`timeline-${step.status}`}>
            <span className="timeline-marker" aria-hidden="true" />
            <div>
              <strong>{step.title}</strong>
              <span>{step.detail}</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function PrintableSafetyNotice() {
  return (
    <section className="print-safety" aria-labelledby="print-safety-title">
      <h4 id="print-safety-title">Dấu hiệu cần trợ giúp khẩn cấp</h4>
      <p>
        Khó thở, khó nuốt, sưng lan nhanh, chảy máu không kiểm soát hoặc chấn thương nặng: không chờ chat hay cuộc gọi lại; hãy tìm trợ giúp khẩn cấp ngay.
      </p>
      <p>
        Với câu hỏi không khẩn cấp, hãy dùng kênh liên hệ chính thức mà phòng khám đã cung cấp.
      </p>
    </section>
  );
}

function PostTreatmentChat() {
  const [role, setRole] = useState("DENTIST");
  const [message, setMessage] = useState("");
  const [transcript, setTranscript] = useState([]);
  const [pinnedEscalation, setPinnedEscalation] = useState(null);

  const [care, setCare] = useState("");
  const [recall, setRecall] = useState("");
  const [monitor, setMonitor] = useState("");
  const [releaseReview, setReleaseReview] = useState(null);
  const [releasedData, setReleasedData] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  const [locale, setLocale] = useState("vi");
  const [procedure, setProcedure] = useState("EXTRACTION");
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [appliedTemplate, setAppliedTemplate] = useState(null);
  const [templateCustomized, setTemplateCustomized] = useState(false);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateNotice, setTemplateNotice] = useState("");

  const [checkIns, setCheckIns] = useState(() => createSessionCheckIns());
  const [acknowledged, setAcknowledged] = useState(false);
  const [callbackOpen, setCallbackOpen] = useState(false);
  const [callbackSubmitted, setCallbackSubmitted] = useState(false);
  const [callbackReason, setCallbackReason] = useState("PAIN_OR_DISCOMFORT");
  const [callbackStart, setCallbackStart] = useState("");
  const [callbackEnd, setCallbackEnd] = useState("");
  const [checkInForm, setCheckInForm] = useState({
    trend: "SAME",
    painScore: 0,
    swelling: "NONE",
    bleeding: "NONE",
    eatingDrinking: "NORMAL",
    difficultyBreathing: false,
    difficultySwallowing: false,
    severeTrauma: false,
  });
  const [feedback, setFeedback] = useState({
    problemResolved: "PARTLY",
    understoodInstructions: true,
    needsHelp: false,
  });
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  const [pending, setPending] = useState(false);
  const [actionNotice, setActionNotice] = useState("");
  const [error, setError] = useState("");
  const activeRequest = useRef(0);
  const careInput = useRef(null);
  const recallInput = useRef(null);
  const monitorInput = useRef(null);
  const messageInput = useRef(null);

  const patientRelease = releasedData;
  const patientReleaseDetails = useMemo(
    () => (patientRelease ? releaseDetails(patientRelease) : {}),
    [patientRelease],
  );
  const pendingCheckIn = useMemo(
    () => checkIns.find((item) => item.status !== "COMPLETED" && item.ref),
    [checkIns],
  );
  const releaseStep = releasedData ? 3 : releaseReview ? 2 : 1;
  const timeZone = localTimeZoneLabel();

  useEffect(() => {
    if (role !== "DENTIST" || releasedData) return undefined;

    let ignore = false;
    setTemplateLoading(true);
    setTemplateNotice("");
    setSelectedTemplate(null);
    const query = new URLSearchParams({
      locale,
      procedure_code: procedure,
    });

    apiRequest(`/api/v1/post-treatment/templates?${query}`, {
      role: "DENTIST",
    })
      .then((data) => {
        if (ignore) return;
        const nextTemplates = normalizeTemplates(data);
        setTemplates(nextTemplates);
        setSelectedTemplate(nextTemplates[0] ?? null);
        if (!nextTemplates.length) {
          setTemplateNotice(
            "Chưa có mẫu đã duyệt cho lựa chọn này. Nha sĩ vẫn có thể nhập hướng dẫn thủ công.",
          );
        }
      })
      .catch((failure) => {
        if (ignore) return;
        setTemplates([]);
        setTemplateNotice(
          unavailableFeatureMessage(failure, "Thư viện mẫu đã duyệt"),
        );
      })
      .finally(() => {
        if (!ignore) setTemplateLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [locale, procedure, releasedData, role]);

  const request = async (url, body, demoRole, handleSuccess) => {
    const requestId = activeRequest.current + 1;
    activeRequest.current = requestId;
    setPending(true);
    setError("");

    try {
      const data = await apiRequest(url, {
        method: "POST",
        body,
        role: demoRole,
      });
      if (activeRequest.current === requestId) handleSuccess(data);
    } catch (failure) {
      if (activeRequest.current === requestId) setError(errorMessage(failure));
    } finally {
      if (activeRequest.current === requestId) setPending(false);
    }
  };

  const changeRole = (event) => {
    activeRequest.current += 1;
    setRole(event.target.value);
    setPending(false);
    setTranscript([]);
    setMessage("");
    setError("");
    setActionNotice("");
  };

  const choosePrompt = (prompt) => {
    setMessage(prompt);
    setError("");
    messageInput.current?.focus();
  };

  const chat = async (event) => {
    event.preventDefault();
    const trimmedMessage = message.trim();
    if (!trimmedMessage) {
      setError("Hãy nhập câu hỏi trước khi gửi.");
      messageInput.current?.focus();
      return;
    }

    const userMessage = {
      id: createRequestId(),
      kind: "user",
      message: trimmedMessage,
    };
    setTranscript((current) => [...current, userMessage]);
    setMessage("");

    await request(
      "/api/v1/portal/chat",
      { message: trimmedMessage },
      "PATIENT",
      (data) => {
        if (data.escalation) {
          setPinnedEscalation(data);
          return;
        }
        setTranscript((current) => [
          ...current,
          { id: createRequestId(), kind: "assistant", data },
        ]);
      },
    );
  };

  const prepareReleaseReview = (event) => {
    event.preventDefault();
    const nextErrors = {};
    const trimmedCare = care.trim();
    const parsedRecall = parseLocalDateTime(recall);
    const parsedMonitor = parseLocalDateTime(monitor);
    const now = Date.now();

    if (!trimmedCare) nextErrors.care = "Hãy nhập hướng dẫn chăm sóc.";
    if (!parsedRecall) {
      nextErrors.recall = "Hãy nhập ngày giờ tái khám hợp lệ.";
    } else if (parsedRecall.date.getTime() <= now) {
      nextErrors.recall = "Ngày giờ tái khám phải ở trong tương lai.";
    }
    if (!parsedMonitor) {
      nextErrors.monitor = "Hãy nhập thời điểm kết thúc theo dõi hợp lệ.";
    } else if (parsedMonitor.date.getTime() <= now) {
      nextErrors.monitor = "Thời điểm kết thúc theo dõi phải ở trong tương lai.";
    }

    setFieldErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      const firstInvalid = nextErrors.care
        ? careInput
        : nextErrors.recall
          ? recallInput
          : monitorInput;
      firstInvalid.current?.focus();
      return;
    }

    setError("");
    setReleaseReview({
      careInstructions: trimmedCare,
      monitorAtDate: parsedMonitor.date,
      monitorUntil: parsedMonitor.apiValue,
      recallAt: parsedRecall.apiValue,
      recallAtDate: parsedRecall.date,
      template: appliedTemplate,
      templateCustomized,
    });
  };

  const editRelease = () => {
    setReleaseReview(null);
    setError("");
    window.requestAnimationFrame(() => careInput.current?.focus());
  };

  const confirmRelease = async () => {
    if (!releaseReview) return;

    const nextErrors = {};
    const now = Date.now();
    if (releaseReview.recallAtDate.getTime() <= now) {
      nextErrors.recall = "Ngày giờ tái khám đã qua. Hãy chọn thời điểm mới.";
    }
    if (releaseReview.monitorAtDate.getTime() <= now) {
      nextErrors.monitor =
        "Thời điểm kết thúc theo dõi đã qua. Hãy chọn thời điểm mới.";
    }
    if (Object.keys(nextErrors).length) {
      setFieldErrors(nextErrors);
      setReleaseReview(null);
      window.requestAnimationFrame(() =>
        (nextErrors.recall ? recallInput : monitorInput).current?.focus(),
      );
      return;
    }

    await request(
      `/api/v1/encounters/${DEMO_ENCOUNTER_ID}/release`,
      {
        care_instructions: releaseReview.careInstructions,
        recall_at: releaseReview.recallAt,
        monitor_until: releaseReview.monitorUntil,
      },
      "DENTIST",
      (data) => {
        setReleasedData({
          ...data,
          _template: releaseReview.template,
          _templateCustomized: releaseReview.templateCustomized,
        });
        setCheckIns(createSessionCheckIns());
        setAcknowledged(false);
        setFeedbackSubmitted(false);
        setCallbackSubmitted(false);
        setReleaseReview(null);
      },
    );
  };

  const applyTemplate = () => {
    if (!selectedTemplate) return;
    setCare(selectedTemplate.instructions);
    setAppliedTemplate(selectedTemplate);
    setTemplateCustomized(false);
    setFieldErrors((current) => ({ ...current, care: undefined }));
    window.requestAnimationFrame(() => careInput.current?.focus());
  };

  const acknowledgeRelease = () => {
    if (!patientRelease) return;
    setAcknowledged(true);
    setActionNotice(
      "Đã đánh dấu trong phiên dùng thử này. Xác nhận không được lưu hoặc gửi đến phòng khám và không phải đồng ý điều trị.",
    );
  };

  const submitCheckIn = (event) => {
    event.preventDefault();
    if (!pendingCheckIn) return;
    const response = {
      trend: checkInForm.trend,
      painScore: Number(checkInForm.painScore),
      swelling: checkInForm.swelling,
      bleeding: checkInForm.bleeding,
      eatingDrinking: checkInForm.eatingDrinking,
    };
    setCheckIns((current) =>
      current.map((item) =>
        item.ref === pendingCheckIn.ref
          ? { ...item, status: "COMPLETED", response }
          : item,
      ),
    );
    if (dangerousCheckIn) setPinnedEscalation(SESSION_RED_FLAG_GUIDANCE);
    setActionNotice(
      dangerousCheckIn
        ? "Check-in chỉ được đánh dấu trên màn hình. Hãy làm theo hướng dẫn khẩn cấp được ghim; dữ liệu không được gửi đến phòng khám."
        : "Check-in đã được đánh dấu trong phiên dùng thử. Câu trả lời không được lưu hoặc gửi đến phòng khám.",
    );
  };

  const submitCallback = (event) => {
    event.preventDefault();
    const parsedStart = callbackStart ? parseLocalDateTime(callbackStart) : null;
    const parsedEnd = callbackEnd ? parseLocalDateTime(callbackEnd) : null;
    if (Boolean(callbackStart) !== Boolean(callbackEnd)) {
      setActionNotice(
        "Hãy nhập cả thời điểm bắt đầu và kết thúc, hoặc để trống cả hai.",
      );
      return;
    }
    if ((callbackStart && !parsedStart) || (callbackEnd && !parsedEnd)) {
      setActionNotice("Khung giờ gọi lại không hợp lệ.");
      return;
    }
    if (
      (parsedStart && parsedStart.date.getTime() <= Date.now()) ||
      (parsedEnd && parsedEnd.date.getTime() <= Date.now())
    ) {
      setActionNotice("Khung giờ gọi lại phải ở trong tương lai.");
      return;
    }
    if (parsedStart && parsedEnd && parsedEnd.date <= parsedStart.date) {
      setActionNotice("Thời điểm kết thúc phải sau thời điểm bắt đầu.");
      return;
    }

    setCallbackSubmitted(true);
    setCallbackOpen(false);
    setCallbackStart("");
    setCallbackEnd("");
    setActionNotice(
      "Chỉ hoàn tất bản minh họa trên màn hình. Không có yêu cầu nào được gửi và nhân viên phòng khám chưa được liên hệ.",
    );
  };

  const submitFeedback = (event) => {
    event.preventDefault();
    setFeedbackSubmitted(true);
    setActionNotice(
      "Phản hồi chỉ được đánh dấu trong phiên dùng thử và không được lưu hoặc gửi đến phòng khám.",
    );
    if (feedback.needsHelp) setCallbackOpen(true);
  };

  const dangerousCheckIn =
    ["INCREASING", "SPREADING_RAPIDLY"].includes(checkInForm.swelling) ||
    checkInForm.bleeding === "UNCONTROLLED" ||
    checkInForm.difficultyBreathing ||
    checkInForm.difficultySwallowing ||
    checkInForm.severeTrauma;

  return (
    <section className="post-treatment-chat" aria-labelledby="post-treatment-title">
      <header className="feature-header">
        <div>
          <p className="eyebrow">Branch 4</p>
          <h2 id="post-treatment-title">Post-treatment journey</h2>
          <p>Phát hành hướng dẫn, theo dõi hồi phục và hỗ trợ bệnh nhân an toàn.</p>
        </div>
        <label className="role-picker" htmlFor="post-treatment-role">
          Vai trò dùng thử
          <select id="post-treatment-role" value={role} onChange={changeRole}>
            <option value="DENTIST">Dentist</option>
            <option value="PATIENT">Patient</option>
          </select>
        </label>
      </header>

      {role === "DENTIST" ? (
        <div className="dentist-workspace">
          <section className="scope-card" aria-labelledby="dentist-scope-title">
            <h3 id="dentist-scope-title">Phát hành cho bệnh nhân</h3>
            <p>
              Kiểm tra chính xác nội dung và thời gian trước khi xác nhận. Bản dùng thử này giữ luồng phát hành hiện có và không bổ sung bảng dữ liệu hay quy trình sửa đổi mới.
            </p>
          </section>

          <ReleaseStepper currentStep={releaseStep} />

          {releasedData ? (
            <>
              <section className="read-only-release print-summary" aria-labelledby="release-complete-title">
                <div className="section-heading">
                  <p className="read-only-banner" id="release-complete-title">
                    Bước 3 · Đã phát hành · Chỉ đọc
                  </p>
                  <button
                    type="button"
                    className="button-secondary compact-button no-print"
                    onClick={() => window.print()}
                  >
                    In bản tóm tắt
                  </button>
                </div>
                <ReleaseReply data={releasedData} />
                <PrintableSafetyNotice />
                {releasedData._template && (
                  <p className="template-provenance">
                    Trong phiên soạn thảo, nội dung dựa trên mẫu <strong>{releasedData._template.title}</strong>, phiên bản {releasedData._template.version}
                    {releasedData._templateCustomized
                      ? "; nha sĩ đã tùy chỉnh trước khi phát hành. Lựa chọn mẫu không được gửi hoặc lưu riêng."
                      : "; nội dung không được chỉnh sửa. Lựa chọn mẫu không được gửi hoặc lưu riêng."}
                  </p>
                )}
                <div className="no-print">
                  <button type="button" onClick={() => window.print()}>
                    In / lưu PDF
                  </button>
                </div>
              </section>
            </>
          ) : releaseReview ? (
            <section className="review-panel" aria-labelledby="release-review-title">
              <p className="step-label">Bước 2/3 · Xem lại</p>
              <h3 id="release-review-title">Xác nhận nội dung phát hành</h3>
              <p>
                Đây là nội dung chính xác sẽ được gửi. Thời gian hiển thị theo múi giờ thiết bị: <strong>{timeZone}</strong>.
              </p>
              {releaseReview.template && (
                <div className="template-provenance">
                  <strong>Nguồn mẫu trong phiên:</strong> {releaseReview.template.title} · phiên bản {releaseReview.template.version} · {releaseReview.template.locale.toUpperCase()}.
                  {releaseReview.templateCustomized
                    ? " Nha sĩ đã tùy chỉnh nội dung. Lựa chọn mẫu không được gửi hoặc lưu riêng."
                    : " Nội dung chưa được tùy chỉnh. Lựa chọn mẫu không được gửi hoặc lưu riêng."}
                </div>
              )}
              <ReleasedValues
                careInstructions={releaseReview.careInstructions}
                recallAt={releaseReview.recallAt}
                monitorUntil={releaseReview.monitorUntil}
                showTimeZone
              />
              <p className="immutable-warning">
                Sau khi xác nhận, màn hình chuyển sang kết quả chỉ đọc. Bản demo này không cung cấp quy trình sửa đổi hoặc lưu phiên bản mới.
              </p>
              <div className="form-actions">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={editRelease}
                  disabled={pending}
                >
                  Quay lại chỉnh sửa
                </button>
                <button type="button" onClick={confirmRelease} disabled={pending}>
                  {pending ? "Đang phát hành…" : "Xác nhận và phát hành"}
                </button>
              </div>
            </section>
          ) : (
            <>
              <TemplateSelector
                locale={locale}
                onLocaleChange={(event) => setLocale(event.target.value)}
                procedure={procedure}
                onProcedureChange={(event) => setProcedure(event.target.value)}
                templates={templates}
                selectedTemplate={selectedTemplate}
                onTemplateChange={(event) =>
                  setSelectedTemplate(
                    templates.find((item) => item.ref === event.target.value) ?? null,
                  )
                }
                onApply={applyTemplate}
                loading={templateLoading}
                notice={templateNotice}
              />

              <form className="release-form" noValidate onSubmit={prepareReleaseReview}>
                <p className="step-label">Bước 1/3 · Soạn thảo</p>
                {appliedTemplate && (
                  <p className="template-provenance" id="care-template-provenance">
                    Đang dùng mẫu trong phiên <strong>{appliedTemplate.title}</strong> · phiên bản {appliedTemplate.version}.
                    {templateCustomized
                      ? " Nội dung đã được nha sĩ tùy chỉnh."
                      : " Nội dung vẫn khớp mẫu đã duyệt."}
                  </p>
                )}
                <p className="timezone-note" id="release-timezone-help">
                  Các thời điểm dùng múi giờ thiết bị: <strong>{timeZone}</strong>.
                </p>
                <label htmlFor="care-instructions">
                  Hướng dẫn
                  <textarea
                    id="care-instructions"
                    ref={careInput}
                    value={care}
                    onChange={(event) => {
                      const nextCare = event.target.value;
                      setCare(nextCare);
                      if (appliedTemplate) {
                        setTemplateCustomized(
                          nextCare.trim() !== appliedTemplate.instructions.trim(),
                        );
                      }
                      setFieldErrors((current) => ({ ...current, care: undefined }));
                    }}
                    disabled={pending}
                    maxLength={2000}
                    aria-invalid={Boolean(fieldErrors.care)}
                    aria-describedby={
                      [
                        "care-count",
                        appliedTemplate ? "care-template-provenance" : "",
                        fieldErrors.care ? "care-error" : "",
                      ].filter(Boolean).join(" ")
                    }
                    required
                  />
                </label>
                <span className="field-meta" id="care-count">{care.length}/2000 ký tự</span>
                {fieldErrors.care && (
                  <span className="field-error" id="care-error" role="alert">{fieldErrors.care}</span>
                )}

                <div className="two-column-fields">
                  <label htmlFor="recall-at">
                    Tái khám
                    <input
                      id="recall-at"
                      ref={recallInput}
                      type="datetime-local"
                      value={recall}
                      onChange={(event) => {
                        setRecall(event.target.value);
                        setFieldErrors((current) => ({ ...current, recall: undefined }));
                      }}
                      disabled={pending}
                      aria-invalid={Boolean(fieldErrors.recall)}
                      aria-describedby={fieldErrors.recall ? "release-timezone-help recall-error" : "release-timezone-help"}
                      required
                    />
                    {fieldErrors.recall && (
                      <span className="field-error" id="recall-error" role="alert">{fieldErrors.recall}</span>
                    )}
                  </label>
                  <label htmlFor="monitor-until">
                    Theo dõi đến
                    <input
                      id="monitor-until"
                      ref={monitorInput}
                      type="datetime-local"
                      value={monitor}
                      onChange={(event) => {
                        setMonitor(event.target.value);
                        setFieldErrors((current) => ({ ...current, monitor: undefined }));
                      }}
                      disabled={pending}
                      aria-invalid={Boolean(fieldErrors.monitor)}
                      aria-describedby={fieldErrors.monitor ? "release-timezone-help monitor-error" : "release-timezone-help"}
                      required
                    />
                    {fieldErrors.monitor && (
                      <span className="field-error" id="monitor-error" role="alert">{fieldErrors.monitor}</span>
                    )}
                  </label>
                </div>
                <button disabled={pending}>Xem lại trước khi phát hành</button>
              </form>
            </>
          )}
        </div>
      ) : (
        <div className="patient-workspace">
          <section className="scope-card" aria-labelledby="patient-scope-title">
            <h3 id="patient-scope-title">Hỗ trợ sau điều trị</h3>
            <p>
              Chat chỉ dùng hồ sơ đã phát hành, FAQ phòng khám và nội dung nha khoa đã duyệt. Chat không chẩn đoán hoặc kê đơn.
            </p>
            <p>
              Quyền riêng tư: cuộc trò chuyện bên dưới chỉ tồn tại trong phiên trên màn hình này. Nội dung chat thô không được lưu vào nhật ký kiểm toán.
            </p>
          </section>

          <aside className="emergency-notice" aria-labelledby="emergency-notice-title">
            <h3 id="emergency-notice-title">Chat không được theo dõi theo thời gian thực</h3>
            <p>
              Nếu bạn khó thở, khó nuốt, sưng lan nhanh, chảy máu không kiểm soát hoặc bị chấn thương nặng, đừng chờ câu trả lời trong chat. Hãy tìm trợ giúp khẩn cấp ngay.
            </p>
          </aside>

          {pinnedEscalation && (
            <EscalationReply
              data={pinnedEscalation}
              onAcknowledge={() => setPinnedEscalation(null)}
            />
          )}

          <JourneyTimeline
            releaseData={patientRelease}
            acknowledged={acknowledged}
            checkIns={checkIns}
          />

          {patientRelease && (
            <section className="patient-release print-summary" aria-labelledby="patient-release-title">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Hồ sơ hiện tại</p>
                  <h3 id="patient-release-title">Hướng dẫn đã phát hành</h3>
                </div>
                <button
                  type="button"
                  className="button-secondary compact-button no-print"
                  onClick={() => window.print()}
                >
                  In / lưu PDF
                </button>
              </div>
              {patientRelease._template && (
                <p className="template-provenance">
                  Trong phiên hiện tại, nội dung được soạn từ mẫu đã duyệt{" "}
                  <strong>{patientRelease._template.title}</strong>. Lựa chọn mẫu không được lưu riêng trên máy chủ.
                </p>
              )}
              <ReleasedValues
                careInstructions={patientReleaseDetails.careInstructions}
                recallAt={patientReleaseDetails.recallAt}
                monitorUntil={patientReleaseDetails.monitorUntil}
              />
              <Citations citations={patientReleaseDetails.citations} />
              <PrintableSafetyNotice />

              <section className="acknowledgement-panel no-print" aria-labelledby="acknowledgement-title">
                <h4 id="acknowledgement-title">Bạn đã đọc hướng dẫn này chưa?</h4>
                {acknowledged ? (
                  <p className="success-message">✓ Đã đánh dấu “Tôi đã đọc và hiểu” trong phiên này. Trạng thái không được lưu hoặc gửi.</p>
                ) : (
                  <div className="form-actions">
                    <button
                      type="button"
                      onClick={acknowledgeRelease}
                    >
                      Tôi đã đọc và hiểu
                    </button>
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => setCallbackOpen(true)}
                    >
                      Tôi cần hỗ trợ
                    </button>
                  </div>
                )}
                <small>Minh họa trong phiên: không lưu, không gửi, không phải đồng ý điều trị và không thay thế tư vấn của nha sĩ.</small>
              </section>
            </section>
          )}

          {patientRelease && pendingCheckIn && (
            <form className="check-in-form" noValidate onSubmit={submitCheckIn}>
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Mốc {pendingCheckIn.offsetHours} giờ · chỉ trong phiên</p>
                  <h3>Hôm nay bạn hồi phục thế nào?</h3>
                </div>
                {pendingCheckIn.dueAt && <time dateTime={pendingCheckIn.dueAt}>{formatDateTime(pendingCheckIn.dueAt)}</time>}
              </div>
              <p className="session-only-note">Minh họa UX: câu trả lời không được lưu hay gửi đến phòng khám và sẽ mất khi tải lại trang. Biểu mẫu không đưa ra chẩn đoán.</p>
              <div className="three-column-fields">
                <label htmlFor="check-in-trend">
                  So với trước
                  <select id="check-in-trend" value={checkInForm.trend} onChange={(event) => setCheckInForm((current) => ({ ...current, trend: event.target.value }))}>
                    <option value="BETTER">Tốt hơn</option>
                    <option value="SAME">Không đổi</option>
                    <option value="WORSE">Tệ hơn</option>
                  </select>
                </label>
                <label htmlFor="pain-score">
                  Mức đau: {checkInForm.painScore}/10
                  <input id="pain-score" type="range" min="0" max="10" value={checkInForm.painScore} onChange={(event) => setCheckInForm((current) => ({ ...current, painScore: event.target.value }))} />
                </label>
                <label htmlFor="eating-drinking">
                  Ăn và uống
                  <select id="eating-drinking" value={checkInForm.eatingDrinking} onChange={(event) => setCheckInForm((current) => ({ ...current, eatingDrinking: event.target.value }))}>
                    <option value="NORMAL">Bình thường</option>
                    <option value="DIFFICULT">Khó khăn</option>
                    <option value="UNABLE">Không thể ăn/uống</option>
                  </select>
                </label>
                <label htmlFor="swelling-level">
                  Sưng
                  <select id="swelling-level" value={checkInForm.swelling} onChange={(event) => setCheckInForm((current) => ({ ...current, swelling: event.target.value }))}>
                    <option value="NONE">Không</option>
                    <option value="MILD">Nhẹ</option>
                    <option value="INCREASING">Đang tăng</option>
                    <option value="SPREADING_RAPIDLY">Lan nhanh</option>
                  </select>
                </label>
                <label htmlFor="bleeding-level">
                  Chảy máu
                  <select id="bleeding-level" value={checkInForm.bleeding} onChange={(event) => setCheckInForm((current) => ({ ...current, bleeding: event.target.value }))}>
                    <option value="NONE">Không</option>
                    <option value="CONTROLLED">Đã kiểm soát</option>
                    <option value="UNCONTROLLED">Không kiểm soát</option>
                  </select>
                </label>
              </div>
              <fieldset className="red-flag-fieldset">
                <legend>Dấu hiệu cảnh báo rõ ràng</legend>
                <label><input type="checkbox" checked={checkInForm.difficultyBreathing} onChange={(event) => setCheckInForm((current) => ({ ...current, difficultyBreathing: event.target.checked }))} /> Khó thở</label>
                <label><input type="checkbox" checked={checkInForm.difficultySwallowing} onChange={(event) => setCheckInForm((current) => ({ ...current, difficultySwallowing: event.target.checked }))} /> Khó nuốt</label>
                <label><input type="checkbox" checked={checkInForm.severeTrauma} onChange={(event) => setCheckInForm((current) => ({ ...current, severeTrauma: event.target.checked }))} /> Chấn thương nặng</label>
              </fieldset>
              {dangerousCheckIn && (
                <p className="red-flag-warning" role="alert">
                  Câu trả lời có dấu hiệu cảnh báo. Nếu bạn đang gặp nguy hiểm, đừng chờ gửi biểu mẫu hoặc chờ cuộc gọi lại; hãy tìm trợ giúp khẩn cấp ngay.
                </p>
              )}
              <button>Đánh dấu check-in trong phiên</button>
            </form>
          )}

          <section className="support-actions no-print" aria-labelledby="support-actions-title">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Minh họa trong phiên · không gửi</p>
                <h3 id="support-actions-title">Mô phỏng yêu cầu gọi lại</h3>
              </div>
              {!callbackOpen && (
                <button type="button" className="button-secondary compact-button" onClick={() => { setCallbackOpen(true); setCallbackSubmitted(false); }}>
                  {callbackSubmitted ? "Thử lại biểu mẫu" : "Mở biểu mẫu"}
                </button>
              )}
            </div>
            <p className="session-only-note">Biểu mẫu chỉ minh họa UX trên màn hình: không lưu, không gửi và không liên hệ nhân viên phòng khám. Không dùng cho tình huống cấp cứu.</p>
            {callbackSubmitted && !callbackOpen && (
              <p className="success-message">✓ Đã hoàn tất minh họa trong phiên. Không có yêu cầu thật nào được gửi.</p>
            )}
            {callbackOpen && (
              <form className="nested-form" noValidate onSubmit={submitCallback}>
                <label htmlFor="callback-reason">
                  Lý do
                  <select id="callback-reason" value={callbackReason} onChange={(event) => setCallbackReason(event.target.value)}>
                    {CALLBACK_REASONS.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
                  </select>
                </label>
                <div className="two-column-fields">
                  <label htmlFor="callback-start">
                    Có thể gọi từ (không bắt buộc)
                    <input id="callback-start" type="datetime-local" value={callbackStart} onChange={(event) => setCallbackStart(event.target.value)} />
                  </label>
                  <label htmlFor="callback-end">
                    Đến (không bắt buộc)
                    <input id="callback-end" type="datetime-local" value={callbackEnd} onChange={(event) => setCallbackEnd(event.target.value)} />
                  </label>
                </div>
                <div className="form-actions">
                  <button type="button" className="button-secondary" onClick={() => setCallbackOpen(false)}>Hủy</button>
                  <button>Đánh dấu yêu cầu trong phiên</button>
                </div>
              </form>
            )}
          </section>

          {patientRelease && (
            feedbackSubmitted ? (
              <p className="success-message no-print">
                ✓ Phản hồi đã được đánh dấu trong phiên. Không có dữ liệu nào được lưu hoặc gửi.
              </p>
            ) : (
            <form className="feedback-form no-print" noValidate onSubmit={submitFeedback}>
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Phản hồi trong phiên · không gửi</p>
                  <h3>Trải nghiệm sau điều trị</h3>
                </div>
              </div>
              <p className="session-only-note">Các lựa chọn dưới đây chỉ minh họa trải nghiệm; chúng sẽ mất khi tải lại trang.</p>
              <div className="three-column-fields">
                <label htmlFor="problem-resolved">
                  Vấn đề đã được giải quyết?
                  <select id="problem-resolved" value={feedback.problemResolved} onChange={(event) => setFeedback((current) => ({ ...current, problemResolved: event.target.value }))}>
                    <option value="YES">Có</option>
                    <option value="PARTLY">Một phần</option>
                    <option value="NO">Chưa</option>
                  </select>
                </label>
                <label className="choice-card"><input type="checkbox" checked={feedback.understoodInstructions} onChange={(event) => setFeedback((current) => ({ ...current, understoodInstructions: event.target.checked }))} /> Tôi hiểu hướng dẫn</label>
                <label className="choice-card"><input type="checkbox" checked={feedback.needsHelp} onChange={(event) => setFeedback((current) => ({ ...current, needsHelp: event.target.checked }))} /> Tôi vẫn cần hỗ trợ</label>
              </div>
              <button>Đánh dấu phản hồi trong phiên</button>
            </form>
            )
          )}

          {actionNotice && <p className="action-notice" role="status">{actionNotice}</p>}

          <section className="chat-panel no-print" aria-labelledby="chat-title">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Không lưu nội dung thô</p>
                <h3 id="chat-title">Chat thông tin đã duyệt</h3>
              </div>
              <button
                type="button"
                className="button-link compact-button"
                onClick={() => setTranscript([])}
                disabled={!transcript.length}
              >
                Xóa cuộc trò chuyện
              </button>
            </div>

            <div className="chat-transcript" aria-live="polite" aria-label="Cuộc trò chuyện trong phiên">
              {!transcript.length && <p className="empty-chat">Cuộc trò chuyện mới. Tin nhắn chỉ được giữ trong bộ nhớ của trang này.</p>}
              {transcript.map((item) => (
                <div key={item.id} className={`chat-bubble bubble-${item.kind}`}>
                  <span>{item.kind === "user" ? "Bạn" : "Trợ lý thông tin"}</span>
                  {item.kind === "user" ? <p>{item.message}</p> : <ChatReply data={item.data} />}
                </div>
              ))}
            </div>

            <section className="quick-prompts" aria-labelledby="quick-prompts-title">
              <h4 id="quick-prompts-title">Câu hỏi nhanh</h4>
              <div>
                {QUICK_PROMPTS.map((prompt) => (
                  <button type="button" className="prompt-button" key={prompt} onClick={() => choosePrompt(prompt)} disabled={pending}>{prompt}</button>
                ))}
              </div>
            </section>

            <form className="chat-form nested-form" noValidate onSubmit={chat}>
              <label htmlFor="patient-question">
                Câu hỏi
                <input id="patient-question" ref={messageInput} value={message} onChange={(event) => setMessage(event.target.value)} disabled={pending} maxLength={1000} aria-describedby="question-count" required />
              </label>
              <span className="field-meta" id="question-count">{message.length}/1000 ký tự</span>
              <button disabled={pending || !message.trim()}>{pending ? "Đang gửi…" : "Gửi"}</button>
            </form>
          </section>
        </div>
      )}

      {pending && (
        <p className="request-status" role="status" aria-live="polite">
          {role === "DENTIST" ? "Đang phát hành…" : "Đang tìm câu trả lời đã duyệt…"}
        </p>
      )}
      {error && <p className="request-error" role="alert">{error}</p>}
    </section>
  );
}

export const route = {
  path: "/post-treatment",
  label: "Post-treatment",
  Component: PostTreatmentChat,
};
