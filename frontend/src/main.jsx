import React from "react";
import { createRoot } from "react-dom/client";
import { featureRoutes } from "./routes";
import "./style.css";

function App() {
  const activeRoute = featureRoutes.find(({ path }) => path === window.location.pathname);
  return <main>
    <h1>CareGuard Dental</h1>
    <p>Demo kiểm soát tuân thủ nha khoa.</p>
    <nav id="feature-routes" aria-label="Modules">{featureRoutes.map(({ path, label }) => <a key={path} href={path}>{label}</a>)}</nav>
    {activeRoute ? <activeRoute.Component /> : <p>Chọn một module để bắt đầu.</p>}
  </main>;
}

createRoot(document.getElementById("root")).render(<App />);
