import React from "react";
import { createRoot } from "react-dom/client";
import { DEMO_ROLES, DemoProvider, useDemoContext } from "./demo-context";
import { featureRoutes } from "./routes";
import "./style.css";

const ROLE_LABELS = {
  FRONT_DESK: "Front desk",
  ASSISTANT: "Assistant",
  DENTIST: "Dentist",
  PATIENT: "Patient",
  QA: "QA / Compliance",
};

function ModuleLink({ route, index, activeRoute, routeHref }) {
  return <a
    className={activeRoute.path === route.path ? "is-active" : ""}
    href={routeHref(route.path)}
    aria-current={activeRoute.path === route.path ? "page" : undefined}
  >
    <span>{String(index + 1).padStart(2, "0")}</span>
    {route.label}
  </a>;
}

function WorkflowNavigation({ activeRoute, routeHref, position = "top" }) {
  const currentIndex = featureRoutes.findIndex(route => route.path === activeRoute.path);
  const previous = featureRoutes[currentIndex - 1];
  const next = featureRoutes[currentIndex + 1];
  const progress = ((currentIndex + 1) / featureRoutes.length) * 100;

  if (position === "bottom") return <nav className="module-pager" aria-label="Chuyển module">
    {previous
      ? <a href={routeHref(previous.path)}><small>← Module trước</small><strong>{previous.label}</strong></a>
      : <span />}
    <div><span>{currentIndex + 1} / {featureRoutes.length}</span><i><b style={{ width: `${progress}%` }} /></i></div>
    {next
      ? <a className="is-next" href={routeHref(next.path)}><small>Module tiếp →</small><strong>{next.label}</strong></a>
      : <a className="is-next" href={routeHref(featureRoutes[0].path)}><small>Quay lại đầu</small><strong>Encounter</strong></a>}
  </nav>;

  return <div className="workflow-context-bar">
    <div><span>Dental demo workflow</span><strong>{activeRoute.label}</strong></div>
    <div className="workflow-context-progress" aria-label={`Module ${currentIndex + 1} trên ${featureRoutes.length}`}>
      <span>{currentIndex + 1}/{featureRoutes.length}</span>
      <i><b style={{ width: `${progress}%` }} /></i>
    </div>
    <div className="workflow-quick-actions">
      {previous && <a href={routeHref(previous.path)}>← Trước</a>}
      {next && <a className="is-primary" href={routeHref(next.path)}>Tiếp theo →</a>}
    </div>
  </div>;
}

function AppShell() {
  const { accessToken, encounterId, role, routeHref, setAccessToken, setEncounterId, setRole } = useDemoContext();
  const activeRoute = featureRoutes.find(({ path }) => path === window.location.pathname)
    || (window.location.pathname === "/" ? featureRoutes[0] : null);

  if (!activeRoute) return <main className="route-not-found"><p>404 · CareGuard</p><h1>Không tìm thấy module</h1><a href={routeHref("/encounter")}>Mở Encounter →</a></main>;

  const ActiveFeature = activeRoute.Component;
  return <div className="app-shell">
    <header className="app-header">
      <div className="app-header-topline">
        <a className="app-brand" href={routeHref("/encounter")}>
          <span aria-hidden="true">CG</span>
          <div><strong>CareGuard</strong><small>Dental operations demo</small></div>
        </a>
        <div className="demo-context-controls">
          <label><span>Encounter context</span>
            <input value={encounterId} onChange={event => setEncounterId(event.target.value)} aria-label="Encounter ID" spellCheck="false" />
          </label>
          <label><span>Acting role</span>
            <select value={role} onChange={event => setRole(event.target.value)}>
              {DEMO_ROLES.map(item => <option value={item} key={item}>{ROLE_LABELS[item]}</option>)}
            </select>
          </label>
          <label className="demo-access-control"><span>Demo access key</span>
            <input type="password" value={accessToken} onChange={event => setAccessToken(event.target.value)} aria-label="Demo access key" autoComplete="current-password" placeholder="Required on public demo" />
          </label>
        </div>
      </div>
      <nav id="feature-routes" className="app-module-nav" aria-label="Modules">
        {featureRoutes.map((route, index) => <ModuleLink
          key={route.path}
          route={route}
          index={index}
          activeRoute={activeRoute}
          routeHref={routeHref}
        />)}
      </nav>
    </header>
    <WorkflowNavigation activeRoute={activeRoute} routeHref={routeHref} />
    <main><ActiveFeature /></main>
    <WorkflowNavigation activeRoute={activeRoute} routeHref={routeHref} position="bottom" />
    <footer className="app-footer"><span>CareGuard Dental · Synthetic demo data only</span><span>Policy dental-policy.v1</span></footer>
  </div>;
}

function App() {
  return <DemoProvider><AppShell /></DemoProvider>;
}

createRoot(document.getElementById("root")).render(<App />);
