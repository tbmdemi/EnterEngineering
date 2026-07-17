import React, { useEffect, useState } from "react";

const ROLES = ["FRONT_DESK", "ASSISTANT", "DENTIST"];

function Coordination() {
  const [role, setRole] = useState("ASSISTANT");
  const [tasks, setTasks] = useState([]);
  const [message, setMessage] = useState("");

  const load = () => fetch(`/api/v1/tasks?owner_role=${role}`, { headers: { "X-Demo-Role": role } })
    .then(async response => {
      const body = await response.json();
      if (!response.ok) throw new Error(body.message || "Không tải được worklist");
      setTasks(body);
      setMessage("");
    })
    .catch(error => setMessage(error.message));

  useEffect(load, [role]);

  const update = (id, action) => fetch(`/api/v1/tasks/${id}/${action}`, {
    method: "POST",
    headers: { "X-Demo-Role": role },
  }).then(async response => {
    const body = await response.json();
    if (!response.ok) throw new Error(body.message || "Không cập nhật được task");
    load();
  }).catch(error => setMessage(error.message));

  return <section aria-labelledby="coordination-title">
    <h2 id="coordination-title">Coordination worklist</h2>
    <label>Vai trò <select value={role} onChange={event => setRole(event.target.value)}>{ROLES.map(value => <option key={value}>{value}</option>)}</select></label>
    {message && <p role="alert">{message}</p>}
    {!tasks.length && !message ? <p>Không có việc đang chờ.</p> : <ul>{tasks.map(task => <li key={task.id}>
      <strong>{task.task_type}</strong> — {task.status}
      {task.status === "OPEN" && <button type="button" onClick={() => update(task.id, "acknowledge")}>Acknowledge</button>}
      {task.status === "ACKNOWLEDGED" && <button type="button" onClick={() => update(task.id, "complete")}>Complete</button>}
    </li>)}</ul>}
  </section>;
}

export const route = { path: "/coordination", label: "Coordination", Component: Coordination };
