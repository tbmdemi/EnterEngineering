import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { DEMO_ROLES, DemoProvider, useDemoContext } from "./demo-context";
import { featureRoutes } from "./routes";
import "./style.css";

const ROLE_LABELS = {
  FRONT_DESK: ["Lễ tân", "Front desk"],
  ASSISTANT: ["Trợ lý", "Assistant"],
  DENTIST: ["Nha sĩ", "Dentist"],
  PATIENT: ["Bệnh nhân", "Patient"],
  QA: ["QA / Tuân thủ", "QA / Compliance"],
};

const ROUTE_LABELS = {
  "/encounter": ["Ca khám", "Encounter"],
  "/documentation-ai": ["Hồ sơ & AI", "Documentation & AI"],
  "/pre-treatment": ["Trước điều trị", "Pre-treatment"],
  "/coordination": ["Điều phối", "Coordination"],
  "/post-treatment": ["Sau điều trị", "Post-treatment"],
  "/compliance": ["Tuân thủ", "Compliance"],
};

const ROUTE_HELP = {
  "/encounter": {
    summary: ["Theo dõi giai đoạn hiện tại và chuyển ca khám sang bước tiếp theo.", "Track the current stage and advance the encounter."],
    steps: [
      ["Kiểm tra đúng mã ca khám và chọn vai trò Nha sĩ.", "Confirm the encounter ID and select the Dentist role."],
      ["Đọc điều kiện còn thiếu trước khi bấm Tiếp tục.", "Review missing requirements before selecting Continue."],
      ["Xác nhận riêng khi chuyển ca sang CLOSED.", "Confirm explicitly before moving the encounter to CLOSED."],
    ],
  },
  "/documentation-ai": {
    summary: ["Lưu hồ sơ lâm sàng và kiểm tra dữ kiện do AI trích xuất.", "Save clinical documentation and review AI-extracted facts."],
    steps: [
      ["Chọn Trợ lý hoặc Nha sĩ để nhập hồ sơ.", "Select Assistant or Dentist to enter documentation."],
      ["Lưu biểu mẫu có cấu trúc trước.", "Save the structured form first."],
      ["Nha sĩ chấp nhận hoặc từ chối dữ kiện AI chưa xác minh.", "A Dentist accepts or rejects unverified AI facts."],
    ],
  },
  "/pre-treatment": {
    summary: ["Hoàn thành các kiểm tra an toàn bắt buộc trước điều trị.", "Complete required safety checks before treatment."],
    steps: [
      ["Khai báo thủ thuật có yêu cầu hình ảnh hay không.", "Declare whether the procedure requires imaging."],
      ["Kiểm tra nguồn trích dẫn và nhập dữ liệu hiện tại.", "Review cited sources and enter current data."],
      ["Xác nhận từng mục cho đến khi trạng thái sẵn sàng.", "Confirm each item until the checklist is ready."],
    ],
  },
  "/coordination": {
    summary: ["Xử lý danh sách việc theo đúng vai trò phụ trách.", "Process the worklist for the responsible role."],
    steps: [
      ["Chọn Lễ tân, Trợ lý hoặc Nha sĩ để xem danh sách tương ứng.", "Select Front Desk, Assistant, or Dentist for the matching worklist."],
      ["Xác nhận bàn giao trước khi hoàn tất tác vụ.", "Acknowledge handoffs before completing them."],
      ["Với xung đột lịch, kiểm tra rồi chọn lý do xử lý.", "For schedule conflicts, evaluate and choose a resolution reason."],
    ],
  },
  "/post-treatment": {
    summary: ["Phát hành hướng dẫn đã xác minh và thử chat phía bệnh nhân.", "Release verified guidance and test the patient chat."],
    steps: [
      ["Dùng vai trò Nha sĩ để nhập hướng dẫn và lịch theo dõi.", "Use the Dentist role to enter instructions and follow-up dates."],
      ["Phát hành gói chăm sóc trước khi đóng ca.", "Release the care package before closing the encounter."],
      ["Chuyển sang Bệnh nhân để thử câu hỏi có nguồn hoặc tình huống khẩn cấp.", "Switch to Patient to test cited answers or emergency escalation."],
    ],
  },
  "/compliance": {
    summary: ["Đánh giá nghĩa vụ, tác vụ phát sinh và điều kiện đóng ca.", "Evaluate obligations, generated tasks, and close readiness."],
    steps: [
      ["Bấm Đánh giá để lưu kết quả chính sách hiện tại.", "Select Evaluate to persist current policy findings."],
      ["Mở module được gợi ý để xử lý mục còn thiếu.", "Open the suggested module to resolve missing items."],
      ["Dùng Sẵn sàng để kiểm tra lại trước khi đóng ca.", "Use Readiness to check again before closing the encounter."],
    ],
  },
};

