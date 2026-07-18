import React, { createContext, useContext, useMemo, useState } from "react";
import { ACCESS_TOKEN_KEY } from "./api";

export const SEED_ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003";
export const DEMO_ROLES = ["FRONT_DESK", "ASSISTANT", "DENTIST", "PATIENT", "QA"];

const DemoContext = createContext(null);

function initialValue() {
  const params = new URLSearchParams(window.location.search);
  const requestedRole = params.get("role") || window.sessionStorage.getItem("careguard.demoRole") || "DENTIST";
  return {
    encounterId: params.get("id") || window.sessionStorage.getItem("careguard.encounterId") || SEED_ENCOUNTER_ID,
    role: DEMO_ROLES.includes(requestedRole) ? requestedRole : "DENTIST",
    accessToken: window.sessionStorage.getItem(ACCESS_TOKEN_KEY) || "",
  };
}

function syncUrl(encounterId, role) {
  const url = new URL(window.location.href);
  url.searchParams.set("id", encounterId);
  url.searchParams.set("role", role);
  window.history.replaceState({}, "", url);
}

export function DemoProvider({ children }) {
  const [context, setContext] = useState(initialValue);

  const update = next => setContext(current => {
    const value = { ...current, ...next };
    window.sessionStorage.setItem("careguard.demoRole", value.role);
    window.sessionStorage.setItem("careguard.encounterId", value.encounterId);
    if (value.accessToken) window.sessionStorage.setItem(ACCESS_TOKEN_KEY, value.accessToken);
    else window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
    syncUrl(value.encounterId, value.role);
    return value;
  });

  const value = useMemo(() => ({
    ...context,
    setRole: role => update({ role }),
    setEncounterId: encounterId => update({ encounterId }),
    setAccessToken: accessToken => update({ accessToken }),
    routeHref: path => `${path}?id=${encodeURIComponent(context.encounterId)}&role=${encodeURIComponent(context.role)}`,
  }), [context]);

  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemoContext() {
  const context = useContext(DemoContext);
  if (!context) throw new Error("useDemoContext must be used inside DemoProvider");
  return context;
}
