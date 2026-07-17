import React from "react";
import { createRoot } from "react-dom/client";
import { featureRoutes } from "./routes";
import "./style.css";

function normalizePath(pathname) {
  if (pathname === "/") return pathname;
  return pathname.replace(/\/+$/, "");
}

function Home() {
  return <main className="home-main">
    <section className="home-hero">
      <p className="app-eyebrow">CareGuard Dental</p>
      <h1>Điều phối ca khám an toàn, rõ ràng</h1>
      <p>Demo kiểm soát quy trình nha khoa bằng deterministic workflow và human review.</p>
    </section>
    <nav className="feature-grid" aria-label="Các module demo">
      {featureRoutes.map(({ path, label }) => <a className="feature-card" key={path} href={path}>
        <span className="feature-card-icon" aria-hidden="true">01</span>
        <span><strong>{label}</strong><small>Mở patient context và tiến trình ca khám</small></span>
        <span aria-hidden="true">→</span>
      </a>)}
    </nav>
  </main>;
}

function App() {
  const pathname = normalizePath(window.location.pathname);
  const activeRoute = featureRoutes.find(({ path }) => normalizePath(path) === pathname);

  if (!activeRoute && pathname !== "/") {
    return <main className="not-found">
      <p className="app-eyebrow">404</p>
      <h1>Không tìm thấy trang</h1>
      <a href="/">Quay về trang chủ</a>
    </main>;
  }

  if (!activeRoute) return <Home />;

  const { Component, label } = activeRoute;
  return <div className="app-shell">
    <header className="app-bar">
      <a className="app-brand" href="/" aria-label="CareGuard Dental - Trang chủ">
        <span aria-hidden="true">CG</span>
        <strong>CareGuard <i>Dental</i></strong>
      </a>
      <nav aria-label="Điều hướng chính">
        <a href="/">Tổng quan</a>
        <a href={activeRoute.path} aria-current="page">{label}</a>
      </nav>
      <span className="app-demo-badge">Synthetic demo</span>
    </header>
    <main className="feature-main"><Component /></main>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