function HelpCenter({ activeRoute, routeHref, tr }) {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef(null);
  const launcherRef = useRef(null);
  const help = ROUTE_HELP[activeRoute.path];
  const moduleLabel = tr(...ROUTE_LABELS[activeRoute.path]);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnEscape = event => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", closeOnEscape);
    document.body.classList.add("help-is-open");
    dialogRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.classList.remove("help-is-open");
      launcherRef.current?.focus();
    };
  }, [open]);

  return <>
    <button ref={launcherRef} className="help-launcher" type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}>
      <span aria-hidden="true">?</span>{tr("Hướng dẫn", "Help")}
    </button>
    {open && <div className="help-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section ref={dialogRef} className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="help-title" tabIndex="-1">
        <header><div><span>{tr("Hướng dẫn theo màn hình", "Contextual guide")}</span><h2 id="help-title">{moduleLabel}</h2></div><button type="button" onClick={() => setOpen(false)} aria-label={tr("Đóng hướng dẫn", "Close guide")}>×</button></header>
        <p className="help-summary">{tr(...help.summary)}</p>
        <ol>{help.steps.map((step, index) => <li key={index}><i>{index + 1}</i><span>{tr(...step)}</span></li>)}</ol>
        <aside><strong>{tr("Mẹo demo", "Demo tip")}</strong><p>{tr("Thanh trên cùng luôn giữ mã ca khám, vai trò và ngôn ngữ khi bạn chuyển module.", "The top bar preserves the encounter ID, role, and language while you move between modules.")}</p></aside>
        <footer><button type="button" onClick={() => setOpen(false)}>{tr("Đã hiểu", "Got it")}</button><a href={routeHref("/encounter")}>{tr("Về đầu quy trình →", "Go to workflow start →")}</a></footer>
      </section>
    </div>}
  </>;
}

function ModuleLink({ route, index, activeRoute, routeHref, tr }) {
  return <a
    className={activeRoute.path === route.path ? "is-active" : ""}
    href={routeHref(route.path)}
    aria-current={activeRoute.path === route.path ? "page" : undefined}
  >
    <span>{String(index + 1).padStart(2, "0")}</span>
    {tr(...(ROUTE_LABELS[route.path] || [route.label, route.label]))}
  </a>;
}

function WorkflowNavigation({ activeRoute, routeHref, tr, position = "top" }) {
  const currentIndex = featureRoutes.findIndex(route => route.path === activeRoute.path);
  const previous = featureRoutes[currentIndex - 1];
  const next = featureRoutes[currentIndex + 1];
  const progress = ((currentIndex + 1) / featureRoutes.length) * 100;

  const label = route => tr(...(ROUTE_LABELS[route.path] || [route.label, route.label]));
  if (position === "bottom") return <nav className="module-pager" aria-label={tr("Chuyển module", "Module navigation")}>
    {previous
      ? <a href={routeHref(previous.path)}><small>{tr("← Module trước", "← Previous module")}</small><strong>{label(previous)}</strong></a>
      : <span />}
    <div><span>{currentIndex + 1} / {featureRoutes.length}</span><i><b style={{ width: `${progress}%` }} /></i></div>
    {next
      ? <a className="is-next" href={routeHref(next.path)}><small>{tr("Module tiếp →", "Next module →")}</small><strong>{label(next)}</strong></a>
      : <a className="is-next" href={routeHref(featureRoutes[0].path)}><small>{tr("Quay lại đầu", "Back to start")}</small><strong>{label(featureRoutes[0])}</strong></a>}
  </nav>;

  return <div className="workflow-context-bar">
    <div><span>{tr("Quy trình demo nha khoa", "Dental demo workflow")}</span><strong>{label(activeRoute)}</strong></div>
    <div className="workflow-context-progress" aria-label={tr(`Module ${currentIndex + 1} trên ${featureRoutes.length}`, `Module ${currentIndex + 1} of ${featureRoutes.length}`)}>
      <span>{currentIndex + 1}/{featureRoutes.length}</span>
      <i><b style={{ width: `${progress}%` }} /></i>
    </div>
    <div className="workflow-quick-actions">
      {previous && <a href={routeHref(previous.path)}>{tr("← Trước", "← Previous")}</a>}
      {next && <a className="is-primary" href={routeHref(next.path)}>{tr("Tiếp theo →", "Next →")}</a>}
    </div>
  </div>;
}

