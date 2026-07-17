import React from "react";
import { createRoot } from "react-dom/client";
import { featureRoutes } from "./routes";
import "./style.css";

function App() {
  const route = featureRoutes.find(item => item.path === window.location.pathname);
  if (route) return <route.Component />;
  return <main><h1>CareGuard Dental</h1><p>Demo kiểm soát tuân thủ nha khoa.</p><nav id="feature-routes" aria-label="Modules">{featureRoutes.map(({ path, label }) => <a key={path} href={path}>{label}</a>)}</nav></main>;
}

createRoot(document.getElementById("root")).render(<App />);
