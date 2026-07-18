import React from "react";
import { createRoot } from "react-dom/client";
import { featureRoutes } from "./routes";
import "./style.css";

function App() {
  const activeRoute = featureRoutes.find(({ path }) => path === window.location.pathname) || featureRoutes[0];

  if (!activeRoute) return <main><p>Không có module nào được đăng ký.</p></main>;

  const ActiveFeature = activeRoute.Component;
  return <>
    <header className="app-header">
      <a className="app-brand" href="/">CareGuard Dental</a>
      <nav id="feature-routes" aria-label="Modules">
        {featureRoutes.map(({ path, label }) => <a
          key={path}
          className={activeRoute.path === path ? "is-active" : ""}
          href={path}
        >{label}</a>)}
      </nav>
    </header>
    <main><ActiveFeature /></main>
  </>;
}

createRoot(document.getElementById("root")).render(<App />);