function AppShell() {
  const { accessToken, encounterId, language, role, routeHref, setAccessToken, setEncounterId, setLanguage, setRole, tr } = useDemoContext();
  const activeRoute = featureRoutes.find(({ path }) => path === window.location.pathname)
    || (window.location.pathname === "/" ? featureRoutes[0] : null);

  if (!activeRoute) return <main className="route-not-found"><p>404 · CareGuard</p><h1>{tr("Không tìm thấy module", "Module not found")}</h1><a href={routeHref("/encounter")}>{tr("Mở Ca khám →", "Open Encounter →")}</a></main>;

  const ActiveFeature = activeRoute.Component;
  return <div className="app-shell">
    <header className="app-header">
      <div className="app-header-topline">
        <a className="app-brand" href={routeHref("/encounter")}>
          <span aria-hidden="true">CG</span>
          <div><strong>CareGuard</strong><small>{tr("Demo vận hành nha khoa", "Dental operations demo")}</small></div>
        </a>
        <div className="demo-context-controls">
          <label><span>{tr("Mã ca khám", "Encounter context")}</span>
            <input value={encounterId} onChange={event => setEncounterId(event.target.value)} aria-label={tr("Mã ca khám", "Encounter ID")} spellCheck="false" />
          </label>
          <label><span>{tr("Vai trò", "Acting role")}</span>
            <select value={role} onChange={event => setRole(event.target.value)}>
              {DEMO_ROLES.map(item => <option value={item} key={item}>{tr(...ROLE_LABELS[item])}</option>)}
            </select>
          </label>
          <label className="demo-language-control"><span>{tr("Ngôn ngữ", "Language")}</span>
            <select value={language} onChange={event => setLanguage(event.target.value)} aria-label={tr("Ngôn ngữ giao diện", "Interface language")}>
              <option value="vi">Tiếng Việt</option><option value="en">English</option>
            </select>
          </label>
          <label className="demo-access-control"><span>{tr("Khóa truy cập demo", "Demo access key")}</span>
            <input type="password" value={accessToken} onChange={event => setAccessToken(event.target.value)} aria-label={tr("Khóa truy cập demo", "Demo access key")} autoComplete="current-password" placeholder={tr("Bắt buộc với demo công khai", "Required on public demo")} />
          </label>
        </div>
      </div>
      <nav id="feature-routes" className="app-module-nav" aria-label={tr("Các module", "Modules")}>
        {featureRoutes.map((route, index) => <ModuleLink
          key={route.path}
          route={route}
          index={index}
          activeRoute={activeRoute}
          routeHref={routeHref}
          tr={tr}
        />)}
      </nav>
    </header>
    <WorkflowNavigation activeRoute={activeRoute} routeHref={routeHref} tr={tr} />
    <main><ActiveFeature /></main>
    <WorkflowNavigation activeRoute={activeRoute} routeHref={routeHref} position="bottom" tr={tr} />
    <footer className="app-footer"><span>{tr("CareGuard Dental · Chỉ dùng dữ liệu demo synthetic", "CareGuard Dental · Synthetic demo data only")}</span><span>{tr("Chính sách", "Policy")} dental-policy.v1</span></footer>
    <HelpCenter activeRoute={activeRoute} routeHref={routeHref} tr={tr} />
  </div>;
}

function App() {
  return <DemoProvider><AppShell /></DemoProvider>;
}

createRoot(document.getElementById("root")).render(<App />);
