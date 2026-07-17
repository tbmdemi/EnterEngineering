import React from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

function App() {
  return <main><h1>CareGuard Dental</h1><p>Demo kiểm soát tuân thủ nha khoa.</p><nav id="feature-routes" aria-label="Modules" /></main>;
}

createRoot(document.getElementById("root")).render(<App />);
