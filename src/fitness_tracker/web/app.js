"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const n = (v) =>
  Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
const iconPaths = {
  overview: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
  workouts: "M5 7v10M2 9v6M19 7v10M22 9v6M5 12h14",
  nutrition: "M8 3v6m-3-6v6c0 3 6 3 6 0V3M8 12v9M19 3c-4 0-5 9 0 9v9M19 3v9",
  exercises: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  progress: "M4 20V4m0 16h17M8 15l4-5 4 2 5-7",
  coach: "m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6Z",
  sleep: "M20 15.5A8.5 8.5 0 0 1 8.5 4a8.5 8.5 0 1 0 11.5 11.5Z",
  goals: "M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12l9-9m-5 0h5v5",
  plus: "M12 5v14M5 12h14",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  microphone: "M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0ZM5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8",
  stop: "M6 6h12v12H6Z",
  refresh: "M20 7v5h-5M4 17v-5h5M6.1 7a7 7 0 0 1 11.5-2L20 8M4 16l2.4 3A7 7 0 0 0 18 17",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  check: "m5 12 4 4L19 6",
  calendar:
    "M8 2v4M16 2v4M3 9h18M4 4h16a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1",
  drop: "M12 3S5 10 5 15a7 7 0 0 0 14 0c0-5-7-12-7-12",
  trophy:
    "M8 3h8v7a4 4 0 0 1-8 0ZM8 5H4v3a4 4 0 0 0 4 4m8-7h4v3a4 4 0 0 1-4 4m-4 2v6m-4 1h8",
  play: "m9 5 11 7-11 7Z",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8m-9 4h2m14 0h2M12 3v2m0 14v2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4",
};
const icon = (key) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${iconPaths[key] || iconPaths.overview}"/></svg>`;
iconPaths.track = iconPaths.calendar;
const pages = {
  overview: "Overview",
  track: "Track",
  exercises: "Exercise library",
  progress: "Progress & insights",
  goals: "Set goals",
  coach: "AI coach",
};
let state,
  catalog = [],
  byId = {},
  page = "overview",
  libraryPage = 0,
  libraryQuery = "",
  libraryMuscle = "",
  libraryEquipment = "",
  workoutTab = "workout",
  journalDate,
  prId,
  workoutForm,
  formDraft,
  chatBusy = false;
let toastTimer;
let reviewDate = "";
let dashboardMetric = "workout",
  dashboardMonth = "";
let intakeMetric = "protein", intakePeriod = "daily";
let bodyMapMode = "week",
  bodyMapDate = "";
let recordExercise = "",
  recordBodyPart = "";
let recordSearchQuery = "", recordRankedIds = null, recordSuggestionsOpen = false;
const exerciseSearchCache = new Map(), exerciseSearchVersions = {}, exerciseSearchTimers = {};
const image = (id) => `/assets/exercises/${encodeURIComponent(id)}.webp`;
const dateObj = (d) => new Date(d + "T12:00:00");
const dateLabel = (d, options = { month: "short", day: "numeric" }) =>
  dateObj(d).toLocaleDateString(undefined, options);
const addDays = (d, amount) => {
  let dt = dateObj(d);
  dt.setDate(dt.getDate() + amount);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
};
const toast = (msg) => {
  $("#toast").textContent = msg;
  $("#toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 4500);
};
let sessionRenewal;
async function renewAppSession() {
  if (!sessionRenewal) {
    sessionRenewal = (async () => {
      const response = await fetch("/api/session");
      const session = await response.json();
      if (!response.ok || typeof session.token !== "string" || !session.token)
        throw Error("Could not reconnect to the app. Please retry.");
      state.token = session.token;
    })().finally(() => {
      sessionRenewal = null;
    });
  }
  return sessionRenewal;
}
async function api(path, data) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = await fetch(
      "/api/" + path,
      data === undefined
        ? {}
        : {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-App-Token": state.token,
            },
            body: JSON.stringify(data),
          },
    );
    let result;
    if (response.ok && response.headers?.get("Content-Type")?.includes("application/x-ndjson")) {
      const reader = response.body.getReader(), decoder = new TextDecoder();
      let buffer = "", final;
      const consume = (line) => {
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.type === "stage") {
          chatStage = event.message;
          if ($("#chat-generation-status")) $("#chat-generation-status").textContent = chatStage;
        } else if (event.type === "final") final = event.response;
        else if (event.type === "error") throw Error(event.message);
      };
      try {
        while (true) {
          const { done, value } = await reader.read();
          buffer += decoder.decode(value, { stream: !done });
          const lines = buffer.split("\n"); buffer = lines.pop();
          lines.forEach(consume);
          if (done) break;
        }
        consume(buffer);
      } finally { reader.releaseLock(); }
      if (!final) throw Error("The response stream ended early. Your message is retained; reconnect to recover it.");
      result = final;
    } else result = await response.json();
    // Only this explicit pre-dispatch rejection can be safely replayed.
    // Network failures, provider errors and other 403s are never retried here.
    if (
      data !== undefined &&
      attempt === 0 &&
      response.status === 403 &&
      result.code === "session_expired"
    ) {
      await renewAppSession();
      continue;
    }
    if (!response.ok) throw Error(result.error || "Request failed");
    return result;
  }
}

async function refresh(renderPage = true) {
  state = await api("state");
  if (typeof exerciseSearchCache !== "undefined") exerciseSearchCache.clear();
  reconcileAiPreview();
  journalDate ||= state.today;
  $("#demo-badge").innerHTML = state.demo
    ? '<span class="pill gold">DEMO WORKSPACE</span>'
    : "";
  $("#avatar").textContent = (state.profile.name || "You")[0].toUpperCase();
  $("#header-date").textContent = dateLabel(state.today, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
  if (renderPage) render();
}
function head(eyebrow, title, sub, buttons = "") {
  return `<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="subtitle">${sub}</p></div><div class="actions">${buttons}<button class="btn secondary mobile-only" data-page="settings" aria-label="Settings">${icon("settings")}</button></div></div>`;
}
function button(label, action, kind = "primary", extra = "") {
  return `<button type="button" class="btn ${kind === "primary" ? "" : kind}" data-action="${action}" ${extra}>${label}</button>`;
}
function empty(title, desc, btn = "") {
  return `<div class="empty"><h3>${title}</h3><p>${desc}</p>${btn}</div>`;
}
function stat(label, value, unit, foot, key, percent) {
  return `<div class="card stat"><div class="stat-top">${label}<span class="icon-box">${icon(key)}</span></div><div class="stat-value">${value} <span>${unit}</span></div><div class="stat-foot">${foot}</div>${percent !== undefined ? `<div class="mini-track"><div style="width:${Math.min(100, Math.max(0, percent))}%"></div></div>` : ""}</div>`;
}
function chart(
  data,
  {
    goal = 0,
    unit = "g",
    color = "#a593e9",
    line = false,
    label = "Progress chart",
    height = 175,
    ceiling = 0,
  } = {},
) {
  const width = 600,
    left = 34,
    right = 14,
    bottom = 27,
    top = 14,
    w = width - left - right,
    h = height - top - bottom;
  const values = data
    .map((d) => d.value)
    .filter((v) => v !== null && v !== undefined);
  const max = ceiling || Math.max(goal * 1.15, ...values, 1) * 1.08;
  const y = (v) => top + h - (h * v) / max,
    x = (i) => left + ((i + 0.5) * w) / Math.max(data.length, 1);
  let svg = `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(label)}">`;
  for (let i = 0; i <= 3; i++) {
    let val = (max * i) / 3;
    svg += `<line class="gridline" x1="${left}" x2="${width - right}" y1="${y(val)}" y2="${y(val)}"/><text x="${left - 7}" y="${y(val) + 3}" text-anchor="end">${Math.round(val)}</text>`;
  }
  if (goal)
    svg += `<line x1="${left}" x2="${width - right}" y1="${y(goal)}" y2="${y(goal)}" stroke="#78629b" stroke-dasharray="4 4"><title>Goal: ${n(goal)} ${esc(unit)}</title></line>`;
  if (line) {
    let segment = [];
    const draw = () => {
      if (segment.length > 1)
        svg += `<polyline points="${segment.join(" ")}" fill="none" stroke="${color}" stroke-width="4" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>`;
      segment = [];
    };
    data.forEach((d, i) => {
      if (d.value === null || d.value === undefined) {
        draw();
        return;
      }
      segment.push(`${x(i)},${y(d.value)}`);
    });
    draw();
  }
  data.forEach((d, i) => {
    if (d.value !== null && d.value !== undefined) {
      const title = esc(`${d.label}: ${n(d.value)} ${unit}`);
      if (line)
        svg += `<circle cx="${x(i)}" cy="${y(d.value)}" r="5" fill="${color}" stroke="#171225" stroke-width="2" tabindex="0" aria-label="${title}"><title>${title}</title></circle>`;
      else {
        let bw = Math.min((w / data.length) * 0.55, 25);
        svg += `<rect x="${x(i) - bw / 2}" y="${y(d.value)}" width="${bw}" height="${Math.max(0, top + h - y(d.value))}" rx="3" fill="${color}"><title>${title}</title></rect>`;
      }
    }
    if (data.length <= 12 || i % Math.ceil(data.length / 9) === 0)
      svg += `<text x="${x(i)}" y="${height - 6}" text-anchor="middle">${esc(d.short || d.label)}</text>`;
  });
  svg += "</svg>";
  return (
    svg +
    `<details><summary>View chart data</summary><div class="scroll-table"><table class="data-table"><thead><tr><th>Date</th><th>${esc(unit)}</th></tr></thead><tbody>${data.map((d) => `<tr><td>${esc(d.label)}</td><td>${d.value === null || d.value === undefined ? "Not logged" : n(d.value)}</td></tr>`).join("")}</tbody></table></div></details>`
  );
}
function muscles() {
  const list = Object.entries(state.insights.body_parts || {}).sort(
    (a, b) => b[1] - a[1],
  );
  const max = Math.max(...list.map((x) => x[1]), 1);
  return list.length
    ? list
        .map(
          ([name, count], i) =>
            `<div class="muscle-row"><div class="muscle-top"><span>${esc(name[0].toUpperCase() + name.slice(1))}</span><span>${count} sets</span></div><div class="muscle-bar"><div style="width:${(count / max) * 100}%;background:${["#ae8ae8", "#8f94ed", "#6f9cdd", "#8b72c1", "#b48dce", "#7167a7"][i % 6]}"></div></div></div>`,
        )
        .join("")
    : empty(
        "Your training mix starts here",
        "Log a workout to see which muscles you train most.",
      );
}
function sessionTitle(value) {
  const date = dateObj(value),
    day = date.getDate();
  const suffix =
    day >= 11 && day <= 13
      ? "th"
      : { 1: "st", 2: "nd", 3: "rd" }[day % 10] || "th";
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][date.getMonth()]} ${day}${suffix} ${String(date.getFullYear()).slice(-2)}'`;
}
function workoutRow(e) {
  const sets = e.exercises.reduce((a, x) => a + (x.sets?.length || 0), 0);
  return `<div class="list-row"><span class="row-icon">${icon("workouts")}</span><div class="row-main"><h3>${esc(sessionTitle(e.date))}</h3><p>${e.exercises.length} exercise${e.exercises.length === 1 ? "" : "s"}${e.kind === "plan" ? " · " + e.exercises.map((x) => esc(byId[x.exercise_id]?.name || x.exercise_id)).join(", ") : ` · ${sets} set${sets === 1 ? "" : "s"}`}${e.duration ? " · " + n(e.duration) + " min" : ""}</p></div>${e.kind === "plan" ? button("Start", "start-plan", "soft", `data-id="${e.id}"`) : ""}<button class="link" data-action="edit-entry" data-id="${e.id}">View / edit ${icon("arrow")}</button></div>`;
}
function heatmap() {
  return `<div class="heatmap">${Object.entries(state.insights.daily)
    .map(
      ([d, v]) =>
        `<button type="button" class="heat-cell ${v.workouts ? "done" : "rest"} ${v.workouts > 1 ? "multi" : ""} ${d === state.today ? "today" : ""}" data-action="activity-day" data-date="${d}" aria-label="${d}: ${v.workouts ? v.workouts + " workout" + (v.workouts === 1 ? "" : "s") : "Rest day, no workout logged"}. View day details or open in Track"></button>`,
    )
    .join(
      "",
    )}</div><div class="heat-labels"><span>12 weeks ago</span><span>Each square is a day</span><span>Today</span></div><div class="habit-legend"><span><i class="gym-day" aria-hidden="true"></i>Workout day</span><span><i class="rest-day" aria-hidden="true"></i>Rest day · no workout logged</span></div>`;
}
function habitDayDetails(day) {
  const entries = state.entries.filter(entry => entry.date === day);
  const workouts = entries.filter(entry => entry.kind === "workout");
  const exercises = workouts.flatMap(entry => entry.exercises || []);
  const areas = Object.values(BodyMap.summarize(workouts, byId).areas)
    .filter(area => area.primary > 0)
    .sort((a, b) => b.primary - a.primary)
    .map(area => area.name);
  const meals = entries.filter(entry => entry.kind === "meal");
  const creatine = entries.filter(GoalTracking.isCreatine);
  const supplements = entries.filter(entry => entry.kind === "supplement" && !GoalTracking.isCreatine(entry));
  const sleep = sleepSummary(entries);
  const row = (label, value) => `<div><dt>${label}</dt><dd>${value}</dd></div>`;
  const workout = workouts.length
    ? `${exercises.length} exercise${exercises.length === 1 ? "" : "s"} · ${exercises.reduce((sum, exercise) => sum + (exercise.sets || []).length, 0)} sets`
    : "No workout logged";
  const protein = meals.length
    ? `${n(meals.reduce((sum, entry) => sum + entry.protein, 0))} g · ${meals.length} meal${meals.length === 1 ? "" : "s"}`
    : "Not logged";
  const creatineText = creatine.length ? `${n(creatine.reduce((sum, entry) => sum + entry.amount, 0))} g` : "Not logged";
  const supplementsText = supplements.length
    ? supplements.map(entry => `<span>${esc(entry.name)} · ${n(entry.amount)} ${esc(entry.unit)}</span>`).join("")
    : "Not logged";
  const sleepText = sleep.logs.length
    ? `${n(sleep.total)} h total · ${n(sleep.night)} h night${sleep.total > sleep.night ? ` · ${n(sleep.total - sleep.night)} h naps` : ""}${sleep.known ? `<span>${n(sleep.continuous)} h uninterrupted</span>` : ""}`
    : "Not logged";
  return `<div class="habit-day-heading"><h3>${esc(dateLabel(day, { weekday: "short", month: "short", day: "numeric", year: "numeric" }))}</h3><span class="habit-day-badge ${workouts.length ? "gym-day" : "rest-day"}">${workouts.length ? "Workout day" : "Rest day"}</span></div><dl>${row("Workout", workout)}${workouts.length ? row("Focus areas", areas.length ? esc(areas.join(" · ")) : "Not specified") : ""}${row("Protein", protein)}${row("Creatine", creatineText)}${row("Supplements", supplementsText)}${row("Sleep", sleepText)}</dl><p>Click the day to open Track.</p>`;
}
let habitTooltipCell = null, habitTooltipTimer;
function hideHabitDetails() {
  clearTimeout(habitTooltipTimer);
  habitTooltipCell?.removeAttribute("aria-describedby");
  habitTooltipCell = null;
  $("#habit-day-tooltip")?.remove();
}
function deferHideHabitDetails() {
  clearTimeout(habitTooltipTimer);
  habitTooltipTimer = setTimeout(() => {
    if (document.activeElement !== habitTooltipCell && !$("#habit-day-tooltip")?.matches(":hover")) hideHabitDetails();
  }, 120);
}
function showHabitDetails(cell) {
  clearTimeout(habitTooltipTimer);
  if (habitTooltipCell === cell) return;
  hideHabitDetails();
  habitTooltipCell = cell;
  const tooltip = document.createElement("div");
  tooltip.id = "habit-day-tooltip";
  tooltip.className = "habit-day-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.innerHTML = habitDayDetails(cell.dataset.date);
  document.body.append(tooltip);
  cell.setAttribute("aria-describedby", tooltip.id);
  positionHabitDetails(cell, tooltip);
}
function positionHabitDetails(cell, tooltip) {
  const anchor = cell.getBoundingClientRect(), box = tooltip.getBoundingClientRect();
  const clampX = value => Math.max(12, Math.min(value, window.innerWidth - box.width - 12));
  const clampY = value => Math.max(12, Math.min(value, window.innerHeight - box.height - 12));
  let left = clampX(anchor.left + anchor.width / 2 - box.width / 2);
  const below = anchor.bottom + 10;
  let top;
  if (below + box.height <= window.innerHeight - 12) top = below;
  else if (anchor.top - box.height - 10 >= 12) top = anchor.top - box.height - 10;
  else {
    top = clampY(anchor.top + anchor.height / 2 - box.height / 2);
    if (anchor.right + box.width + 22 <= window.innerWidth) left = anchor.right + 10;
    else if (anchor.left - box.width - 10 >= 12) left = anchor.left - box.width - 10;
  }
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${clampY(top)}px`;
}
function dayEntries() {
  const entries = journalEntries().filter((e) => e.date === journalDate);
  const meals = entries.filter((e) => e.kind === "meal"),
    supplements = entries.filter(
      (e) => e.kind === "supplement" && !GoalTracking.isCreatine(e),
    ),
    creatineEntries = entries.filter(GoalTracking.isCreatine),
    workouts = entries.filter((e) => e.kind === "workout");
  return {
    meals,
    supplements,
    creatineEntries,
    workouts,
    protein: meals.reduce((a, e) => a + e.protein, 0),
    creatine: creatineEntries
      .filter((e) => e.unit === "g")
      .reduce((a, e) => a + e.amount, 0),
  };
}
function dayWorkout(entry) {
  return `<div class="journal-workout">${workoutRow(entry)}${entry.exercises
    .map((item) => {
      const exercise = byId[item.exercise_id];
      return `<div class="list-row"><img class="journal-exercise-photo" src="${image(exercise.id)}" alt="${esc(exercise.name)}"><div class="row-main"><h3>${esc(exercise.name)}</h3><p>${item.sets.map((set) => (set.seconds ? `${n(set.seconds)} sec${set.weight ? ` · ${n(set.weight)} kg` : ""}` : `${set.weight ? n(set.weight) + " kg" : "Bodyweight"} × ${n(set.reps)} reps`)).join(" · ")}</p></div></div>`;
    })
    .join("")}</div>`;
}
function sleepSummary(entries) {
  const logs = entries.filter((e) => e.kind === "sleep");
  return {
    logs,
    total: logs.reduce((sum, e) => sum + e.hours, 0),
    night: logs
      .filter((e) => e.period === "night")
      .reduce((sum, e) => sum + e.hours, 0),
    continuous: Math.max(
      0,
      ...logs
        .filter((e) => e.period === "night" && e.continuous_hours != null)
        .map((e) => e.continuous_hours || 0),
    ),
    known: logs.some((e) => e.period === "night" && e.continuous_hours != null),
  };
}
function sleepJournal() {
  const s = sleepSummary(state.entries.filter((e) => e.date === journalDate));
  const p = state.profile;
  return `<section class="journal-panel journal-sleep" aria-label="Daily sleep journal"><div class="card-head"><div><h3>Your sleep</h3><p>${n(s.total)} / ${n(p.sleep_goal)} h total · ${n(s.night)} / ${n(p.night_hours_goal)} h at night</p></div><div class="actions">${button(icon("plus") + " Log sleep", "new-sleep")}</div></div><div class="sleep-progress-pair">${stat("Total rest", n(s.total), `/ ${n(p.sleep_goal)} h`, "Night sleep + naps", "sleep", (s.total / p.sleep_goal) * 100)}${stat("Night sleep", n(s.night), `/ ${n(p.night_hours_goal)} h`, "Includes sleep after brief wake-ups", "sleep", (s.night / p.night_hours_goal) * 100)}</div><p class="sleep-stretch-note">Uninterrupted stretch: <strong>${s.known ? n(s.continuous) : "—"} / ${n(p.night_sleep_goal)} h</strong> · Personal goal, separate from your consistency score.</p>${s.logs.length ? s.logs.map((e) => `<div class="list-row"><span class="row-icon">${icon("sleep")}</span><div class="row-main"><h3>${{ night: "Night sleep", afternoon: "Afternoon nap", other: "Other nap" }[e.period]}</h3><p>${n(e.hours)} h${e.period === "night" ? (e.continuous_hours == null ? " · uninterrupted stretch not recorded" : ` · ${n(e.continuous_hours)} h uninterrupted`) : ""}</p></div><button class="link" data-action="edit-entry" data-id="${e.id}">Edit sleep</button></div>`).join("") : '<p class="small muted">Log naps and that night’s sleep under this rest day, including night sleep after midnight.</p>'}${verificationFooter("sleep")}</section>`;
}
function sleepInsights() {
  const series = (key, goal, label) =>
    chart(
      Object.entries(state.insights.daily)
        .slice(-14)
        .map(([day, v]) => ({
          label: day,
          short: dateLabel(day, { day: "numeric" }),
          value:
            !v.sleep ||
            (key === "night_continuous" && !v.sleep.continuity_recorded)
              ? null
              : v.sleep[key],
        })),
      { goal, unit: "h", label, line: true },
    );
  return `<section class="card section-space" aria-label="Sleep insights"><div class="card-head"><div><h2>Your sleep rhythm</h2><p>Naps and that night’s sleep belong to the same rest day · last 14 days</p></div><button class="link" data-page="goals">Set sleep targets ↗</button></div><div class="sleep-insight-grid"><div><h3>Total rest · ${n(state.profile.sleep_goal)} h/day</h3>${series("hours", state.profile.sleep_goal, "Daily total rest hours")}</div><div><h3>Night sleep · ${n(state.profile.night_hours_goal)} h/night</h3>${series("night_hours", state.profile.night_hours_goal, "Total night sleep hours")}</div><div><h3>Uninterrupted stretch · ${n(state.profile.night_sleep_goal)} h personal goal</h3>${series("night_continuous", state.profile.night_sleep_goal, "Longest uninterrupted night stretch")}</div></div><p class="muscle-note">Consistency uses total rest and total night sleep. Brief wake-ups do not remove your night hours. Your uninterrupted-stretch goal is tracked separately, with no score penalty. Unknown continuity stays unrecorded.</p></section>`;
}

let activeAiPreview = null;
function reconcileAiPreview() {
  if (activeAiPreview && !state.drafts.some((draft) => draft.id === activeAiPreview.draft_id))
    activeAiPreview = null;
}
function journalEntries() {
  if (!activeAiPreview || activeAiPreview.date !== journalDate)
    return state.entries;
  const updated = new Map(
    activeAiPreview.entries.map((entry) => [entry.id, entry]),
  );
  return [
    ...state.entries.filter((entry) => !updated.has(entry.id)),
    ...updated.values(),
  ];
}
function dayPlan() {
  const plans = journalEntries().filter(
    (entry) => entry.kind === "plan" && entry.date === journalDate,
  );
  const hasWorkout = state.entries.some(
    (entry) => entry.kind === "workout" && entry.date === journalDate,
  );
  return plans
    .map(
      (plan) =>
        `<details class="day-plan" ${hasWorkout ? "" : "open"}><summary><span><strong>Planned exercises</strong><small>${plan.exercises.length} exercise${plan.exercises.length === 1 ? "" : "s"}</small></span><svg class="plan-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary><div class="day-plan-content">${state.entries.some((e) => e.id === plan.id) ? `<div class="actions">${button("Edit plan", "edit-entry", "soft", `data-id="${plan.id}"`)}</div>` : ""}<ul>${plan.exercises.map((ex) => `<li>${esc(byId[ex.exercise_id]?.name || ex.exercise_id)}</li>`).join("")}</ul><p class="small muted">Intentions only. Log what you actually do separately.</p></div></details>`,
    )
    .join("");
}
function previewEntryDetails(entry) {
  let summary = "";
  if (entry.kind === "workout" || entry.kind === "plan")
    summary = entry.exercises
      .map(
        (ex) =>
          `${byId[ex.exercise_id]?.name || ex.exercise_id}${ex.sets ? ": " + ex.sets.map((set) => (set.seconds ? `${set.seconds} sec${set.weight ? " + " + set.weight + " kg" : ""}` : `${set.weight ? set.weight + " kg" : "Bodyweight"} × ${set.reps} reps`)).join("; ") : ""}`,
      )
      .join("\n");
  else if (entry.kind === "meal")
    summary = [
      ...(entry.items || []).map(
        (item) =>
          `${item.name} (${item.portion}): ≈${n(item.protein)} g protein${item.notes ? " · " + item.notes : ""}`,
      ),
      `${entry.items?.length ? "Total" : entry.description} · ${n(entry.protein)} g protein${entry.low != null && entry.high != null ? ` (estimate ${n(entry.low)}–${n(entry.high)} g)` : ""}`,
    ].join("\n");
  else if (entry.kind === "supplement" || entry.kind === "creatine")
    summary = `${entry.name} · ${n(entry.amount)} ${entry.unit}`;
  else if (entry.kind === "sleep")
    summary = `${entry.period} sleep · ${n(entry.hours)} hours${entry.continuous_hours != null ? ` · ${n(entry.continuous_hours)} hours uninterrupted` : ""}`;
  else if (entry.kind === "body")
    summary = `Body weight · ${n(entry.weight_kg)} kg`;
  return `<div class="preview-detail"><strong>${esc(sessionTitle(entry.date))} · ${entry.kind === "meal" ? "Food" : entry.kind === "body" ? "Body measurement" : esc(entry.kind)}</strong><p>${esc(summary)}</p>${entry.notes ? `<p class="small muted">${esc(entry.notes)}</p>` : ""}</div>`;
}
function previewMatches(entry, kind) {
  const category = GoalTracking.isCreatine(entry) ? "creatine" : entry.kind;
  return category === kind || (kind === "workout" && category === "plan");
}
function verificationFooter(kind) {
  if (activeAiPreview?.date === journalDate) {
    const entries = activeAiPreview.entries.filter((entry) =>
      previewMatches(entry, kind),
    );
    if (!entries.length) return "";
    const all = activeAiPreview.entries.length,
      multiple = all > entries.length;
    return `<section class="ai-preview-verification" role="region" aria-label="Verify AI ${kind} entry"><h3>Verify this ${kind === "meal" ? "food" : kind} preview</h3>${activeAiPreview.summary ? `<p class="preview-amount-summary">${esc(activeAiPreview.summary)}</p>` : ""}<p>Not saved yet. ${multiple ? `This batch contains ${all} entries across the day; approval saves all of them.` : "Check the entries above, then approve or suggest changes."}</p><details><summary>Review proposed details</summary>${entries.map(previewEntryDetails).join("")}</details><div class="actions">${button(multiple ? `Approve all ${all} entries` : "Approve & save", "approve-preview", "primary", `data-id="${activeAiPreview.draft_id}"`)}${button("Suggest changes", "change-preview", "soft", `data-id="${activeAiPreview.draft_id}"`)}${button(multiple ? "Revert all previews" : "Revert preview", "revert-preview", "secondary", `data-id="${activeAiPreview.draft_id}"`)}</div></section>`;
  }
  const pending = state.drafts.filter((draft) => {
    const entries =
      draft.kind === "batch"
        ? draft.data.entries.map((e) => ({ ...e.data, kind: e.kind }))
        : [{ ...draft.data, kind: draft.kind }];
    return entries.some(
      (e) => e.date === journalDate && previewMatches(e, kind),
    );
  });
  return pending.length
    ? `<section class="ai-preview-verification"><h3>AI preview awaiting verification</h3>${pending.map((draft) => draftHtml(draft)).join("")}</section>`
    : "";
}
async function showAiPreview(id, summary = "") {
  activeAiPreview = await api("draft-preview", { id });
  activeAiPreview.summary =
    summary ||
    state.messages?.findLast((message) => message.draft?.id === id)
      ?.preview_summary ||
    "";
  journalDate = activeAiPreview.date;
  await closeModal();
  await refresh(false);
  location.hash = "track";
  render();
  $(".ai-preview-verification")
    ?.closest(".journal-panel")
    ?.scrollIntoView({ block: "start" });
}
function openAiLogChooser() {
  const choices = [
    ["workout", "Workout", "Exercises, sets, reps or time", "workouts"],
    ["meal", "Food & protein", "Describe your meal and portions", "nutrition"],
    ["creatine", "Creatine", "Log your intake in grams", "drop"],
    [
      "supplement",
      "Supplements",
      "Vitamins and your other supplements",
      "drop",
    ],
    ["sleep", "Sleep", "Night sleep or a nap", "sleep"],
    ["any", "A mixed log", "Log several parts of your day together", "coach"],
  ];
  modal(
    "What would you like to log?",
    `${sessionTitle(journalDate)} · Choose a type, then add your details in chat.`,
    `<div class="ai-log-choices">${choices.map(([kind, title, hint, symbol]) => `<button type="button" class="coach-starter ai-log-choice" data-action="ai-log" data-kind="${kind}">${icon(symbol)}<span><strong>${title}</strong><small>${hint}</small></span>${icon("arrow")}</button>`).join("")}</div>`,
  );
}
async function openAiLog(kind = "any", revisionId = "") {
  const dateInput = $("#entry-date");
  if (dateInput?.value) journalDate = dateInput.value;
  if (revisionId) {
    const draft = state.drafts?.find((item) => item.id === revisionId);
    const data =
      draft?.kind === "batch" ? draft.data.entries[0]?.data : draft?.data;
    if (data?.date) journalDate = data.date;
  }
  await closeModal();
  const prompts = {
    workout: `Log my workout for ${journalDate}. Keep every exercise and set; ask me if anything is unclear. Here is what I did:\n`,
    meal: `Log my food for ${journalDate}. Estimate protein from my meal and portions, ask if needed, and prepare a preview for approval. I ate:\n`,
    creatine: `Log my creatine for ${journalDate}. Ask if the amount in grams is unclear, then prepare a preview for approval. I took:\n`,
    supplement: `Log my supplements for ${journalDate}. Use the amount and unit I give, or ask me to clarify. I took:\n`,
    sleep: `Log my sleep for rest day ${journalDate}. Ask for any essential missing information. I slept:\n`,
    body: `Log my body weight for ${journalDate}. My weight in kg is: `,
    any: `Prepare a log for ${journalDate}. Here is what I did or consumed:\n`,
  };
  prepareCoachMessage(
    revisionId
      ? `Suggest changes to my pending preview for ${journalDate}, preserving the other entries. Change: `
      : prompts[kind] || prompts.any,
  );
  chatLoggingKind = kind;
  chatRevisionId = revisionId || null;
  location.hash = "coach";
  render();
  $("#chat-input")?.focus();
  if (!state.coach_consent?.accepted)
    toast("Accept the sharing agreement once to use AI logging.");
}

function drawPlan(preservePosition = true) {
  const f = workoutForm;
  modal(
    sessionTitle(f.date),
    "Plan only the exercises you intend to do. Record actual sets, reps, weights or time after training.",
    `<form id="workout-form">${field("Session date", "date", f.date, "date", "required")}<div class="actions">${button("Plan this session with AI", "ask-plan", "soft")}</div><div class="picker section-space">${usualPicker()}<label for="picker-search">Choose exercises</label><input id="picker-search" placeholder="Search exercises" autocomplete="off"><div id="picker-results" class="picker-results">${pickerResults("")}</div></div><ul class="plan-exercises">${f.exercises.map((ex, i) => `<li><img src="${image(ex.exercise_id)}" alt=""><strong>${esc(byId[ex.exercise_id].name)}</strong><button type="button" class="remove" data-action="remove-exercise" data-index="${i}" aria-label="Remove ${esc(byId[ex.exercise_id].name)}">×</button></li>`).join("")}</ul>${entryFooter(f.id, formDraft)}</form>`,
    "",
    preservePosition,
  );
}

function dayBodyMap(workouts) {
  if (!workouts.length) return "";
  const report = BodyMap.summarize(workouts, byId, journalEntries(), {
    end: journalDate,
    mode: "day",
  });
  return BodyMap.render(report, {
    id: "overview-body-map",
    title: "This workout, on your body",
    subtitle: `${sessionTitle(journalDate)} · Hover, tap or focus a body area to explore.`,
    preview: activeAiPreview?.entries.some(
      (e) => e.kind === "workout" && e.date === journalDate,
    ),
  });
}
function insightsBodyMapInner() {
  const day = bodyMapDate || journalDate || state.today;
  const range = BodyMap.period(day, bodyMapMode);
  const workouts = state.entries.filter(
    (e) =>
      e.kind === "workout" &&
      e.date >= range.start &&
      e.date <= range.end &&
      e.date <= state.today,
  );
  const report = BodyMap.summarize(
    workouts,
    byId,
    state.entries.filter((e) => e.date <= state.today),
    {
      end: range.end,
      mode: bodyMapMode,
    },
  );
  const label =
    bodyMapMode === "week"
      ? `${dateLabel(range.start)} – ${dateLabel(range.end)} · Monday–Sunday`
      : sessionTitle(day);
  const controls = `<div class="body-map-controls"><div class="body-map-period" role="group" aria-label="Body map timeframe">${["day", "week"].map((mode) => `<button class="btn ${bodyMapMode === mode ? "soft" : "secondary"}" data-action="body-map-range" data-mode="${mode}" aria-pressed="${bodyMapMode === mode}">${mode === "day" ? "Day" : "Week"}</button>`).join("")}</div><label for="body-map-date">Date<input id="body-map-date" aria-label="Body map date" type="date" min="1900-01-01" max="2050-12-31" required value="${day}"></label></div>`;
  return BodyMap.render(report, {
    id: "insights-muscle-map",
    title: "Your training footprint",
    subtitle: `${label} · ${report.sessions} workout ${report.sessions === 1 ? "day" : "days"}${workouts.length ? "" : " · No workouts recorded"}`,
    controls,
  });
}
function insightsBodyMap() {
  return `<div id="insights-body-map" class="section-space">${insightsBodyMapInner()}</div>`;
}
function dailyJournal() {
  const d = dayEntries();
  return `<section class="card daily-journal" aria-label="Daily workout and nutrition journal"><div class="card-head journal-heading"><div><h2>${esc(sessionTitle(journalDate))}</h2></div><div class="journal-tools"><div class="actions journal-date-controls">${button("←", "journal-prev", "secondary", 'aria-label="Previous journal day"')}<label class="journal-date-label" for="journal-date">Journal date<input id="journal-date" type="date" min="1900-01-01" max="2050-12-31" required value="${journalDate}" aria-label="Journal date"></label>${button("→", "journal-next", "secondary", 'aria-label="Next journal day"')}${button("Today", "journal-today", "soft")}</div>${button(icon("coach") + " Log using AI", "ai-log-chooser")}</div></div><div class="grid equal"><div class="journal-panel"><div class="card-head"><div><h3>Your workout</h3><p>${d.workouts.length} session${d.workouts.length === 1 ? "" : "s"} · ${d.workouts.reduce((n, e) => n + e.exercises.reduce((s, x) => s + x.sets.length, 0), 0)} sets</p></div><div class="actions">${button(icon("plus") + (d.workouts.length ? " Edit workout" : " Log workout"), d.workouts.length ? "edit-entry" : "new-workout", "primary", d.workouts.length ? `data-id="${d.workouts[0].id}"` : "")}</div></div>${dayPlan()}${d.workouts.length ? d.workouts.map(dayWorkout).join("") : empty("Make room for movement", "Your workout for this day will appear here.")}${verificationFooter("workout")}</div><div class="journal-side"><section class="journal-panel journal-creatine" aria-label="Creatine tracking"><div class="card-head"><div><h3>Creatine</h3><p>${n(d.creatine)} g logged</p></div>${button(icon("plus") + " Log creatine", "new-creatine")}</div>${d.creatineEntries.length ? d.creatineEntries.map((e) => `<div class="list-row"><span class="row-icon">${icon("drop")}</span><div class="row-main">${n(e.amount)} g${e.notes ? ` · ${esc(e.notes)}` : ""}</div><button class="link" data-action="edit-entry" data-id="${e.id}">Edit</button></div>`).join("") : '<p class="small muted">No creatine logged for this day.</p>'}${verificationFooter("creatine")}</section><section class="journal-panel journal-supplements" aria-label="Supplement tracking"><div class="card-head"><h3>Supplements</h3><div class="actions">${button(icon("plus") + " Log supplement", "new-supplement")}</div></div>${d.supplements.length ? d.supplements.map((e) => `<div class="list-row"><div class="row-main">${esc(e.name)} · ${n(e.amount)} ${esc(e.unit)}</div><button class="link" data-action="edit-entry" data-id="${e.id}">Edit</button></div>`).join("") : '<p class="small muted">No supplements logged for this day.</p>'}${verificationFooter("supplement")}</section><div class="journal-panel journal-food"><div class="card-head"><div><h3>Protein</h3><p>${n(d.protein)} g protein</p></div><div class="actions">${button(icon("plus") + " Log food", "new-meal")}</div></div>${d.meals.length ? d.meals.map((e) => `<div class="list-row"><span class="row-icon">${icon("nutrition")}</span><div class="row-main"><h3>${esc(e.description)}</h3><p>${activeAiPreview?.entries.some((entry) => entry.id === e.id) ? "AI preview · awaiting approval" : e.source === "ai" ? "Approved AI estimate" : "Manually logged"}</p></div><strong>${n(e.protein)} <small class="muted">g</small></strong><button class="link" data-action="edit-entry" data-id="${e.id}">Edit</button></div>`).join("") : empty("What fueled this day?", "Add food here without leaving your workout journal.")}${verificationFooter("meal")}</div>${sleepJournal()}${
    activeAiPreview?.entries.some(
      (e) => e.kind === "body" && e.date === journalDate,
    )
      ? `<div class="journal-panel">${activeAiPreview.entries
          .filter((e) => e.kind === "body")
          .map(previewEntryDetails)
          .join("")}${verificationFooter("body")}</div>`
      : ""
  }</div></div>${dayBodyMap(d.workouts)}</section>`;
}
function dashboardScoreTrend() {
  const series = (state.insights.consistency_trend || []).map((p) => ({
    label: p.date,
    short: dateLabel(p.date),
    value: p.overall,
  }));
  const known = series.filter((p) => p.value != null),
    delta = known.length > 1 ? known.at(-1).value - known[0].value : null;
  return `<section class="card dashboard-trend section-space"><div class="card-head"><div><div class="eyebrow">THE LONG GAME</div><h2>Your consistency, over time</h2><p>${delta === null ? "Your trend starts with your first logs." : `${delta >= 0 ? "+" : ""}${n(delta)} percentage points since ${dateLabel(known[0].label)}`}</p></div></div>${known.length ? chart(series, { unit: "%", line: true, ceiling: 100, label: "Overall consistency over time", height: 190 }) : empty("Your first point starts here", "Track your day to start your consistency trend.")}<p class="dashboard-note">Based on saved logs and your current goals. Past points are recalculated when goals or records change.</p></section>`;
}
function activityDayHtml(d, label) {
  if (d.outsideMonth)
    return '<span class="activity-spacer" aria-hidden="true"></span>';
  return `<button class="activity-day ${d.tone} ${d.day === state.today ? "is-today" : ""}" data-action="activity-day" data-date="${d.day}" aria-label="${dateLabel(d.day, { month: "long", day: "numeric", year: "numeric" })}: ${esc(label)} · ${esc(d.note)}. Open in Track" title="${esc(d.note)}"><span>${d.number}</span><small>${dashboardMetric === "workout" ? (d.logged ? "✓" : "·") : n(d.ratio * 100) + "%"}</small></button>`;
}
function weeklyScoreHtml(week) {
  const range = `${dateLabel(week.start, { month: "short", day: "numeric" })} – ${dateLabel(week.end, { month: "short", day: "numeric" })}`;
  const value = week.percent == null ? "—" : `${n(week.percent)}%`;
  return `<div class="activity-day weekly-score ${week.tone}" role="group" tabindex="0" data-week-start="${week.start}" aria-label="Weekly score ${esc(range)}: ${value}. ${esc(week.note)}" title="${esc(range + ": " + week.note)}"><strong>${value}</strong></div>`;
}
function activityCalendarInner() {
  const month = dashboardMonth || state.today.slice(0, 7);
  const data = Dashboard.calendar(
    state.entries,
    state.profile,
    month,
    dashboardMetric,
    state.today,
  );
  const label = {
    workout: "Gym days",
    protein: "Protein",
    creatine: "Creatine",
    supplements: "Supplements",
    sleep: "Sleep",
  }[dashboardMetric];
  return `<div class="card-head"><div><div class="eyebrow">SMALL STEPS, EVERY DAY</div><h2>Your activity calendar</h2></div><label class="sr-only" for="activity-metric">Calendar metric</label><select id="activity-metric" aria-label="Calendar metric">${Object.entries(
    {
      workout: "Gym days",
      protein: "Protein goal",
      creatine: "Creatine goal",
      supplements: "Supplements",
      sleep: "Sleep goals",
    },
  )
    .map(
      ([key, title]) =>
        `<option value="${key}" ${dashboardMetric === key ? "selected" : ""}>${title}</option>`,
    )
    .join(
      "",
    )}</select></div><div class="activity-month-controls">${button("←", "activity-prev", "secondary", 'aria-label="Previous activity month"')}<input id="activity-month" aria-label="Activity month" type="month" min="1900-01" max="2050-12" required value="${month}">${button("→", "activity-next", "secondary", 'aria-label="Next activity month"')}</div><div class="activity-weekdays">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Weekly score"].map((d) => `<span>${d}</span>`).join("")}</div><div class="activity-days">${data.weeks.map((w) => w.days.map((d) => activityDayHtml(d, label)).join("") + weeklyScoreHtml(w)).join("")}</div><div class="activity-legend">${dashboardMetric === "supplements" ? '<span><i class="building"></i>Weekly progress</span><span><i class="met"></i>90%+ of weekly targets</span>' : '<span><i class="unlogged"></i>No log / rest</span><span><i class="critical"></i>Below 25%</span><span><i class="low"></i>25–49%</span><span><i class="mid"></i>50–64%</span><span><i class="partial"></i>65–79%</span><span><i class="near"></i>80–94%</span><span><i class="met"></i>95%+</span>'}</div><p class="dashboard-note">${data.loggedDays} ${label.toLowerCase()} ${dashboardMetric === "workout" ? "" : "days "}logged this month. Select a day to open Track.${dashboardMetric === "supplements" ? " Days show cumulative weekly target completion. Weeks turn green at 90%." : dashboardMetric !== "workout" ? " Weekly score uses all seven days; missing and future days count as zero." : " Weekly score compares gym days with your weekly target."} Weeks run Monday–Sunday, including days in adjacent months.</p>`;
}
function updateActivityCalendar() {
  $("#dashboard-activity").innerHTML = activityCalendarInner();
}
function supplementUnitLabel(unit, amount) {
  const labels = {
    days: ["day taken", "days taken"],
    doses: ["dose", "doses"],
    tablet: ["tablet", "tablets"],
    capsule: ["capsule", "capsules"],
    softgel: ["softgel", "softgels"],
    serving: ["serving", "servings"],
    scoop: ["scoop", "scoops"],
    drop: ["drop", "drops"],
  };
  return labels[unit]?.[amount === 1 ? 0 : 1] || unit;
}
function reviewWeekControls(prefix) {
  const reference = reviewDate || state.today;
  const week = GoalTracking.windowFor({ period: 1, unit: "week" }, reference);
  return `<div class="review-week-controls" role="group" aria-label="Review week for ${prefix === "overview-week" ? "weekly goals" : "intake"}">${button("←", "review-week-prev", "secondary", `data-review="${prefix}" aria-label="Previous week for ${prefix}"`)}<label for="${prefix}-date">Review date<input id="${prefix}-date" class="review-date" type="date" required min="1900-01-01" max="${state.today}" value="${reference}" aria-label="Review date for ${prefix}"></label>${button("→", "review-week-next", "secondary", `data-review="${prefix}" aria-label="Next week for ${prefix}" ${week.end >= state.today ? "disabled" : ""}`)}${button("This week", "review-week-today", "soft", `data-review="${prefix}"`)}</div>`;
}
function updateReviewPanels(focusSelector) {
  const weekly = $("#overview-weekly-goals");
  if (weekly) weekly.outerHTML = weeklyGoalsPanel();
  for (const panel of document.querySelectorAll(".nutrition-metrics")) {
    panel.outerHTML = nutritionMetrics(panel.id);
  }
  if (focusSelector) queueMicrotask(() => $(focusSelector)?.focus());
}
function weeklyGoalsPanel() {
  const reference = reviewDate || state.today;
  const week = Dashboard.weeklySupplements(
    state.entries,
    state.profile,
    reference,
    state.today,
  );
  const primary = Dashboard.weeklyTargets(
    state.entries,
    state.profile,
    reference,
    state.today,
  );
  const supplements = week.rows.filter(
    (r) => r.name.toLowerCase() !== "creatine",
  );
  const primaryCards = primary.rows
    .map(
      (row) =>
        `<article class="weekly-supplement ${row.percent != null && row.percent >= 100 - 1e-9 ? "is-achieved" : ""}"><div class="weekly-supplement-heading"><h3>${row.name}</h3><span class="supplement-week-status">${row.percent == null ? "No target" : `${n(row.percent)}%`}</span></div><div class="weekly-supplement-amount"><strong>${n(row.value)}</strong><span>/ ${row.target == null ? "—" : n(row.target)} ${row.measure}</span></div>${row.percent != null ? `<div class="supplement-week-meter" role="progressbar" aria-label="${row.name} weekly target" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(Math.min(100, row.percent))}"><span style="width:${Math.min(100, row.percent)}%"></span></div><p class="supplement-week-remaining">${n(row.remaining)} ${row.measure === "days" && row.remaining === 1 ? "day" : row.measure} remaining</p>` : ""}</article>`,
    )
    .join("");
  const supplementCards = supplements
    .map((row) => {
      const hasTarget = row.target !== null;
      const consumed =
        row.consumed
          .map(
            (item) =>
              `${n(item.amount)} ${supplementUnitLabel(item.unit, item.amount)}`,
          )
          .join(" + ") || "0 logged";
      return `<article class="weekly-supplement ${row.achieved ? "is-achieved" : ""}"><div class="weekly-supplement-heading"><h3>${esc(row.name)}</h3><span class="supplement-week-status">${hasTarget ? `${n((row.value / row.target) * 100)}%` : "No target"}</span></div>${hasTarget ? `<div class="weekly-supplement-amount"><strong>${n(row.value)}</strong><span>/ ${n(row.target)} ${esc(supplementUnitLabel(row.goal.measure, row.target))}</span></div><div class="supplement-week-meter" role="progressbar" aria-label="${esc(row.name)} weekly target" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(row.percent)}"><span style="width:${row.percent}%"></span></div><p class="supplement-week-remaining">${n(row.remaining)} ${esc(supplementUnitLabel(row.goal.measure, row.remaining))} remaining</p>` : ""}<p class="small muted">Logged quantity: ${esc(consumed)}</p>${row.equivalent && hasTarget ? `<p class="small muted">Weekly equivalent of ${n(row.goal.amount)} ${esc(supplementUnitLabel(row.goal.measure, row.goal.amount))} ${goalPeriodText(row.goal)}.</p>` : ""}${row.incompatible ? `<p class="small muted">${row.incompatible} log(s) use a different unit and are excluded from progress.</p>` : ""}</article>`;
    })
    .join("");
  return `<section class="card weekly-supplements section-space" id="overview-weekly-goals" aria-label="Weekly goals progress"><div class="card-head"><div><div class="eyebrow">YOUR WEEKLY ROUTINE</div><h2>Your weekly goals</h2><p>${dateLabel(week.start)} – ${dateLabel(week.end)} · Monday–Sunday</p></div>${reviewWeekControls("overview-week")}<button class="link" data-page="goals">Manage goals ↗</button></div><div class="weekly-supplement-grid">${primaryCards}${supplementCards}</div><p class="dashboard-note">Saved quantities against the full selected week's targets. Missing and future days add zero.</p></section>`;
}
function overview() {
  const workouts = state.entries
    .filter((e) => e.kind === "workout" && e.date <= state.today)
    .sort((a, b) => b.date.localeCompare(a.date));
  const latest = workouts[0];
  const body = latest
    ? BodyMap.render(
        BodyMap.summarize([latest], byId, state.entries, {
          end: latest.date,
          mode: "day",
        }),
        {
          id: "dashboard-body-map",
          title: "Your latest workout, mapped",
          subtitle: `${sessionTitle(latest.date)} · Hover or tap a body area.`,
          controls: button(
            "Open this day ↗",
            "activity-day",
            "secondary",
            `data-date="${latest.date}"`,
          ),
        },
      )
    : "";
  return `<div class="dashboard-grid"><section class="card dashboard-calendar" id="dashboard-activity">${activityCalendarInner()}</section><aside class="card dashboard-habit" aria-label="Training habits"><div class="card-head"><div><h2>The habit of showing up</h2><p>Your training days over the last 12 weeks</p></div></div>${heatmap()}</aside></div><div class="overview-metrics">${consistencyScores(true)}</div>${weeklyGoalsPanel()}${nutritionMetrics("overview-intake")}${body}${dashboardScoreTrend()}`;
}
function track() {
  const history = state.entries
    .filter((e) => e.kind === "workout" || e.kind === "plan")
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, 30);
  return `<div class="track-page-heading"><h1>Track your day</h1>${button("Plan a session", "new-plan", "secondary")}</div>${dailyJournal()}<details class="card track-history"><summary>Recent workouts & session plans</summary><p class="small muted">Your 30 most recent sessions and plans. Use the date picker to open any other day.</p>${history.length ? history.map(workoutRow).join("") : "<p class=muted>Your session history will appear here.</p>"}</details>`;
}
function workouts() {
  const entries = state.entries
    .filter((e) => e.kind === workoutTab)
    .sort((a, b) =>
      workoutTab === "plan"
        ? a.date.localeCompare(b.date)
        : b.date.localeCompare(a.date),
    );
  return (
    head(
      "BUILD YOUR PRACTICE",
      "Every session tells a story.",
      "Record what you did. Make a plan for what comes next.",
      button("Plan a session", "new-plan", "secondary") +
        button(icon("plus") + " Log a workout", "new-workout"),
    ) +
    `<div class="grid cols-2"><div class="card"><div class="tabs"><button class="tab ${workoutTab === "workout" ? "active" : ""}" data-action="workout-tab" data-tab="workout">Workout journal</button><button class="tab ${workoutTab === "plan" ? "active" : ""}" data-action="workout-tab" data-tab="plan">Planned sessions</button></div>${entries.length ? entries.map(workoutRow).join("") : empty(workoutTab === "plan" ? "Make your next session intentional" : "The story starts with one workout", "Choose exercises from the library and add your sets.", button("Add a session", workoutTab === "plan" ? "new-plan" : "new-workout", "soft"))}</div><div><div class="card"><div class="card-head"><div><h2>Showing up, over time</h2><p>Your training days across the last 12 weeks</p></div></div>${heatmap()}<p class="muscle-note">Gym goals count distinct training days. Two workouts in one day still count as one gym day.</p></div><div class="card section-space"><h2>A plan you can actually follow</h2><p class="subtitle">Plan which exercises you intend to do. Record sets, reps, weights or time only when logging the completed workout.</p><div class="section-space">${button("Build a plan with your coach", "ask-plan", "soft")}</div></div></div></div>`
  );
}
function monthCoverage() {
  return GoalTracking.monthCoverage(state.entries, journalDate, state.today);
}
function nutritionMetrics(id = "insights-intake") {
  const reference = reviewDate || state.today;
  return `<section class="card nutrition-metrics section-space" id="${id}" aria-label="Nutrition attainment percentages"><div class="card-head"><div><h2>Your intake, in perspective</h2><p>Quantity and timing, alongside your consistency score.</p></div>${reviewWeekControls(id)}<button class="link" data-page="goals">Adjust targets ↗</button></div><div class="intake-metric-grid">${[
    "protein",
    "creatine",
  ]
    .map((key) => {
      const m = GoalTracking.intakeMetrics(
        state.entries,
        key,
        state.profile.goals[key],
        reference,
        state.today,
        { historyPeriod: "week" },
      );
      const pct = (value) => (value === null ? "—" : `${n(value)}%`);
      return `<article class="intake-metric-card"><h3>${key === "protein" ? "Protein" : "Creatine"}</h3><div class="quantity-pair"><div><span>${m.isDailyGoal ? "Daily attainment" : "Daily reference"} · ${dateLabel(reference)}</span><strong>${pct(m.day.percent)}</strong><p>${n(m.day.value)} / ${n(m.day.target)} g</p></div><div><span>Weekly quantity · ${goalRange(m.week)}</span><strong>${pct(m.week.percent)}</strong><p>${n(m.week.value)} / ${n(m.week.target)} g · ${m.week.open ? "in progress" : "completed"}</p></div><div><span>Monthly quantity · ${goalRange(m.month)}</span><strong>${pct(m.month.percent)}</strong><p>${n(m.month.value)} / ${n(m.month.target)} g · ${m.month.loggedDays}/${m.month.days} days logged</p></div></div><div class="quantity-history"><div><span>Quantity coverage</span><strong>${pct(m.history.percent)}</strong></div><div><span>Average daily attainment</span><strong>${pct(m.history.attainment)}</strong></div><div><span>${m.isDailyGoal ? "Exact daily goal hits" : "Daily reference reached"}</span><strong>${m.history.met} / ${m.history.days}<small> completed days</small></strong></div></div><p class="muscle-note">${m.history.days ? `${goalRange({ start: m.history.start, end: m.history.end })} · ${m.history.loggedDays} logged of ${m.history.days} completed days` : "No completed days in this selected week"}. Today is excluded. ${!m.isDailyGoal ? "Daily and weekly references divide your chosen target across its timeframe; they are guides, not extra goals." : ""}</p></article>`;
    })
    .join(
      "",
    )}</div><p class="muscle-note">Quantity percentages can exceed 100%. Average daily attainment caps each day at 100%, so a high day does not erase a low day. Weekly quantity uses the total logged for that week, allowing intake to vary across days. Missing completed days count as zero logged intake. Your consistency score separately allows for short breaks.</p></section>`;
}

function nutrition() {
  const p = state.profile,
    entries = state.entries.filter((e) => e.date === journalDate),
    meals = entries.filter((e) => e.kind === "meal"),
    supps = entries.filter((e) => e.kind === "supplement");
  return (
    head(
      "FUEL THE WORK YOU PUT IN",
      "Good habits, one meal at a time.",
      "Track protein, creatine and the supplements in your routine.",
      button("Describe a meal to AI", "ask-food", "secondary") +
        button(icon("plus") + " Log food", "new-meal"),
    ) +
    `<div class="toolbar"><label for="nutrition-date">YOUR DAILY JOURNAL</label><input id="nutrition-date" type="date" min="1900-01-01" max="2050-12-31" value="${journalDate}" aria-label="Nutrition date"></div><p class="muscle-note" style="margin-bottom:16px">Choose any day to log or review food and supplements. Overview lets you log these alongside your workout.</p><div class="stats">${intakeGoalStat("protein")}${intakeGoalStat("creatine")}${stat("Food days logged", monthCoverage().foodDays, `/ ${monthCoverage().days}`, `${dateLabel(journalDate, { month: "long", year: "numeric" })} · includes partial days`, "check")}${stat("Creatine days logged", monthCoverage().creatineDays, `/ ${monthCoverage().days}`, `${dateLabel(journalDate, { month: "long", year: "numeric" })} · any amount logged`, "calendar")}</div>${nutritionMetrics()}${consistencyScores()}<div class="grid cols-2"><div class="card"><div class="card-head"><h2>On your plate</h2><span class="pill">${dateLabel(journalDate)}</span></div>${meals.length ? meals.map((e) => `<div class="list-row"><span class="row-icon">${icon("nutrition")}</span><div class="row-main"><h3>${esc(e.description)}</h3><p>${e.source === "ai" ? "AI estimate · approved by you" : "Manually logged"}${e.low !== undefined ? " · range " + n(e.low) + "–" + n(e.high) + " g" : ""}</p></div><strong>${n(e.protein)} <small class="muted">g</small></strong><button class="link" data-action="edit-entry" data-id="${e.id}">Edit</button></div>`).join("") : empty("What fueled you today?", "Add a meal manually or describe what you ate to your AI coach.", button("Add food", "new-meal", "soft"))}</div><div class="card"><div class="card-head"><h2>Your supplement routine</h2><button class="link" data-action="new-supplement">Log supplement +</button></div>${p.supplements
      .map((name) => {
        let logged = supps.filter(
          (e) => e.name.toLowerCase() === name.toLowerCase(),
        );
        return `<div class="list-row"><span class="row-icon">${icon("drop")}</span><div class="row-main"><h3>${esc(name)}</h3><p>${logged.length ? logged.map((e) => n(e.amount) + " " + esc(e.unit)).join(" + ") + " logged" : "No entry on this day"}</p></div>${button(logged.length ? "Add more" : "Log", "quick-supplement", "soft", `data-name="${esc(name)}"`)}</div>`;
      })
      .join(
        "",
      )}${supps.length ? `<details><summary>Review ${supps.length} supplement entries</summary>${supps.map((e) => `<div class="list-row"><div class="row-main">${esc(e.name)} · ${n(e.amount)} ${esc(e.unit)}</div><button class="link" data-action="edit-entry" data-id="${e.id}">Edit</button></div>`).join("")}</details>` : ""}<p class="muscle-note">Targets are personal settings, not prescribed doses. Add supplement names in Settings.</p></div></div><div class="coach-callout">${icon("coach")}<div class="row-main"><h3>“I had two eggs and a bowl of dal…”</h3><p>Your coach can ask about portions, explain its estimate, and draft a food entry for your review.</p></div>${button("Estimate my meal", "ask-food", "secondary")}</div>`
  );
}
function exerciseMatches(q, muscle = "", equipment = "") {
  const words = q
    .toLowerCase()
    .replace(/[-_]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  return catalog.filter((e) => {
    const hay = [
      e.name,
      ...(e.aliases || []),
      ...e.primaryMuscles,
      ...e.secondaryMuscles,
      ...(e.bodyParts || []),
      e.equipment || "",
      e.category,
    ]
      .join(" ")
      .toLowerCase()
      .replace(/[-_]/g, " ");
    return (
      words.every((w) => hay.includes(w)) &&
      (!muscle || (e.bodyParts || []).includes(muscle)) &&
      (!equipment || e.equipment === equipment)
    );
  });
}
function exerciseCards(list) {
  return list
    .map(
      (e) =>
        `<button class="exercise-card" data-action="exercise-detail" data-id="${esc(e.id)}"><img class="exercise-photo" src="${image(e.id)}" alt="${esc(e.name)} ${e.photoNote ? "reference photo" : "demonstration"}" loading="lazy"><div class="exercise-info"><h3>${esc(e.name)}</h3><p>${esc((e.bodyParts || e.primaryMuscles).join(" · "))}</p><p>${esc(e.equipment || "body only")} · ${esc(e.level)}</p>${e.photoNote ? '<span class="pill">REFERENCE PHOTO</span>' : ""}</div></button>`,
    )
    .join("");
}
function libraryResults() {
  const list = exerciseMatches(libraryQuery, libraryMuscle, libraryEquipment);
  const maxPage = Math.max(0, Math.ceil(list.length / 24) - 1);
  libraryPage = Math.min(libraryPage, maxPage);
  return `<p class="small muted" style="margin-bottom:15px">${list.length} exercises · Photos and instructions available offline</p><div class="exercise-grid">${exerciseCards(list.slice(libraryPage * 24, (libraryPage + 1) * 24))}</div>${!list.length ? empty("No matching exercises", "Try another name, muscle group or piece of equipment.") : ""}<div class="pagination">${button("← Previous", "library-prev", "secondary", libraryPage === 0 ? "disabled" : "")}<span>Page ${libraryPage + 1} of ${maxPage + 1}</span>${button("Next →", "library-next", "secondary", libraryPage >= maxPage ? "disabled" : "")}</div>`;
}
function exercises() {
  const muscles = [
      ...new Set(catalog.flatMap((e) => e.bodyParts || [])),
    ].sort(),
    equipment = [
      ...new Set(catalog.map((e) => e.equipment).filter(Boolean)),
    ].sort();
  return (
    head(
      "GET TO KNOW YOUR MOVEMENT",
      "Find your next favorite exercise.",
      `${catalog.length} exercises. Real photos. Clear instructions. A place to start.`,
    ) +
    `<div class="toolbar"><div class="search-wrap">${icon("search")}<input id="exercise-search" placeholder="Search exercises, muscles, equipment…" value="${esc(libraryQuery)}" aria-label="Search exercise library"></div><select id="muscle-filter" aria-label="Filter muscle"><option value="">All muscles</option>${muscles.map((m) => `<option ${libraryMuscle === m ? "selected" : ""}>${esc(m)}</option>`).join("")}</select><select id="equipment-filter" aria-label="Filter equipment"><option value="">All equipment</option>${equipment.map((m) => `<option ${libraryEquipment === m ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></div><div id="library-results">${libraryResults()}</div>`
  );
}
function exerciseRecords() {
  const prs = state.insights.prs,
    counts = Object.fromEntries(
      WorkoutHistory.usualExercises(state.entries, state.today).map((item) => [
        item.id,
        item.count,
      ]),
    );
  const allIds = Object.keys(prs).sort(
    (a, b) =>
      (counts[b] || 0) - (counts[a] || 0) ||
      (byId[a]?.name || a).localeCompare(byId[b]?.name || b),
  );
  const areas = (id) => byId[id]?.bodyParts || byId[id]?.primaryMuscles || [];
  const parts = [...new Set(allIds.flatMap(areas))].sort();
  const ids = (recordSearchQuery && recordRankedIds ? recordRankedIds.filter(id => allIds.includes(id)) : allIds).filter(
    (id) =>
      (!recordExercise || recordExercise === id) &&
      (!recordBodyPart || areas(id).includes(recordBodyPart)),
  );
  return `<section class="card records-card" aria-label="All exercise records"><div class="card-head records-heading"><div><h2>Your exercises & personal records</h2><p>Every tracked exercise · most trained first · all time</p></div><div class="pr-filters"><div class="pr-search-field"><label for="pr-exercise-filter">Exercise<input type="search" id="pr-exercise-filter" maxlength="200" aria-label="Filter PRs by exercise" role="combobox" aria-autocomplete="list" aria-controls="pr-exercise-options" aria-expanded="${recordSuggestionsOpen}" autocomplete="off" placeholder="Type an exercise, muscle or equipment…" value="${esc(recordSearchQuery)}"></label><div id="pr-exercise-options" class="pr-search-options" role="listbox" ${recordSuggestionsOpen ? "" : "hidden"}>${ids.slice(0, 8).map(id => `<button type="button" role="option" aria-selected="${recordExercise === id}" data-action="filter-pr-exercise" data-id="${esc(id)}"><img src="${image(id)}" alt=""><span>${esc(byId[id]?.name || id)}</span></button>`).join("") || '<p class="small muted">No tracked matches yet.</p>'}</div></div><label>Body part<select id="pr-body-filter" aria-label="Filter PRs by body part"><option value="">All body parts</option>${parts.map((part) => `<option value="${esc(part)}" ${recordBodyPart === part ? "selected" : ""}>${esc(part)}</option>`).join("")}</select></label><span class="pill" role="status">${ids.length}${ids.length !== allIds.length ? ` / ${allIds.length}` : ""} EXERCISES</span></div></div>${
    ids.length
      ? `<div class="pr-card-scroll" role="region" aria-label="Exercise PR cards" tabindex="0"><div class="pr-card-grid">${ids
          .map((id) => {
            const pr = prs[id];
            const timed = !pr.reps && pr.seconds;
            const main = timed
              ? `${n(pr.seconds)}<small> sec</small>`
              : pr.weight
                ? `${n(pr.weight)}<small> kg × </small>${n(pr.reps)}<small> reps</small>`
                : `${n(pr.reps)}<small> reps</small>`;
            return `<article class="pr-kpi"><div class="pr-kpi-head"><img src="${image(id)}" alt="${esc(byId[id]?.name || id)}" loading="lazy"><h3>${esc(byId[id]?.name || id)}</h3></div><span class="pr-kpi-label">${timed ? "Longest hold" : pr.weight ? "Best logged load" : "Bodyweight PR"}</span><div class="pr-kpi-value">${main}</div>${!timed && pr.seconds ? `<p class="small muted">Longest hold · ${n(pr.seconds)} sec</p>` : ""}<p class="pr-kpi-meta">${counts[id] || 0} session${counts[id] === 1 ? "" : "s"} · ${esc(sessionTitle(timed ? pr.seconds_date || pr.date : pr.date))}</p><div class="records-actions"><button class="link" data-action="select-pr" data-id="${id}" aria-label="View ${esc(byId[id]?.name || id)} PR trend">Trend ↗</button><button class="link" data-action="exercise-history" data-id="${id}" aria-label="Edit ${esc(byId[id]?.name || id)} logs">Edit logs</button></div></article>`;
          })
          .join(
            "",
          )}</div></div><p class="muscle-note">Scroll to explore every exercise. PRs use your saved sets; open a trend for the monthly history.</p>`
      : empty(
          allIds.length
            ? "No PRs match these filters"
            : "Your records start with a session",
          allIds.length
            ? "Choose another exercise or body part, or clear the filters."
            : "Log your usual exercises to build your PR collection.",
          allIds.length
            ? button("Clear filters", "clear-pr-filters", "soft")
            : "",
        )
  }</section>`;
}
function updateExerciseRecords(focusId) {
  const previous = focusId ? $(`#${focusId}`) : null;
  const selection = previous?.type === "search" ? [previous.selectionStart, previous.selectionEnd] : null;
  const section = $(".records-card");
  if (section) section.outerHTML = exerciseRecords();
  if (focusId) {
    const control = $(`#${focusId}`);
    control?.focus();
    if (control?.type === "search" && selection) control.setSelectionRange?.(...selection);
  }
}
async function rankedExerciseSearch(query, { tracked = false, bodyPart = "" } = {}) {
  const key = JSON.stringify([query.trim().toLowerCase(), tracked, bodyPart]);
  if (exerciseSearchCache.has(key)) return exerciseSearchCache.get(key);
  const params = new URLSearchParams({ q: query.trim(), limit: tracked ? "100" : "30", tracked: tracked ? "1" : "0", body_part: bodyPart });
  const result = await api("exercise-search?" + params);
  const ids = result.items.map(item => item.id).filter(id => byId[id]);
  if (exerciseSearchCache.size >= 100) exerciseSearchCache.clear();
  exerciseSearchCache.set(key, ids);
  return ids;
}
function scheduleExerciseSearch(target, query) {
  clearTimeout(exerciseSearchTimers[target]);
  const version = (exerciseSearchVersions[target] || 0) + 1;
  exerciseSearchVersions[target] = version;
  if (!query.trim()) return;
  exerciseSearchTimers[target] = setTimeout(async () => {
    try {
      const ids = await rankedExerciseSearch(query, { tracked: target === "records", bodyPart: target === "records" ? recordBodyPart : "" });
      if (exerciseSearchVersions[target] !== version) return;
      if (target === "records" && $(".records-card") && recordSearchQuery === query) {
        recordRankedIds = ids;
        updateExerciseRecords(document.activeElement?.id === "pr-exercise-filter" ? "pr-exercise-filter" : null);
      } else if (target === "picker" && $("#picker-search")?.value === query) {
        $("#picker-results").innerHTML = pickerResults(query, ids.map(id => byId[id]));
      }
    } catch { /* Existing local keyword results stay available during an index restart. */ }
  }, 220);
}
function searchExerciseRecords(query) {
  recordSearchQuery = query;
  recordExercise = "";
  recordRankedIds = query.trim() ? exerciseMatches(query).map(ex => ex.id) : null;
  recordSuggestionsOpen = Boolean(query.trim());
  updateExerciseRecords("pr-exercise-filter");
  scheduleExerciseSearch("records", query);
}
function resetDialog() {
  modal(
    "Reset your journal",
    "Start again with an empty journal. This is permanent unless you restore your own backup.",
    `<form id="reset-form" class="reset-form"><p class="reset-warning">Clears all workouts, plans, food, supplements, body measurements, PR history, chat, pending drafts and your personal profile/goals. The exercise library stays available. No data is cleared until you type RESET and confirm.</p><div class="actions section-space">${button("Download a backup first", "export", "secondary")}</div><label class="checkbox-label section-space"><input type="checkbox" name="clear_connections"> Also remove locally saved AI connections</label><div class="field section-space"><label for="reset-confirm">Type RESET to confirm</label><input id="reset-confirm" name="confirm" type="text" required pattern="RESET" autocomplete="off" spellcheck="false"></div><div id="form-error" class="error" role="alert"></div><div class="modal-foot">${button("Keep my journal", "close-modal", "secondary")}<button class="btn danger" type="submit">Reset all journal data</button></div></form>`,
  );
}
let selectedBodyPart;
function areaBreakdown(group) {
  const detail = state.insights.area_details?.[group];
  if (!detail)
    return empty(
      "Training detail starts with your logs",
      "Log a workout to explore your body-part focus.",
    );
  const areas = Object.entries(detail.areas).sort((a, b) => b[1] - a[1]),
    max = Math.max(...areas.map((item) => item[1]), 1);
  return `<div class="grid equal"><div>${areas.map(([name, count]) => `<div class="muscle-row"><div class="muscle-top"><span>${esc(name)}</span><span>${count} sets</span></div><div class="muscle-bar"><div style="width:${(count / max) * 100}%;background:#a58bdf"></div></div></div>`).join("")}</div><div>${Object.entries(
    detail.exercises,
  )
    .sort((a, b) => b[1] - a[1])
    .map(
      ([id, count]) =>
        `<div class="list-row"><img class="journal-exercise-photo" src="${image(id)}" alt=""><div class="row-main"><h3>${esc(byId[id].name)}</h3><p>${count} sets · last 28 days</p></div><button class="link" data-action="exercise-history" data-id="${id}">View logs</button></div>`,
    )
    .join("")}</div></div>`;
}
function trainingDetail() {
  const groups = Object.keys(state.insights.body_parts || {}).sort(
    (a, b) => state.insights.body_parts[b] - state.insights.body_parts[a],
  );
  selectedBodyPart = groups.includes(selectedBodyPart)
    ? selectedBodyPart
    : groups[0];
  return `<section class="card records-card" aria-label="Detailed training focus"><div class="card-head"><div><h2>A closer look at your training</h2><p>Movement types and areas within each body part · last 28 days</p></div>${groups.length ? `<select id="body-area-select" aria-label="Body part to explore">${groups.map((group) => `<option ${group === selectedBodyPart ? "selected" : ""}>${esc(group)}</option>`).join("")}</select>` : ""}</div><div id="area-breakdown">${areaBreakdown(selectedBodyPart)}</div><p class="muscle-note">These are exercise classifications, not measured muscle activation. Detailed areas can overlap; Overview counts each body part once per set.</p></section>`;
}
function progress() {
  const s = state.insights,
    ids = Object.keys(s.prs).sort((a, b) =>
      byId[a].name.localeCompare(byId[b].name),
    );
  prId = ids.includes(prId) ? prId : ids[0];
  const pr = s.prs[prId],
    ex = byId[prId];
  let months = [];
  for (let i = 11; i >= 0; i--) {
    let d = dateObj(state.today);
    d.setDate(1);
    d.setMonth(d.getMonth() - i);
    let key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
      val = s.monthly[prId]?.[key];
    let metric = pr?.weight ? "weight" : pr?.reps ? "reps" : "seconds";
    months.push({
      label: key,
      short: d.toLocaleDateString(undefined, { month: "short" }),
      value: val ? val[metric] : null,
    });
  }
  const metric = pr?.weight ? "kg" : pr?.reps ? "reps" : "seconds";
  const body = Object.entries(s.daily)
    .map(([d, v]) => ({ label: d, short: dateLabel(d), value: v.body }))
    .filter((d) => d.value !== null);
  const frequency = Object.entries(s.frequency)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  return (
    head(
      "PROGRESS YOU CAN SEE",
      "Look how far you’re coming.",
      "Find the patterns behind your consistency, strength and nutrition.",
      button("Log body weight", "new-body", "secondary"),
    ) +
    insightsBodyMap() +
    exerciseRecords() +
    trainingDetail() +
    sleepInsights() +
    nutritionMetrics() +
    `<div class="grid cols-2"><div class="card" id="strength-chart-card"><div class="card-head"><div><h2>Your strength, over time</h2><p>Monthly best logged ${metric === "kg" ? "load" : metric} · last 12 months</p></div><span class="pill gold">PERSONAL RECORDS</span></div>${ids.length ? `<select id="pr-select" class="full-width" aria-label="Exercise for PR chart">${ids.map((id) => `<option value="${id}" ${id === prId ? "selected" : ""}>${esc(byId[id].name)}</option>`).join("")}</select><div class="section-space"><strong class="pr-value">${n(pr.weight || pr.reps || pr.seconds)} <small class="muted">${metric}</small></strong><p class="small muted">${pr.weight ? n(pr.reps) + " reps at your best load · " : ""}Best logged · ${dateLabel(metric === "seconds" ? pr.seconds_date || pr.date : pr.date, { month: "short", day: "numeric", year: "numeric" })}</p></div>${chart(months, { unit: metric, line: true, label: ex.name + " monthly personal record" })}${pr.estimated_1rm ? `<p class="muscle-note">Estimated 1RM: ${n(pr.estimated_1rm)} kg (Epley, sets of 1–10 reps). This estimate is separate from your actual best load.</p>` : ""}<p class="muscle-note">Weights are recorded per your chosen convention. Use the same convention for dumbbells and assisted machines. Empty months are gaps.</p>` : empty("Your first PR is ahead of you", "Log sets to see your best loads, reps and monthly changes.")}</div><div class="card"><div class="card-head"><div><h2>Your training balance</h2><p>Body-part sets · last 28 days</p></div></div>${muscles()}<p class="muscle-note">Volume alone does not measure growth. Use this to notice your training emphasis.</p></div></div>` +
    `<div class="grid equal section-space"><div class="card" id="intake-panel">${intakePanel()}</div><div class="card"><div class="card-head"><div><h2>Exercises you come back to</h2><p>Sessions including each exercise · last 28 days</p></div></div>${frequency.length ? frequency.map(([id, count], i) => `<div class="list-row"><span class="pill">0${i + 1}</span><img src="${image(id)}" width="42" height="37" style="object-fit:contain" alt="${esc(byId[id].name)}"><div class="row-main"><h3>${esc(byId[id].name)}</h3><p>${esc((byId[id].bodyParts || byId[id].primaryMuscles).join(", "))}</p></div><strong>${count}<small class="muted"> sessions</small></strong></div>`).join("") : empty("Your favorites will find you", "Your most repeated exercises appear as you log sessions.")}</div></div><div class="section-space"><div class="card"><div class="card-head"><div><h2>Body weight journal</h2><p>Logged measurements · last 12 weeks</p></div>${button("+ Log", "new-body", "soft")}</div>${body.length ? chart(body, { unit: "kg", line: true, label: "Logged body weight" }) : empty("An optional piece of your story", "Add body weight measurements if this is useful for your goals.")}${
      state.entries.some((e) => e.kind === "body")
        ? `<details><summary>View / edit measurements</summary>${state.entries
            .filter((e) => e.kind === "body")
            .map(
              (e) =>
                `<div class="list-row"><div class="row-main">${esc(sessionTitle(e.date))} · ${n(e.weight_kg)} kg</div><button class="link" data-action="edit-entry" data-id="${e.id}">Edit / delete</button></div>`,
            )
            .join("")}</details>`
        : ""
    }</div></div><div class="coach-callout">${icon("coach")}<div class="row-main"><h3>Turn a pattern into a plan.</h3><p>Ask your coach to explain these trends or help you focus the next three months.</p></div>${button("Explore with my coach", "ask-progress", "secondary")}</div>`
  );
}
function intakePanel() {
  const points = Dashboard.intakeSeries(state.entries, intakeMetric, intakePeriod, state.today);
  const range = points.length ? `${dateLabel(points[0].start, { month: "short", day: "numeric", year: "numeric" })} – ${dateLabel(points[points.length - 1].end > state.today ? state.today : points[points.length - 1].end, { month: "short", day: "numeric", year: "numeric" })}` : "No entries yet";
  return `<div class="card-head intake-chart-head"><div><h2>Protein & creatine rhythm</h2><p>${intakePeriod === "weekly" ? "Weekly totals" : "Daily totals"} · ${points.length} recorded ${intakePeriod === "weekly" ? "weeks" : "days"} · ${esc(range)}</p></div><div class="intake-chart-controls"><div class="tabs" role="group" aria-label="Intake chart timeframe">${["daily", "weekly"].map(period => `<button type="button" class="tab ${intakePeriod === period ? "active" : ""}" data-action="intake-period" data-period="${period}" aria-pressed="${intakePeriod === period}">${period === "daily" ? "Daily" : "Weekly"}</button>`).join("")}</div><select id="intake-metric" aria-label="Intake metric"><option value="protein" ${intakeMetric === "protein" ? "selected" : ""}>Protein · g</option><option value="creatine" ${intakeMetric === "creatine" ? "selected" : ""}>Creatine · g</option></select></div></div><div id="intake-chart">${intakeChart(intakeMetric)}</div><p class="muscle-note">${intakePeriod === "weekly" ? "Monday–Sunday totals; the current week is still in progress." : "Each point totals all entries logged for that day."} Only ${intakePeriod === "weekly" ? "weeks" : "days"} with entries are plotted; missing logs do not mean zero intake. Showing the latest 20 recorded ${intakePeriod === "weekly" ? "weeks" : "days"} at most. The dashed line shows your ${intakePeriod === "weekly" ? "weekly" : "daily"} goal reference.</p>`;
}
function intakeChart(metric) {
  const points = Dashboard.intakeSeries(state.entries, metric, intakePeriod, state.today);
  if (!points.length) return empty("No intake entries yet", "Log protein or creatine to see your trend.");
  const data = points.map(point => ({
    value: point.value,
    short: dateLabel(point.start, { month: "short", day: "numeric" }),
    label: intakePeriod === "weekly" ? `${point.start} – ${point.end}${point.end >= state.today && point.start <= state.today ? " (in progress)" : ""}` : point.start,
  }));
  const reference = GoalTracking.intakeMetrics(state.entries, metric, state.profile.goals[metric], state.today, state.today);
  return chart(data, {
    unit: "g",
    line: true,
    goal: intakePeriod === "weekly" ? reference.week.target : reference.day.target,
    label: `${intakePeriod === "weekly" ? "Weekly" : "Daily"} ${metric} intake, latest ${data.length} recorded points`,
  });
}

function papersHtml(papers) {
  return papers
    .map(
      (p) =>
        `<a class="paper" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer"><strong>${esc(p.title)}</strong><span>${p.kind ? esc(p.kind) : esc(p.year) + " · Europe PMC"} ↗</span></a>`,
    )
    .join("");
}
function draftHtml(d, inChat = false) {
  const entries = d.kind === "batch" ? d.data.entries : [{ data: d.data }];
  const incomplete = entries.some(item => item.data.notes?.includes("Needs clarification (not included"));
  return `<div class="draft-card"><strong>Review your preview</strong><p>${d.kind === "batch" ? d.data.entries.length + " proposed entries" : "Proposed " + esc(d.kind)} · not saved yet</p>${inChat ? '<p class="small muted">Review the list above. Tell your coach what to change, or approve when everything looks right.</p>' : ""}<div class="actions">${inChat ? button(d.kind === "batch" ? "Approve & save all" : "Approve & save", "approve-chat-draft", "primary", `data-id="${d.id}" ${incomplete ? 'disabled title="Resolve the highlighted questions before approval"' : ""}`) + button("Suggest changes", "change-preview", "soft", `data-id="${d.id}"`) : ""}${button(inChat ? "View in Track" : "Review in Track", "preview-ai-draft", "soft", `data-id="${d.id}"`)}${button("Revert", "dismiss-draft", "secondary", `data-id="${d.id}"`)}</div></div>`;
}
function agentDetails(message) {
  const a = message.agent;
  if (a.architecture !== "LangGraph") return "";
  return `<details class="agent-details"><summary>How this answer was prepared</summary><p>LangGraph · input budget ${n(a.context_budget_tokens)} tokens per call · ${a.input_token_estimates.length} model calls</p><p>Guides: ${a.skills.map((s) => esc(s.title)).join(" · ")}</p><ul>${a.trace
    .filter((t) => t.node === "tool")
    .map(
      (t) =>
        `<li>${esc(t.tool)} · ${t.ok ? "completed" : "unavailable"}${t.args?.query ? " · " + esc(t.args.query) : ""}${t.args?.expression ? " · " + esc(t.args.expression) + (t.value !== undefined ? " = " + n(t.value) : "") : ""}</li>`,
    )
    .join(
      "",
    )}</ul><p class="small muted">Input estimates: ${a.input_token_estimates.map(n).join(", ")}. Qwen checks the local context budget before generating.</p></details>`;
}
function chatText(text) {
  const inline = (value) => esc(value)
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]\n]+)\]\((https:\/\/[^\s<>]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1 ↗</a>');
  return String(text || "").split(/\n\s*\n/).map(block => {
    const lines = block.split("\n");
    if (lines.every(line => /^\s*\d+\.\s/.test(line)))
      return `<ol>${lines.map(line => `<li>${inline(line.replace(/^\s*\d+\.\s*/, ""))}</li>`).join("")}</ol>`;
    if (lines.every(line => /^\s*[-•]\s/.test(line)))
      return `<ul>${lines.map(line => `<li>${inline(line.replace(/^\s*[-•]\s*/, ""))}</li>`).join("")}</ul>`;
    return `<p>${lines.map(inline).join("<br>")}</p>`;
  }).join("");
}
function messageHtml(m) {
  if (m.role === "user")
    return `<article class="message user" data-message-id="${esc(m.id || m.request_id || "")}"><div class="message-meta">YOU</div><p>${esc(m.text)}</p>${m.status === "pending" ? '<span class="chat-message-state">Sent · awaiting your coach</span>' : m.status === "failed" ? `<div class="chat-message-failure"><span>${esc(m.error || "Could not finish this answer.")}</span><button type="button" class="link" data-action="retry-chat" data-id="${esc(m.id || m.request_id)}">Try again</button></div>` : ""}</article>`;
  const draft = m.draft && state.drafts.find((d) => d.id === m.draft.id);
  return `<div class="message ${m.role === "user" ? "user" : ""}"><div class="message-meta">${m.role === "user" ? "YOU" : esc("YOUR COACH" + (m.provider ? " · " + m.provider : ""))}</div><div class="coach-message-body">${chatText(m.text)}</div>${draft ? draftHtml(draft, true) : ""}${m.approved ? `<div class="actions">${button("View in Track", "view-approved-track", "soft", `data-date="${esc(m.approved.date)}"`)}</div>` : ""}<details class="message-resources" ${!m.draft && !m.papers?.length && !m.citations?.length && !m.notices?.length && m.agent?.architecture !== "LangGraph" ? "hidden" : ""}><summary>Details</summary><div>${m.papers?.length ? `<details><summary>Sources retrieved · ${m.papers.length}</summary>${papersHtml(m.papers)}</details>` : ""}${m.agent ? agentDetails(m) : ""}${
    m.citations?.length
      ? `<div class="cited-sources">${m.citations
          .filter((url) => /^https?:\/\//.test(url))
          .map(
            (url, i) =>
              `<a class="link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Source ${i + 1}${m.cached_citations?.includes(url) ? " · cached guide" : ""} ↗</a>`,
          )
          .join(" · ")}</div>`
      : ""
  }${m.draft && !draft ? '<p class="small muted">Preview approved, replaced or reverted.</p>' : ""}${(m.notices || []).map((v) => `<p class="notice">${esc(v)}</p>`).join("")}</div></details></div>`;
}
function quotaSummary(provider, connections = state.connections) {
  return `Qwen runs locally · ${n(connections.ollama_context_tokens || 8192)} context tokens`;
}
let chatLoggingKind = null,
  chatRevisionId = null;
let chatStage = "Received. Understanding your request…";
let chatResearchMode = false,
  chatComposerDraft = "",
  optimisticChat = null,
  chatPollTimer = null,
  chatPollBusy = false,
  chatThreadSignature = "";
function chatIsBusy() {
  return (
    chatBusy ||
    Boolean(state.chat_status?.busy) ||
    state.messages?.some((message) => message.status === "pending")
  );
}
function chatConsentGate() {
  if (state.coach_consent?.accepted) return "";
  return `<section class="chat-consent-gate" aria-label="Coach sharing agreement"><h3>Before your first chat</h3><p>Your messages and relevant journal details are processed by <strong>Qwen through Ollama on your computer</strong>. Optional Research sends public queries to search services; your journal stays on your computer.</p><p>AI advice and estimates can be wrong and are not medical care. Proposed journal entries still need your approval.</p><form id="coach-consent-form"><label class="checkbox-label"><input type="checkbox" name="agreement" required> I agree to this sharing for future coach messages and understand these limits.</label><button class="btn section-space" type="submit">Agree & start chatting</button><p class="small muted">Remembered on your computer. Review or revoke anytime in Sharing permissions.</p><p id="coach-consent-error" class="error" role="alert"></p></form></section>`;
}
function chatVisibleMessages() {
  const messages = [...state.messages];
  if (
    optimisticChat &&
    !messages.some((m) => m.request_id === optimisticChat.request_id)
  )
    messages.push(optimisticChat);
  return messages;
}
function chatThreadHtml() {
  const messages = chatVisibleMessages();
  return (
    (messages.length
      ? messages.map(messageHtml).join("")
      : `<div class="message"><div class="message-meta">YOUR COACH</div><p>Tell me what you ate, what you’re working toward, or what feels stuck. We can work through it together.</p></div>`) +
    state.drafts
      .filter((d) => !messages.some((m) => m.draft?.id === d.id) && !(state.chat_hidden_drafts || []).includes(d.id))
      .map((draft) => draftHtml(draft))
      .join("") +
    (chatIsBusy()
      ? `<div class="chat-generating" role="status" aria-live="polite"><span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span><span id="chat-generation-status">Your coach is preparing an answer…</span></div>`
      : "")
  );
}
function syncChatThread(forceScroll = false) {
  const thread = $("#chat-thread");
  if (!thread) return;
  const nearBottom =
    thread.scrollHeight - thread.clientHeight - thread.scrollTop < 80;
  const signature = JSON.stringify([
    chatVisibleMessages(),
    state.drafts,
    chatIsBusy(),
  ]);
  if (signature !== chatThreadSignature) {
    const scroll = thread.scrollTop;
    thread.innerHTML = chatThreadHtml();
    chatThreadSignature = signature;
    thread.scrollTop = forceScroll || nearBottom ? thread.scrollHeight : scroll;
  }
  const wait = state.connections.rate_limits?.waiting;
  const seconds = Math.ceil(((wait?.until || 0) * 1000 - Date.now()) / 1000);
  if ($("#chat-generation-status"))
    $("#chat-generation-status").textContent =
      seconds > 0
        ? `Waiting ${seconds}s for provider limits, then continuing your answer…`
        : chatStage;
  const submit = $("#chat-form [type=submit]");
  if (submit) {
    submit.disabled = chatIsBusy() || coachModelBusy;
    submit.innerHTML = chatIsBusy() ? "Generating…" : "Send " + icon("arrow");
  }
  setCoachControlsDisabled(chatIsBusy() || coachModelBusy);
  updateChatVoiceControls();
}
async function refreshChatSnapshot() {
  const snapshot = await api("chat-state");
  state.messages = snapshot.messages;
  state.chat_hidden_drafts = snapshot.chat_hidden_drafts || [];
  state.drafts = snapshot.drafts;
  reconcileAiPreview();
  state.chat_status = snapshot.chat_status;
  state.coach_consent = snapshot.coach_consent;
  state.connections.rate_limits = snapshot.rate_limits;
  if (
    optimisticChat &&
    state.messages.some((m) => m.request_id === optimisticChat.request_id)
  )
    optimisticChat = null;
  syncChatThread();
}
function ensureChatPolling() {
  if (chatPollTimer || !chatIsBusy()) return;
  chatPollTimer = setInterval(async () => {
    if (chatPollBusy) return;
    chatPollBusy = true;
    try {
      await refreshChatSnapshot();
    } catch {
      /* Keep the visible turn while reconnecting. */
    } finally {
      chatPollBusy = false;
      if (!chatIsBusy()) {
        clearInterval(chatPollTimer);
        chatPollTimer = null;
      }
    }
  }, 1200);
}
async function saveCoachAgreement(accepted) {
  state.coach_consent = await api("coach-consent", { accepted, version: 1 });
  await closeModal();
  if ((location.hash || "#overview") === "#coach") render();
}
function coachSharingDialog() {
  modal(
    "Sharing permissions",
    "Your agreement is saved on your computer.",
    `<p>Your agreement covers local Qwen coaching with relevant journal details. Model inference runs on your computer through Ollama. Optional Research sends public queries to search services.</p><p class="section-space">AI guidance can be wrong. Every proposed journal entry still needs your approval.</p><p class="small muted">${state.coach_consent?.accepted ? "Sharing is enabled." : "Sharing is not enabled."}</p><div class="modal-foot">${button("Close", "close-modal", "secondary")}${state.coach_consent?.accepted ? button("Revoke sharing permission", "revoke-coach-consent", "soft", chatIsBusy() ? "disabled" : "") : ""}</div>`,
  );
}

const coachModelLists = { ollama: ["qwen3:8b"] };
function coachProviderLabel() { return "Qwen · Ollama"; }
function pendingCoachConnection() {
  const provider = $("#coach-provider")?.value;
  if (!provider) return false;
  const chosen = $("#coach-model")?.value;
  const model =
    chosen === "__custom__" ? $("#coach-custom-model")?.value.trim() : chosen;
  return (
    provider !== state.connections.provider ||
    model !== state.connections[provider + "_model"]
  );
}
function updateCoachConnectionState() {
  const provider = $("#coach-provider")?.value;
  if (!provider) return;
  const chosen = $("#coach-model")?.value;
  const model =
    chosen === "__custom__" ? $("#coach-custom-model")?.value.trim() : chosen;
  const pending = pendingCoachConnection();
  const apply = $("#coach-apply-connection"),
    preview = $("#coach-switch-preview"),
    cancel = $("#coach-cancel-connection");
  if (apply) {
    apply.textContent = coachModelBusy
      ? "Switching connection…"
      : pending
        ? `Switch to ${coachProviderLabel(provider)}`
        : "Connection active";
    apply.disabled = coachModelBusy || chatIsBusy() || !pending || !model;
  }
  if (preview) {
    preview.hidden = !pending;
    preview.textContent = `Not active yet: ${coachProviderLabel(provider)} · ${model || "choose a model"}. Select Switch connection below to apply. The current connection stays active until then.`;
  }
  if (cancel) cancel.hidden = !pending;
  const local = $("#coach-local-description");
  if (local) local.hidden = provider !== "ollama";
}
function cancelCoachConnection() {
  const provider = state.connections.provider || "ollama";
  $("#coach-provider").value = provider;
  $("#coach-model").innerHTML = coachModelOptions(provider);
  $("#coach-custom-model-field").hidden = true;
  $("#coach-custom-model").required = false;
  updateCoachConnectionState();
  $("#coach-model-status").textContent =
    "Kept the active connection. Your message is unchanged.";
}
let coachModelLoadRequest = 0,
  coachModelBusy = false;
function coachModelOptions(
  provider,
  selected = state.connections[provider + "_model"] || "",
) {
  return `<option value="">Choose a model</option>${[
    ...new Set([selected, ...coachModelLists[provider]]),
  ]
    .filter((model) => model && model !== "__custom__")
    .map(
      (model) =>
        `<option value="${esc(model)}" ${model === selected ? "selected" : ""}>${esc(model)}</option>`,
    )
    .join(
      "",
    )}<option value="__custom__" ${selected === "__custom__" ? "selected" : ""}>Enter a model ID…</option>`;
}
function coachModelControls() {
  const provider = state.connections.provider || "ollama";
  return `<form id="coach-model-form" class="coach-model-controls" aria-label="Coach connection selection">
    <div class="coach-current-connection"><span class="eyebrow">ACTIVE CONNECTION</span><strong id="coach-current-connection">${esc(coachProviderLabel(provider))} · ${esc(state.connections[provider + "_model"] || "Choose a model")}</strong><small>Inference runs on your computer. No API key needed.</small></div>
    <div class="coach-model-grid"><input type="hidden" id="coach-provider" value="ollama"><div><label for="coach-model">Choose a model</label><select id="coach-model">${coachModelOptions(provider)}</select></div></div>
    <div class="field" id="coach-custom-model-field" hidden><label for="coach-custom-model">Model ID</label><input id="coach-custom-model" maxlength="160" placeholder="Enter the exact model ID"></div>
    <p id="coach-local-description" class="small muted" ${provider === "ollama" ? "" : "hidden"}>Recommended: Qwen3 8B. Start Ollama and install it with ollama pull qwen3:8b. The local context is ${n(state.connections.ollama_context_tokens || 8192)} tokens. Research still sends public queries to search services.</p>
    <div id="coach-switch-preview" class="coach-switch-preview" role="status" hidden></div>
    <div class="actions coach-switch-actions"><button class="btn" id="coach-apply-connection" type="submit" disabled>Connection active</button>${button("Keep current connection", "coach-cancel-connection", "secondary", 'id="coach-cancel-connection" hidden')}</div>
    <div class="actions">${button("Refresh model list", "coach-load-models", "secondary")}${button("Test active connection", "coach-test-connection", "secondary")}</div>
    <p id="coach-quota-info" class="small muted">${esc(quotaSummary(provider))}</p><p id="coach-model-status" class="small muted" role="status">Choose a connection and model, then select Switch connection. The active connection is shown above.</p></form>`;
}
function setCoachControlsDisabled(disabled) {
  const form = $("#coach-model-form");
  if (form) for (const element of form.elements) element.disabled = disabled;
  if (!disabled) updateCoachConnectionState();
}
async function loadCoachModels() {
  const form = $("#coach-model-form"),
    provider = $("#coach-provider").value,
    select = $("#coach-model"),
    status = $("#coach-model-status"),
    request = ++coachModelLoadRequest;
  status.textContent = `Loading ${coachProviderLabel(provider)} models…`;
  try {
    const data = await api("models", { provider });
    coachModelLists[provider] = data.models;
    if (
      form !== $("#coach-model-form") ||
      request !== coachModelLoadRequest ||
      $("#coach-provider").value !== provider
    )
      return;
    select.innerHTML = coachModelOptions(provider, select.value);
    status.textContent = `${data.models.length} models found. Choose a model, then select Switch connection.`;
    updateCoachConnectionState();
  } catch (error) {
    if (form === $("#coach-model-form") && request === coachModelLoadRequest)
      status.textContent = error.message;
  }
}
async function saveCoachModel() {
  if (chatIsBusy() || coachModelBusy)
    throw Error("Wait for the current coach request to finish.");
  const form = $("#coach-model-form"),
    provider = $("#coach-provider").value;
  const model =
    $("#coach-model").value === "__custom__"
      ? $("#coach-custom-model").value.trim()
      : $("#coach-model").value;
  if (!model) throw Error("Choose or enter a model first.");
  coachModelBusy = true;
  coachModelLoadRequest++;
  setCoachControlsDisabled(true);
  updateCoachConnectionState();
  try {
    state.connections = await api("connections", {
      provider,
      [provider + "_model"]: model,
    });
    if (form !== $("#coach-model-form")) return;
    $("#coach-active-model").textContent =
      `Using ${coachProviderLabel(provider)} · ${model}`;
    $("#coach-model-status").textContent =
      `Connection switched to ${coachProviderLabel(provider)} · ${model}. Your next message uses this connection.`;
    const current = $("#coach-current-connection");
    if (current)
      current.textContent = `${coachProviderLabel(provider)} · ${model}`;
    const hint = current?.parentElement?.querySelector("small");
    if (hint)
      hint.textContent =
        "Inference runs on your computer. No API key needed.";
    $("#coach-quota-info").textContent = quotaSummary(provider);
    const voiceControls = $("#chat-voice-controls");
    if (voiceControls) voiceControls.innerHTML = chatVoiceControls();
  } finally {
    coachModelBusy = false;
    if (form === $("#coach-model-form")) setCoachControlsDisabled(false);
  }
}
async function testCoachConnection(provider, status) {
  if (chatIsBusy() || coachModelBusy)
    throw Error("Wait for the current coach request to finish.");
  const model = state.connections[provider + "_model"],
    label = coachProviderLabel(provider);
  status.textContent = `Testing ${label} · ${model || "no model saved"}…`;
  coachModelBusy = true;
  coachModelLoadRequest++;
  setCoachControlsDisabled(true);
  try {
    const result = await api("connection-test", { provider, model });
    state.connections.rate_limits = result.rate_limits;
    if ($("#coach-quota-info"))
      $("#coach-quota-info").textContent = quotaSummary(
        state.connections.provider || "ollama",
      );
    status.textContent = `${label} responded ✓ · ${result.model} · ${(result.latency_ms / 1000).toFixed(1)} s. No fitness data was sent.`;
  } catch (error) {
    status.textContent = `${label}: ${error.message}`;
  } finally {
    coachModelBusy = false;
    setCoachControlsDisabled(false);
  }
}

const coachStarters = [
  { title: "Log/Plan Workout", hint: "Choose a day · review before saving", icon: "workouts", prompt: "Help me log or plan my workout. " },
  { title: "Protein/Creatine", hint: "Estimate food or log your intake", icon: "nutrition", prompt: "Help me with protein or creatine. " },
  { title: "Supplements/Sleep Logging", hint: "Use your goals and preferred units", icon: "sleep", prompt: "Help me log supplements or sleep. " },
  { title: "Learn an exercise", hint: "Steps, cues, mistakes & a short video", icon: "exercises", prompt: "Help me learn this exercise with simple steps, form cues and common mistakes: " },
  { title: "Assess my progress", hint: "Workouts · intake & recovery", icon: "progress", prompt: "Assess my progress" },
];
function coachPromptCards() {
  return `<div class="coach-starters" role="group" aria-label="Start a conversation">${coachStarters.map((starter) => `<button type="button" class="coach-starter" data-prompt="${esc(starter.prompt)}">${icon(starter.icon)}<span><strong>${esc(starter.title)}</strong><small>${esc(starter.hint)}</small></span></button>`).join("")}</div>`;
}
const voiceInput = VoiceInput.create({
  transcribe: (data) => api("transcribe", data),
  onTranscript(text) {
    const input = $("#chat-input");
    if (!input) return false;
    const combined = input.value + (input.value && !/\s$/.test(input.value) ? "\n" : "") + text;
    if (combined.length > input.maxLength) return false;
    input.value = combined;
    chatComposerDraft = combined;
    resizeChatComposer();
    input.focus({ preventScroll: true });
    return true;
  },
  onChange: updateChatVoiceControls,
});
function resizeChatComposer() {
  const input = $("#chat-input");
  if (!input) return;
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight + 2}px`;
}
function chatVoiceButton() {
  const { phase } = voiceInput.state();
  const recording = phase === "recording";
  const disabled = chatIsBusy() || coachModelBusy || (voiceInput.isBusy() && !recording);
  const label = recording ? "Stop recording and transcribe" : "Record audio";
  return `<button type="button" class="btn secondary chat-microphone ${recording ? "is-recording" : ""}" data-action="${recording ? "voice-stop" : "voice-record"}" aria-label="${label}" title="${label}" ${disabled ? "disabled" : ""}>${icon(recording ? "stop" : "microphone")}</button>`;
}
function chatVoiceControls() {
  const { phase, message, pendingText } = voiceInput.state();
  if (!message && !pendingText) return "";
  return `<div class="chat-voice-status"><p class="${phase === "error" ? "error" : "muted"}" role="status" aria-live="polite">${esc(message)}</p>${voiceInput.isBusy() || pendingText ? `<button type="button" class="link" data-action="voice-cancel" aria-label="Cancel recording or transcription">Cancel</button>` : ""}</div>${pendingText ? `<label class="small">Transcript<textarea readonly rows="3">${esc(pendingText)}</textarea></label><button type="button" class="btn secondary" data-action="voice-insert">Insert transcript</button>` : ""}`;
}
function updateChatVoiceControls() {
  const controls = $("#chat-voice-controls");
  if (controls) controls.innerHTML = chatVoiceControls();
  const microphone = $("#chat-voice-button");
  if (microphone) microphone.innerHTML = chatVoiceButton();
  const submit = $("#chat-form [type=submit]");
  if (submit) submit.disabled = chatIsBusy() || coachModelBusy || voiceInput.isBusy();
}
function coach() {
  return `<div class="coach-layout"><div class="card chat-card"><div class="chat-title"><span class="row-icon">${icon("coach")}</span><div class="row-main"><h2>Your fitness coach</h2><p id="coach-active-model" class="small muted">${state.connections.provider ? "Using " + coachProviderLabel(state.connections.provider) + " · " + esc(state.connections[state.connections.provider + "_model"] || "Choose a model") : "Start Ollama to use your local Qwen coach"}</p></div><button type="button" class="btn secondary chat-new-button" data-action="new-chat" aria-label="Start a new chat" title="Start a new chat">${icon("refresh")}</button><details class="chat-options"><summary>Options ${icon("settings")}</summary><div class="chat-options-panel"><h3>Chat settings</h3>${coachModelControls()}<label class="checkbox-label chat-research-choice"><input id="coach-research" type="checkbox" ${chatResearchMode ? "checked" : ""}> Research this message with sources</label><p class="small muted">Off by default for quicker replies. Research uses extra calls and may take longer.</p><div class="chat-sharing-links">${button("Coaching skills", "coach-skills", "secondary")}<button type="button" class="link" data-action="preview-context">Preview shared data</button><button type="button" class="link" data-action="coach-sharing">Sharing permissions</button><button type="button" class="link" data-page="settings">Connections ↗</button></div></div></details></div>${chatConsentGate()}<div class="chat-thread" id="chat-thread" role="log" aria-label="Coach conversation" aria-live="polite" aria-relevant="additions text">${chatThreadHtml()}</div>${state.coach_consent?.accepted ? `<form id="chat-form" class="chat-compose"><label class="sr-only" for="chat-input">Message your coach</label><div class="chat-input-row"><textarea id="chat-input" rows="5" required maxlength="6000" placeholder="Message your coach…">${esc(chatComposerDraft)}</textarea><div class="chat-compose-actions"><span id="chat-voice-button">${chatVoiceButton()}</span><button class="btn" type="submit" aria-label="Send message" ${chatBusy ? "disabled" : ""}>${chatBusy ? "Generating…" : "Send " + icon("arrow")}</button></div></div><div id="chat-voice-controls">${chatVoiceControls()}</div><div class="chat-compose-hint"><span>Enter to send · Shift+Enter for a new line</span><span id="chat-mode-label">${chatResearchMode ? "Research on" : "Quick chat"}</span></div><div id="chat-error" class="error" role="alert"></div></form>` : ""}</div><aside class="card coach-tasks" aria-label="Coach tasks"><h3>How can I help?</h3><p class="small muted">Choose a task to get started.</p>${coachPromptCards()}</aside></div>`;
}
function goalProgress(key, reference = journalDate) {
  return GoalTracking.progress(
    state.entries,
    state.profile.goals[key],
    key,
    reference,
    state.today,
  );
}
function goalPeriodText(goal) {
  return GoalTracking.periodLabel(goal);
}
function goalRange(goal) {
  return goal.start === goal.end
    ? dateLabel(goal.start)
    : `${dateLabel(goal.start)} – ${dateLabel(goal.end)}`;
}
function intakeGoalStat(key) {
  const g = goalProgress(key),
    label = key === "protein" ? "Protein" : "Creatine";
  const percent = g.amount ? (g.value / g.amount) * 100 : null;
  return stat(
    `${label} · ${goalPeriodText(g)}`,
    percent === null ? "—" : n(percent),
    percent === null ? "" : "%",
    `${n(g.value)} / ${n(g.amount)} g · ${goalRange(g)}`,
    key === "protein" ? "nutrition" : "drop",
    g.percent,
  );
}

function consistencyScores(compact = false) {
  const c = state.insights.consistency;
  const tiles = [
    {
      label: "Overall",
      value: c.overall,
      attainment: c.attainment,
      note: `${c.scored_categories} of 5 categories tracked`,
      key: "overall",
    },
    ...Object.entries(c.categories).map(([key, item]) => ({
      label: {
        exercise: "Exercise",
        protein: "Protein",
        creatine: "Creatine",
        supplements: "Supplements",
        sleep: "Sleep",
      }[key],
      value: item.score,
      attainment: item.attainment,
      note: item.since
        ? `${item.logged_days} logged day${item.logged_days === 1 ? "" : "s"} · since ${dateLabel(item.since)}`
        : "Start logging to build your score",
      key,
    })),
  ];
  return `<section class="card consistency-panel ${compact ? "consistency-compact" : "section-space"}" aria-label="Consistency scores"><div class="card-head"><div><h2>Your consistency</h2><p>Small steps count. Short breaks leave room to come back.</p></div><button class="link" data-page="goals">Set goals ↗</button></div><div class="consistency-grid">${tiles.map((t) => `<div class="consistency-tile ${t.key === "overall" ? "overall-score" : ""}"><span>${t.label}</span><div class="score-value">${t.value === null ? "—" : n(t.value)}<small>%</small></div><div class="score-track"><span style="width:${t.value || 0}%"></span></div><p class="attainment-line">Target attainment <strong>${t.attainment == null ? "—" : n(t.attainment) + "%"}</strong></p><p>${esc(t.note)}</p></div>`).join("")}</div><details class="score-method"><summary>How the score works</summary><p>This measures consistency with your current goals, not fitness, strength or health. Overall is the equal average of categories with data. New categories show — until you start; early scores are provisional. Each category uses its own logged history, up to the last 365 days. Goal changes recalculate that history. Target attainment is the unadjusted, day-weighted average percentage of each completed goal period, capped at 100% per period. It excludes unfinished periods. Overall averages the categories with completed data; it can include fewer categories than the consistency score.</p><p>Meeting a target earns full credit, capped at 100%. Missed days in a continuous break count at 10% for days 1–7, 35% for days 8–14, 65% for days 15–21, then 100%. Partial target periods have a 25% penalty on the shortfall and reset the break streak. The score is earned credit ÷ (earned credit + weighted misses) × 100. There is no penalty for an unfinished day or week; gym rest days are included in the frequency target.</p><p>For example, 90 consistent days followed by 30 days off gives about 84%; four separate one-week breaks during the same history give about 97%. Protein and Creatine use their own gram targets. Supplements score their individual saved quantity or frequency goals. Each selected supplement starts its history with its first comparable log; supplements without logs stay unscored. Sleep uses the lower attainment of total rest and total night hours. Naps cannot replace the night target. Uninterrupted stretches are a separate personal goal and do not reduce the score; unknown continuity is never inferred. Unlogged completed periods count as missed, not as proof you skipped them.</p></details></section>`;
}
let supplementGoalDraft = {};
const supplementMeasures = {
  days: "Days taken",
  doses: "Doses logged",
  g: "g",
  mg: "mg",
  mcg: "mcg",
  ml: "ml",
  capsule: "Capsules",
  tablet: "Tablets",
  softgel: "Softgels",
  serving: "Servings",
  scoop: "Scoops",
  drop: "Drops",
  IU: "IU",
};
function supplementGoalChoice(name, checked) {
  return `<label class="routine-choice"><input type="checkbox" name="consistency_supplements" value="${esc(name)}" ${checked ? "checked" : ""}><span>${esc(name)}</span></label>`;
}
function syncSupplementGoals() {
  document.querySelectorAll("[data-supplement-goal]").forEach((card) => {
    const read = (key) =>
      card.querySelector(`[data-goal-field="${key}"]`).value;
    supplementGoalDraft[card.dataset.supplementGoal] = {
      amount: read("amount"),
      measure: read("measure"),
      period: read("period"),
      unit: read("unit"),
    };
  });
}
function supplementGoalCards(selected) {
  return (
    selected
      .filter((name) => name !== "Creatine")
      .map((name) => {
        const index = state.profile.supplements.indexOf(name),
          id = `supp-goal-${index}`;
        const goal = (supplementGoalDraft[name] ||= {
          amount: 1,
          measure: "days",
          period: 1,
          unit: "day",
        });
        const saved = state.profile.supplement_goals[name];
        const progress = saved
          ? GoalTracking.supplementProgress(
              state.entries,
              saved,
              name,
              state.today,
              state.today,
            )
          : null;
        return `<section class="card goal-card supplement-goal-card" data-supplement-goal="${esc(name)}" aria-label="${esc(name)} goal"><div class="card-head"><h3>${esc(name)}</h3><span class="pill">SUPPLEMENT GOAL</span></div><div class="goal-timeframe"><div class="field"><label for="${id}-amount">Target amount</label><input id="${id}-amount" data-goal-field="amount" type="number" min="0.001" step="any" required value="${goal.amount}"></div><div class="field"><label for="${id}-measure">Measure</label><select id="${id}-measure" data-goal-field="measure">${Object.entries(
          supplementMeasures,
        )
          .map(
            ([value, label]) =>
              `<option value="${value}" ${goal.measure === value ? "selected" : ""}>${label}</option>`,
          )
          .join(
            "",
          )}</select></div></div><div class="goal-timeframe"><div class="field"><label for="${id}-period">Every</label><input id="${id}-period" data-goal-field="period" type="number" min="1" max="${{ day: 365, week: 52, month: 120 }[goal.unit]}" step="1" required value="${goal.period}"></div><div class="field"><label for="${id}-unit">Timeframe</label><select id="${id}-unit" data-goal-field="unit"><option value="day" ${goal.unit === "day" ? "selected" : ""}>Day(s)</option><option value="week" ${goal.unit === "week" ? "selected" : ""}>Week(s)</option><option value="month" ${goal.unit === "month" ? "selected" : ""}>Month(s)</option></select></div></div><div class="goal-current">${saved ? `<span>Saved target · ${n(saved.amount)} ${esc(supplementMeasures[saved.measure].toLowerCase())} ${goalPeriodText(saved)}</span><strong>${n(progress.value)} <small>/ ${n(saved.amount)}</small></strong><p>${goalRange(progress)} · logged so far${progress.incompatible ? ` · ${progress.incompatible} entries use another unit` : ""}</p>` : "<p>Set your target, then save goals to start tracking it.</p>"}</div></section>`;
      })
      .join("") ||
    '<p class="muted small">Select a supplement to add its goal here. Creatine uses its dedicated card above.</p>'
  );
}
function drawSupplementGoals() {
  syncSupplementGoals();
  const selected = [
    ...document.querySelectorAll('[name="consistency_supplements"]:checked'),
  ].map((el) => el.value);
  $("#supplement-goal-cards").innerHTML = supplementGoalCards(selected);
}
function supplementLogUnit(name) {
  if (name === "Creatine") return "g"; // Compatibility for old saved shortcuts.
  const measure = state.profile.supplement_goals[name]?.measure;
  return measure && !["days", "doses"].includes(measure)
    ? measure
    : name === "Collagen"
      ? "g"
      : "capsule";
}

function syncSupplementAmount(preserveExisting = false) {
  const amount = $("#entry-amount"), unit = $("#entry-unit");
  if (!amount || !unit || preserveExisting || amount.dataset.manual) return;
  if (/^tablets?$/i.test(unit.value.trim())) {
    if (!amount.value || amount.dataset.default === "true") {
      amount.value = "1"; amount.dataset.default = "true";
    }
  } else if (amount.dataset.default === "true") {
    amount.value = ""; delete amount.dataset.default;
  }
}

let supplementUnitRequest = 0;
async function refreshSupplementUnit(preserveExisting = false) {
  const form = $("#simple-entry-form"),
    unit = $("#entry-unit");
  if (!form || !unit) return;
  const request = ++supplementUnitRequest;
  try {
    const profile = await api("profile");
    if (request !== supplementUnitRequest || form !== $("#simple-entry-form"))
      return;
    state.profile = profile;
    const name = $("#entry-name").value;
    if (!preserveExisting && !unit.dataset.manual && name && name !== "__new__")
      unit.value = supplementLogUnit(name);
    syncSupplementAmount(preserveExisting);
  } catch {
    /* Cached goals remain usable if a background refresh fails. */
  }
}
function goals() {
  supplementGoalDraft = JSON.parse(
    JSON.stringify(state.profile.supplement_goals || {}),
  );
  const g = state.profile.goals;
  const cards = [
    ["workout", "Gym days", "workouts", "days"],
    ["protein", "Protein", "nutrition", "g"],
    ["creatine", "Creatine", "drop", "g"],
  ];
  return (
    head(
      "YOUR GOALS, YOUR PACE",
      "Set your rhythm.",
      "Choose overall targets and the time you want to give them.",
    ) +
    `<form id="goals-form"><div class="goal-grid primary-goals">${cards
      .map(([key, label, ico, unit]) => {
        const goal = g[key],
          p = goalProgress(key, state.today);
        return `<section class="card goal-card"><div class="card-head"><span class="row-icon">${icon(ico)}</span><h2>${label}</h2></div><div class="field"><label for="goal-${key}-amount">${label} target · ${unit}</label><input id="goal-${key}-amount" name="${key}_amount" type="number" min="${key === "creatine" ? 0 : key === "workout" ? 1 : 0.01}" step="${key === "workout" ? 1 : "any"}" required value="${goal.amount}"></div><div class="goal-timeframe"><div class="field"><label for="goal-${key}-period">Every</label><input id="goal-${key}-period" name="${key}_period" type="number" min="1" max="${{ day: 365, week: 52, month: 120 }[goal.unit]}" step="1" required value="${goal.period}"></div><div class="field"><label for="goal-${key}-unit">Timeframe</label><select id="goal-${key}-unit" name="${key}_unit"><option value="day" ${goal.unit === "day" ? "selected" : ""}>Day(s)</option><option value="week" ${goal.unit === "week" ? "selected" : ""}>Week(s)</option><option value="month" ${goal.unit === "month" ? "selected" : ""}>Month(s)</option></select></div></div><div class="goal-current"><span>Saved target · ${n(goal.amount)} ${unit} ${goalPeriodText(goal)}</span><strong>${n(p.value)} <small>/ ${n(goal.amount)} ${unit}</small></strong><p>${goalRange(p)} · logged so far</p></div></section>`;
      })
      .join(
        "",
      )}<section class="card goal-card"><div class="card-head"><span class="row-icon">${icon("sleep")}</span><h2>Sleep</h2></div><div class="field"><label for="goal-sleep-hours">Total sleep · hours per day</label><input id="goal-sleep-hours" name="sleep_goal" type="number" min="0.1" max="24" step="0.1" required value="${state.profile.sleep_goal}"></div><div class="field"><label for="goal-night-total">Night sleep · hours per rest day</label><input id="goal-night-total" name="night_hours_goal" type="number" min="0.1" max="24" step="0.1" required value="${state.profile.night_hours_goal}"></div><div class="field"><label for="goal-night-hours">Uninterrupted stretch · personal goal hours</label><input id="goal-night-hours" name="night_sleep_goal" type="number" min="0.1" max="24" step="0.1" required value="${state.profile.night_sleep_goal}"></div><p class="muscle-note">Total rest includes naps. The night target includes sleep before and after brief wake-ups. The uninterrupted-stretch goal is separate and does not affect consistency.</p></section></div><section class="card section-space"><div class="card-head"><div><h2>Supplements you take</h2><p>Select from the starting options or add your own. Every selected supplement has a goal.</p></div></div><div class="routine-choices" id="goal-supplement-choices">${state.profile.supplements
      .filter((name) => name.toLowerCase() !== "creatine")
      .map((name) =>
        supplementGoalChoice(
          name,
          state.profile.consistency_supplements.includes(name),
        ),
      )
      .join(
        "",
      )}</div><div class="custom-goal-supplement section-space"><label for="goal-new-supplement">Add a custom supplement</label><div class="actions"><input id="goal-new-supplement" maxlength="100" placeholder="e.g. Magnesium">${button("Add supplement", "goal-add-supplement", "soft")}</div><p id="goal-supplement-status" class="small muted" role="status"></p></div><p class="muscle-note">Protein and Creatine keep their dedicated goals. Creatine has its own consistency score; the other selected supplements use the individual goals below.</p></section><section class="section-space" aria-label="Supplement goals"><div class="card-head"><div><h2>Supplement goals</h2><p>Choose quantity or frequency goals per day, Monday–Sunday week, or calendar month.</p></div></div><div class="goal-grid" id="supplement-goal-cards">${supplementGoalCards(state.profile.consistency_supplements)}</div><p class="muscle-note">Days taken counts each date once; doses counts log entries. Quantity goals use matching units, with g/mg/mcg converted automatically. Targets are your choices; no dose is prescribed.</p></section><div class="goal-save"><p>Gym days count once per date. Days use a rolling window; weeks run Monday–Sunday; months run from the first to the actual last day, including leap-year February. Targets repeat until you change them.</p><button class="btn" type="submit">Save goals</button></div><p id="goals-error" role="alert"></p></form>` +
    consistencyScores()
  );
}

function localConnectionSettings(c) {
  return `<form class="provider-card" id="ollama-connection-form" data-connection="ollama" aria-label="Local Ollama connection"><div class="card-head"><h3>Local · Ollama</h3><span class="provider-status">Runs on your computer</span></div><p class="small muted">Recommended: Qwen3 8B. Install with <code>ollama pull qwen3:8b</code>, then start Ollama. Typed chat, log previews, corrections, plans and the research agent use the same approval flow. Research still uses external public search.</p><div class="field"><label for="ollama-url">Local Ollama address</label><input id="ollama-url" name="ollama_url" value="${esc(c.ollama_url || "http://127.0.0.1:11434")}" required></div><div class="field"><label for="ollama-model">Installed model</label><input id="ollama-model" name="ollama_model" value="${esc(c.ollama_model || "qwen3:8b")}" list="ollama-models" required><datalist id="ollama-models"></datalist></div><div class="field"><label for="ollama-context">Local context · tokens</label><input id="ollama-context" name="ollama_context_tokens" type="number" min="4096" max="64000" step="1" value="${c.ollama_context_tokens || 8192}" required></div><p class="small muted">Context includes the prompt, journal context, recent conversation, tool results and reply. Larger contexts use more memory. Your coach runs locally without an API key.</p><div class="actions">${button("Find installed models", "load-models", "soft", 'data-provider="ollama"')}<button class="btn" type="submit">Save local setup</button>${button("Test saved local connection", "test-connection", "secondary", 'data-provider="ollama"')}</div><p id="ollama-model-status" class="small muted"></p><p id="ollama-save-status" class="small muted" role="status"></p><p class="small muted">Saved settings apply to your next coaching message.</p></form>`;
}
function connectionSettings() {
  const c = state.connections;
  return `<section class="card" aria-label="Qwen setup"><h2>Your local Qwen coach</h2><p class="subtitle">No accounts or API keys. Start Ollama on your computer to use the coach.</p>${localConnectionSettings(c)}<form id="agent-connection-form" data-connection="agent"><div class="field section-space"><label for="agent-budget">Agent input budget · tokens</label><input id="agent-budget" type="number" name="context_budget_tokens" min="2000" max="64000" step="1" required value="${c.context_budget_tokens || 5000}"></div><p class="small muted">Limits the journal context included in each coaching request.</p><button type="submit" class="btn secondary">Save agent budget</button><p id="agent-save-status" class="small muted" role="status"></p></form></section>`;
}

function settings() {
  const p = state.profile;
  return (
    head(
      "MAKE IT YOURS",
      "A journal that fits your life.",
      "Personal goals, your local Qwen coach, and control over your data.",
    ) +
    `<div class="settings-grid"><div><form class="card" id="profile-form"><div class="card-head"><h2>Your profile & training context</h2></div><div class="form-grid"><div class="field"><label for="profile-name">Your name</label><input id="profile-name" name="name" value="${esc(p.name)}" class="full-width"></div><div class="field"><label for="body-weight">Body weight · kg (optional)</label><input id="body-weight" name="weight_kg" type="number" min="20" max="500" step="0.1" value="${p.weight_kg || ""}" class="full-width"></div><div class="field"><label for="experience">Training experience</label><select id="experience" name="experience" class="full-width">${["beginner", "intermediate", "advanced"].map((v) => `<option ${p.experience === v ? "selected" : ""}>${v}</option>`).join("")}</select></div></div><div class="field section-space"><label for="focus">What are you working toward?</label><textarea id="focus" name="focus" placeholder="Stronger arms over the next 3 months…">${esc(p.focus)}</textarea></div><div class="field"><label for="constraints">Equipment, available days, dietary preferences, limitations</label><textarea id="constraints" name="constraints" placeholder="Full gym, Mon/Wed/Fri, vegetarian…">${esc(p.constraints)}</textarea></div><div class="field"><label for="supplements">Supplements in your routine · comma separated</label><input id="supplements" name="supplements" value="${esc(p.supplements.filter((name) => name.toLowerCase() !== "creatine").join(", "))}" class="full-width"></div><p class="muscle-note">Update overall targets in Set goals on the top menu. Profile weight gives the coach context; log measurements in Progress for a timeline.</p><button class="btn section-space" type="submit">Save profile</button></form><div class="card section-space"><h2>Your journal belongs to you</h2><p class="subtitle">Your logs and conversations are stored on your computer. Qwen runs locally through Ollama, with no account or API key.</p><div class="actions section-space">${button("Export journal backup", "export", "secondary")}</div><div class="reset-card section-space"><h3>Start fresh</h3><p class="subtitle">Clear all journal data and personal goals. You can download a backup and review exactly what will be removed first.</p>${button("Reset journal…", "reset-dialog", "secondary", 'style="margin-top:14px"')}</div><p class="muscle-note">Exports include fitness data and chat, without API keys. See the README for full database backup and restore steps. Core tracking works without an internet connection.</p></div></div>${connectionSettings()}</div>`
  );
}
function fitChatViewport() {
  const card = $(".chat-card");
  if (card)
    card.style.setProperty(
      "--chat-height",
      `${Math.max(300, window.innerHeight - card.getBoundingClientRect().top - 18)}px`,
    );
}
window.addEventListener("resize", fitChatViewport);
function render() {
  hideHabitDetails();
  voiceInput.cancel();
  page = location.hash.slice(1) || "overview";
  if (["journal", "workouts", "nutrition"].includes(page)) {
    page = "track";
    location.hash = "track";
  }
  if (!pages[page] && page !== "settings") page = "overview";
  document.body.classList.toggle("coach-page", page === "coach");
  document.body.classList.toggle("dashboard-page", page === "overview");
  document.body.classList.toggle("progress-page", page === "progress");
  document.body.classList.toggle("compact-section-page", ["exercises", "progress", "goals"].includes(page));
  document.body.classList.toggle("tracking-page", page === "track");
  $("#page-label").textContent = pages[page] || "Settings & connections";
  $("#nav").innerHTML = Object.entries(pages)
    .map(
      ([id, label]) =>
        `<button class="nav-item ${id === page ? "active" : ""}" data-page="${id}" aria-label="${label}" ${id === page ? 'aria-current="page"' : ""}>${icon(id)}<span>${label}</span></button>`,
    )
    .join("");
  $("#content").innerHTML = {
    overview,
    track,
    exercises,
    progress,
    coach,
    settings,
    goals,
  }[page]();
  BodyMap.bind($("#content"));
  if (page === "coach") {
    fitChatViewport();
    resizeChatComposer();
    chatThreadSignature = "";
    syncChatThread(true);
    ensureChatPolling();
  }
}
const dialogLifecycle = DialogLifecycle.create($("#modal"), () => {
  $("#modal-content").innerHTML = "";
  formDraft = null;
});
function closeModal() {
  return dialogLifecycle.close();
}
function modal(title, description, body, headerActions = "", preservePosition = false) {
  const dialog = $("#modal"),
    keepPosition = preservePosition && dialog.open,
    scroll = dialog.scrollTop,
    bodyScroll = $("#modal .modal-body")?.scrollTop || 0,
    active = document.activeElement;
  let focusSelector;
  if (keepPosition && dialog.contains(active)) {
    if (active.id) focusSelector = `#${CSS.escape(active.id)}`;
    else if (active.dataset.set) focusSelector = `[data-set="${active.dataset.set}"]`;
    else if (active.dataset.action) {
      focusSelector = `[data-action="${active.dataset.action}"]`;
      for (const key of ["index", "setIndex"])
        if (active.dataset[key] !== undefined)
          focusSelector += `[data-${key === "setIndex" ? "set-index" : key}="${active.dataset[key]}"]`;
    }
  }
  $("#modal-content").innerHTML =
    `<div class="modal-head"><div><h2>${esc(title)}</h2><p class="modal-description">${esc(description)}</p></div><div class="modal-head-actions">${headerActions}<button class="close" data-action="close-modal" aria-label="Close dialog">×</button></div></div><div class="modal-body">${body}</div>`;
  if (keepPosition) {
    // Updating an open editor is not opening a new dialog. In particular,
    // lifecycle.show() deliberately resets scroll for genuinely new editors.
    (focusSelector && dialog.querySelector(focusSelector) || dialog).focus({ preventScroll: true });
    const head = $("#modal-content").firstElementChild;
    const restore = () => {
      if (!dialog.open || $("#modal-content").firstElementChild !== head) return;
      dialog.scrollTop = scroll;
      $("#modal .modal-body").scrollTop = bodyScroll;
    };
    restore();
    requestAnimationFrame(restore);
  } else dialogLifecycle.show();
}
function field(label, name, value = "", type = "text", extra = "") {
  const id = "entry-" + name;
  if (type === "date") extra += ' min="1900-01-01" max="2050-12-31"';
  return `<div class="field"><label for="${id}">${label}</label><input class="full-width" id="${id}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;
}
function entryFooter(existing, draft) {
  return `<div id="form-error" class="error" role="alert"></div><div class="modal-foot">${existing ? `<button type="button" class="btn secondary" data-action="delete-entry" data-id="${existing}">Delete entry</button>` : ""}<button type="button" class="btn secondary" data-action="close-modal">Cancel</button><button class="btn" type="submit">${draft ? "Approve & save" : existing ? "Save changes" : "Save entry"}</button></div>`;
}
function simpleForm(kind, entry = {}, draft = null) {
  if (GoalTracking.isCreatine({ ...entry, kind })) kind = "creatine";
  formDraft = draft;
  let body = field(
    kind === "sleep" ? "Rest day" : "Date",
    "date",
    entry.date || journalDate || state.today,
    "date",
    `required`,
  );
  if (kind === "meal")
    body +=
      `<div class="field"><label for="entry-description">What did you eat? Include portions.</label><textarea id="entry-description" name="description" required maxlength="2000">${esc(entry.description || "")}</textarea></div>` +
      field(
        "Protein · grams",
        "protein",
        entry.protein ?? "",
        "number",
        'required min="0" max="500" step="0.1"',
      ) +
      (entry.low !== undefined
        ? `<div class="form-grid">${field("Estimate range · low g", "low", entry.low, "number", 'min="0" max="500" step="0.1"')}${field("Estimate range · high g", "high", entry.high, "number", 'min="0" max="500" step="0.1"')}</div>`
        : "");
  if (kind === "supplement") {
    const options = [
      ...new Set([
        ...state.profile.supplements,
        ...(entry.name ? [entry.name] : []),
      ]),
    ].filter((name) => name.toLowerCase() !== "creatine");
    const chosen = entry.name || options[0];
    body += `<div class="field"><label for="entry-name">Supplement</label><select class="full-width" id="entry-name" name="name" required><option value="">Select a supplement</option>${options.map((name) => `<option value="${esc(name)}" ${name === chosen ? "selected" : ""}>${esc(name)}</option>`).join("")}<option value="__new__">+ Add a new supplement…</option></select></div><div class="custom-supplement-box" id="custom-supplement-box" hidden><label for="new-supplement-name">New supplement name</label><div class="actions"><input id="new-supplement-name" maxlength="100" placeholder="e.g. Magnesium" autocomplete="off">${button("Save to my list", "save-supplement-option", "soft")}</div><p class="small muted">Saved names stay in your selection list for future logs.</p></div><div class="form-grid">${field("Amount", "amount", entry.amount ?? (/^tablets?$/i.test(entry.unit || supplementLogUnit(chosen)) ? 1 : ""), "number", 'required min="0.001" max="100000" step="0.001"' + (entry.amount == null && /^tablets?$/i.test(entry.unit || supplementLogUnit(chosen)) ? ' data-default="true"' : ""))}${field("Unit", "unit", entry.unit || supplementLogUnit(chosen), "text", 'required maxlength="20"')}</div>`;
  }
  if (kind === "creatine")
    body +=
      field(
        "Creatine · grams",
        "amount",
        entry.amount ?? "",
        "number",
        'required min="0.001" max="100000" step="0.001"',
      ) + '<input type="hidden" name="unit" value="g">';
  if (kind === "sleep") {
    body +=
      `<div class="field"><label for="entry-period">Sleep type</label><select id="entry-period" name="period"><option value="night" ${(entry.period || "night") === "night" ? "selected" : ""}>Night sleep</option><option value="afternoon" ${entry.period === "afternoon" ? "selected" : ""}>Afternoon nap</option><option value="other" ${entry.period === "other" ? "selected" : ""}>Other nap</option></select></div>` +
      field(
        "Hours slept",
        "hours",
        entry.hours ?? "",
        "number",
        'required min="0.1" max="24" step="0.1"',
      ) +
      `<div id="night-sleep-fields" ${entry.period && entry.period !== "night" ? "hidden" : ""}>${field("Longest uninterrupted stretch · hours", "continuous_hours", entry.continuous_hours ?? "", "number", 'min="0" max="24" step="0.1"')}<p class="small muted">Optional. Track your uninterrupted-sleep goal without affecting consistency. For 2–6 am, then 6–8:30 am, enter 6.5 hours total and 4 hours uninterrupted.</p></div><p class="muscle-note">Choose the day you’re resting from, not the morning you wake. Naps and that night’s sleep share the same rest day—even if you go to bed after midnight.</p>`;
  }
  if (kind === "body")
    body += field(
      "Body weight · kg",
      "weight_kg",
      entry.weight_kg || "",
      "number",
      'required min="20" max="500" step="0.1"',
    );
  body +=
    `<div class="field section-space"><label for="entry-notes">Notes ${draft ? "· review AI assumptions" : ""}</label><textarea id="entry-notes" name="notes" maxlength="4000">${esc(entry.notes || "")}</textarea></div>` +
    entryFooter(entry.id, draft);
  modal(
    draft
      ? "Review your " +
          (kind === "meal"
            ? "food estimate"
            : kind === "creatine"
              ? "creatine entry"
              : "supplement entry")
      : kind === "meal"
        ? "Log your food"
        : kind === "body"
          ? "Body weight check-in"
          : kind === "creatine"
            ? "Log creatine"
            : kind === "sleep"
              ? "Log sleep"
              : "Log a supplement",
    draft
      ? "Edit anything that needs correcting. Approval adds this entry to your journal."
      : kind === "body"
        ? "Small entries add up to a bigger picture."
        : entry.id
          ? "Correct this entry or change its date."
          : "Log an entry for the selected day. You can change the date.",
    `<form id="simple-entry-form" data-kind="${kind}" data-id="${entry.id || ""}" data-source="${entry.source || "manual"}">${body}</form>`,
  );
  if (kind === "supplement") refreshSupplementUnit(Boolean(entry.id));
}
function openWorkout(kind = "workout", entry = {}, draft = null) {
  formDraft = draft;
  const day = entry.date || journalDate || state.today;
  const source = entry;
  workoutForm = JSON.parse(
    JSON.stringify({
      ...source,
      kind,
      name: sessionTitle(day),
      date: day,
      duration: source.duration || "",
      notes: source.notes || "",
      exercises: (source.exercises || []).map((item) =>
        kind === "plan"
          ? { exercise_id: item.exercise_id }
          : item.sets?.length
            ? WorkoutHistory.normalize(item, byId)
            : WorkoutHistory.makeExercise(
                state.entries,
                item.exercise_id,
                day,
                byId,
              ),
      ),
    }),
  );
  drawWorkout(false);
}
function syncWorkout() {
  const form = $("#workout-form");
  if (!form) return;
  if (workoutForm.kind === "plan") {
    workoutForm.date = form.elements.date.value;
    return;
  }
  for (const key of ["date", "duration", "notes"])
    workoutForm[key] = form.elements[key].value;
  workoutForm.duration = Number(workoutForm.duration || 0);
  form.querySelectorAll("[data-set]").forEach((input) => {
    const [ex, set, key] = input.dataset.set.split(":");
    workoutForm.exercises[ex].sets[set][key] = Number(input.value);
  });
  for (const item of workoutForm.exercises)
    for (const set of item.sets) {
      if (item.tracking === "time") set.reps = 0;
      else set.seconds = 0;
      if (item.load_mode === "bodyweight") set.weight = 0;
    }
}
function usualPicker() {
  const usual = WorkoutHistory.usualExercises(state.entries, state.today).slice(
    0,
    12,
  );
  return `<div class="usual-heading"><h3>Your usual exercises</h3><span class="small muted">Based on your logged sessions</span></div>${
    usual.length
      ? `<div class="usual-grid">${usual
          .map((item) => {
            const ex = byId[item.id],
              selected = workoutForm.exercises.some(
                (e) => e.exercise_id === item.id,
              );
            return `<button type="button" class="usual-exercise ${selected ? "selected" : ""}" data-action="pick-exercise" data-recall="true" data-id="${item.id}" ${selected ? "disabled" : ""}><img src="${image(item.id)}" alt=""><span>${esc(ex.name)}<small>${item.count} sessions · ${selected ? "Added ✓" : workoutForm.kind === "plan" ? "Add exercise +" : "Use last entry +"}</small></span></button>`;
          })
          .join("")}</div>`
      : '<p class="small muted">Your regular exercises will appear here after you log workouts.</p>'
  }`;
}
function workoutOptions() {
  const f = workoutForm;
  return `<details class="workout-options" id="workout-options"><summary aria-label="Workout options" title="Workout options"><span aria-hidden="true">⋯</span></summary><div class="workout-options-panel"><div data-workout-options-list><div class="eyebrow">WORKOUT OPTIONS</div>${f.kind === "workout" && WorkoutHistory.latestWorkout(state.entries, f.date, f.id) ? '<button type="button" data-action="request-previous-workout">Use previous workout…</button>' : ""}<button type="button" class="workout-clear-option" data-action="request-blank-workout">Start blank…</button></div><div data-workout-options-confirm hidden role="group" aria-label="Confirm workout changes"><h3 id="workout-confirm-title"></h3><p id="workout-confirm-description"></p><div class="actions"><button type="button" class="btn secondary" data-action="cancel-workout-replace">Keep editing</button><button type="button" class="btn danger" id="workout-confirm-button"></button></div></div></div></details>`;
}
function resetWorkoutOptions() {
  const options = $("#workout-options");
  if (!options) return;
  options.querySelector("[data-workout-options-list]").hidden = false;
  options.querySelector("[data-workout-options-confirm]").hidden = true;
}
function confirmWorkoutReplace(action) {
  syncWorkout();
  const options = $("#workout-options");
  options.querySelector("[data-workout-options-list]").hidden = true;
  options.querySelector("[data-workout-options-confirm]").hidden = false;
  const blank = action === "blank-workout";
  $("#workout-confirm-title").textContent = blank
    ? "Start this form blank?"
    : "Replace with your previous workout?";
  $("#workout-confirm-description").textContent = blank
    ? "This clears the exercises, duration and notes in this form. Saved logs are not deleted."
    : "This replaces the current form and its unsaved edits with your previous session. Saved logs are not changed.";
  const confirm = $("#workout-confirm-button");
  confirm.dataset.action = action;
  confirm.textContent = blank ? "Clear form" : "Replace form";
  options.querySelector('[data-action="cancel-workout-replace"]').focus();
}
function workoutSetRow(item, i, j) {
  const set = item.sets[j],
    ex = byId[item.exercise_id],
    keys =
      item.load_mode === "bodyweight"
        ? [item.tracking === "time" ? "seconds" : "reps"]
        : ["weight", item.tracking === "time" ? "seconds" : "reps"];
  return `<div class="set-row metric-${keys.length}"><span>${j + 1}</span>${keys.map((key) => {
    const label = `${esc(ex.name)} set ${j + 1} ${key}`;
    return `<div class="set-number"><input type="number" value="${set[key] || (key === "weight" ? 0 : "")}" min="${key === "weight" ? 0 : 1}" max="${key === "seconds" ? 86400 : 1000}" step="${key === "weight" ? "any" : "1"}" data-set="${i}:${j}:${key}" aria-label="${label}" required><div class="set-number-arrows"><button type="button" data-action="step-set" data-direction="1" aria-label="Increase ${label} by 1">▴</button><button type="button" data-action="step-set" data-direction="-1" aria-label="Decrease ${label} by 1">▾</button></div></div>`;
  }).join("")}<button type="button" class="remove" data-action="remove-set" data-index="${i}" data-set-index="${j}" aria-label="Remove ${esc(ex.name)} set ${j + 1}">×</button></div>`;
}
function stepWorkoutNumber(input, direction) {
  const current = Number.isFinite(input.valueAsNumber) ? input.valueAsNumber : 0;
  input.value = String(Math.min(Number(input.max), Math.max(Number(input.min),
    Number((current + direction).toFixed(6)))));
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
}
function drawWorkout(preservePosition = true) {
  const f = workoutForm;
  if (f.kind === "plan") return drawPlan(preservePosition);
  const exercisesHtml = f.exercises
    .map((item, i) => {
      const ex = byId[item.exercise_id],
        timed = item.tracking === "time",
        plank = item.exercise_id === "Plank",
        bodyweight = item.load_mode === "bodyweight";
      const keys = bodyweight
        ? [timed ? "seconds" : "reps"]
        : ["weight", timed ? "seconds" : "reps"];
      const last = WorkoutHistory.latestExercise(
        state.entries,
        item.exercise_id,
        f.date,
        f.id,
      );
      return `<div class="workout-exercise"><div class="exercise-title"><img src="${image(ex.id)}" alt="${esc(ex.name)}"><div class="row-main"><h3>${esc(ex.name)}</h3><p class="small muted">${esc((ex.bodyParts || ex.primaryMuscles).join(", "))}${last ? " · Last logged " + esc(sessionTitle(last.date)) : ""}</p></div><button type="button" class="remove" data-action="remove-exercise" data-index="${i}" aria-label="Remove ${esc(ex.name)}">×</button></div><div class="tracking-choice"><div class="tracking-control">${plank ? '<span class="pill">TIME ONLY · seconds</span>' : `<label for="tracking-${i}">Track by</label><select id="tracking-${i}" data-tracking="${i}" aria-label="${esc(ex.name)} tracking"><option value="reps" ${!timed ? "selected" : ""}>Reps</option><option value="time" ${timed ? "selected" : ""}>Time</option></select>`}</div><div class="tracking-control"><label for="load-mode-${i}">Resistance</label><select id="load-mode-${i}" data-load-mode="${i}" aria-label="${esc(ex.name)} resistance"><option value="bodyweight" ${bodyweight ? "selected" : ""}>Bodyweight</option><option value="weighted" ${!bodyweight ? "selected" : ""}>Added weight</option></select></div></div><div class="set-labels metric-${keys.length}"><span>SET</span>${keys.map((key) => `<span>${key === "weight" ? "LOAD · kg" : key === "seconds" ? "TIME · sec" : "REPS"}</span>`).join("")}<span></span></div>${item.sets.map((_, j) => workoutSetRow(item, i, j)).join("")}<button type="button" class="link" data-action="add-set" data-index="${i}">+ Add set</button>${last ? `<button type="button" class="link recall-last" data-action="recall-exercise" data-index="${i}">Use last entry · ${esc(sessionTitle(last.date))}</button>` : ""}</div>`;
    })
    .join("");
  modal(
    sessionTitle(f.date),
    f.kind === "plan"
      ? "Plans stay separate from completed workouts. All sets are editable."
      : f.id
        ? "Edit this day’s workout. Save changes updates this day instead of adding another entry."
        : "Start with an empty workout. Add a recent exercise or search for something new.",
    `<form id="workout-form"><div class="form-grid">${field("Date", "date", f.date, "date", "required")}${field("Session duration · minutes", "duration", f.duration, "number", 'min="0" max="1440" step="1"')}</div>${f._copied_from ? `<div class="notice section-space">Prefilled from ${esc(sessionTitle(f._copied_from))}. Review and edit before saving.</div>` : f.id && f.kind === "workout" ? '<div class="notice section-space">One workout per day. Saving replaces this day’s current information.</div>' : ""}<div class="picker section-space">${usualPicker()}<label for="picker-search" class="section-space">ADD AN EXERCISE · SEARCH ${catalog.length} MOVEMENTS</label><input id="picker-search" placeholder="Search by exercise, muscle or equipment" autocomplete="off"><div class="picker-results" id="picker-results">${pickerResults("")}</div></div>${exercisesHtml}<div class="field section-space"><label for="entry-notes">Session notes, progression, how you felt</label><textarea id="entry-notes" name="notes" maxlength="4000">${esc(f.notes)}</textarea></div>${f.id ? `<div class="actions">${button("Copy as a plan", "copy-plan", "soft")}${f.kind === "plan" ? button("Start this workout", "start-current-plan", "soft") : ""}</div>` : ""}${entryFooter(f.id, formDraft)}</form>`,
    workoutOptions(),
    preservePosition,
  );
  $("#workout-options").addEventListener("toggle", (event) => {
    if (!event.currentTarget.open) resetWorkoutOptions();
  });
}
function pickerResults(query, matches = null) {
  if (!query.trim())
    return '<p class="small muted">Search the full library to add something new.</p>';
  return (
    (matches || exerciseMatches(query))
      .slice(0, 12)
      .map((ex) => {
        const selected = workoutForm.exercises.some(
          (e) => e.exercise_id === ex.id,
        );
        return `<button class="picker-item" type="button" data-action="pick-exercise" data-id="${ex.id}" ${selected ? "disabled" : ""}><img src="${image(ex.id)}" alt=""><span>${esc(ex.name)}<small>${esc((ex.bodyParts || ex.primaryMuscles).join(" · "))} · ${esc(ex.equipment || "body only")}</small></span><span style="margin-left:auto">${selected ? "✓" : "+"}</span></button>`;
      })
      .join("") ||
    '<p class="small muted">No matches. Try a different name.</p>'
  );
}
function detailExercise(id) {
  const e = byId[id],
    pr = state.insights.prs[id];
  modal(
    e.name,
    (e.bodyParts || e.primaryMuscles).join(" · ") +
      " · " +
      (e.equipment || "body only") +
      " · " +
      e.level,
    `<img class="exercise-detail-photo" src="${image(id)}" alt="${esc(e.name)} reference">${e.photoNote ? `<p class="notice">${esc(e.photoNote)}</p>` : ""}${e.referenceVideo ? `<a class="btn soft section-space" href="${esc(e.referenceVideo)}" target="_blank" rel="noopener noreferrer">Watch your reference video ↗</a>` : ""}${pr ? `<p class="notice">Your best logged: ${pr.weight ? n(pr.weight) + " kg × " + n(pr.reps) + " reps" : pr.reps ? n(pr.reps) + " reps" : n(pr.seconds) + " seconds"}</p>` : ""}<h3 class="section-space">Find your form</h3><ol class="instructions">${e.instructions.map((v) => `<li>${esc(v)}</li>`).join("")}</ol><div class="actions"><a class="btn secondary" href="https://www.youtube.com/results?search_query=${encodeURIComponent(e.name + " exercise proper form tutorial")}" target="_blank" rel="noopener noreferrer">Watch on YouTube ↗</a></div>`,
  );
}
async function saveConnection(service) {
  const form = $(`#${service}-connection-form`);
  state.connections = await api("connections", Object.fromEntries(new FormData(form)));
  $(`#${service}-save-status`).textContent = service === "ollama" ? "Local Qwen setup saved." : "Agent budget saved.";
}

function prepareCoachMessage(message) {
  voiceInput.cancel();
  chatComposerDraft = message;
  chatLoggingKind = null;
  chatRevisionId = null;
  const options = $(".chat-options");
  if (options) options.open = false;
  const input = $("#chat-input");
  if (input) {
    input.value = message;
    resizeChatComposer();
    input.focus();
  }
}

async function sendChat(event, approvalId = null, retryRequestId = null) {
  event.preventDefault();
  if (chatIsBusy()) return;
  const input = $("#chat-input"),
    error = $("#chat-error");
  if (voiceInput.isBusy()) {
    error.textContent = "Stop or cancel audio and review the transcript before sending.";
    return;
  }
  if (coachModelBusy) {
    error.textContent = "Wait for the connection change or test to finish.";
    return;
  }
  if (!state.coach_consent?.accepted) {
    error.textContent = "Accept the sharing agreement before your first chat.";
    return;
  }
  if (!approvalId && pendingCoachConnection()) {
    error.textContent =
      "Apply your connection change with Switch connection, or choose Keep current connection before sending.";
    $("#coach-apply-connection")?.focus();
    return;
  }
  const message = approvalId ? "I approve" : input.value.trim();
  error.textContent = "";
  if (!message) {
    error.textContent = "Enter a message for your coach.";
    return;
  }
  const request_id = retryRequestId || crypto.randomUUID();
  const logging_kind = chatLoggingKind,
    revise_draft_id = chatRevisionId;
  const research =
    logging_kind && logging_kind !== "any" ? false : chatResearchMode;
  chatResearchMode = false;
  if ($("#coach-research")) $("#coach-research").checked = false;
  if ($("#chat-mode-label")) $("#chat-mode-label").textContent = "Quick chat";
  const options = $(".chat-options");
  if (options) options.open = false;
  optimisticChat = {
    role: "user",
    text: message,
    request_id,
    status: "pending",
    research,
    logging_kind,
    revise_draft_id,
  };
  chatStage = "Received. Understanding your request…";
  chatBusy = true;
  if (!approvalId) {
    input.value = "";
    chatComposerDraft = "";
    resizeChatComposer();
  }
  syncChatThread(true);
  ensureChatPolling();
  try {
    const reply = await api("chat", {
      message,
      stream: true,
      request_id,
      date: journalDate,
      research,
      logging_kind,
      revise_draft_id,
      ...(approvalId ? { approve_draft_id: approvalId } : {}),
    });
    await refresh(false);
    optimisticChat = null;
    if (reply.draft) {
      chatLoggingKind = null;
      chatRevisionId = null;
    } else if (reply.approved) {
      activeAiPreview = null;
      journalDate = reply.approved.date;
      chatLoggingKind = null;
      chatRevisionId = null;
    }
  } catch (failure) {
    try {
      await refreshChatSnapshot();
    } catch {
      /* The local message stays visible. */
    }
    if (
      state.messages?.some(
        (item) => item.role === "assistant" && item.request_id === request_id,
      )
    ) {
      optimisticChat = null;
      return;
    }
    if (optimisticChat)
      optimisticChat = {
        ...optimisticChat,
        status: "failed",
        error: failure.message,
      };
    if (!state.chat_status?.busy && $("#chat-error"))
      $("#chat-error").textContent = failure.message;
    if (
      !state.chat_status?.busy &&
      input === $("#chat-input") &&
      !input.value
    ) {
      if (!approvalId) {
        input.value = message;
        chatComposerDraft = message;
        resizeChatComposer();
      }
    }
  } finally {
    chatBusy = false;
    syncChatThread();
    ensureChatPolling();
  }
}

async function action(name, el) {
  const id = el.dataset.id;
  switch (name) {
    case "voice-record":
      if (!chatIsBusy() && !coachModelBusy) await voiceInput.record();
      break;
    case "voice-stop":
      voiceInput.stop();
      break;
    case "voice-cancel":
      voiceInput.cancel();
      break;
    case "voice-insert":
      voiceInput.insert();
      break;
    case "intake-period":
      intakePeriod = el.dataset.period === "weekly" ? "weekly" : "daily";
      $("#intake-panel").innerHTML = intakePanel();
      $("#intake-panel").querySelector(`[data-period="${intakePeriod}"]`).focus({ preventScroll: true });
      break;
    case "new-chat": {
      if (chatIsBusy()) {
        toast("Wait for the coach to finish before starting a new chat.");
        break;
      }
      voiceInput.cancel();
      el.disabled = true;
      try {
        await api("new-chat", {});
        optimisticChat = null;
        chatComposerDraft = "";
        chatLoggingKind = null;
        chatRevisionId = null;
        chatResearchMode = false;
        await refreshChatSnapshot();
        render();
        $("#chat-input")?.focus();
      } finally {
        el.disabled = false;
      }
      break;
    }
    case "review-week-prev":
    case "review-week-next":
    case "review-week-today": {
      const chosen =
        name === "review-week-today"
          ? state.today
          : addDays(
              reviewDate || state.today,
              name === "review-week-prev" ? -7 : 7,
            );
      reviewDate =
        chosen < "1900-01-01"
          ? "1900-01-01"
          : chosen > state.today
            ? state.today
            : chosen;
      updateReviewPanels(
        `[data-action="${name}"][data-review="${el.dataset.review}"]`,
      );
      break;
    }
    case "filter-pr-exercise":
      recordExercise = id; recordSearchQuery = byId[id].name;
      recordRankedIds = [id]; recordSuggestionsOpen = false;
      exerciseSearchVersions.records = (exerciseSearchVersions.records || 0) + 1;
      updateExerciseRecords("pr-exercise-filter");
      break;
    case "clear-pr-filters":
      recordSearchQuery = ""; recordRankedIds = null; recordSuggestionsOpen = false;
      exerciseSearchVersions.records = (exerciseSearchVersions.records || 0) + 1;
      recordExercise = "";
      recordBodyPart = "";
      updateExerciseRecords("pr-exercise-filter");
      break;
    case "coach-sharing":
      coachSharingDialog();
      break;
    case "revoke-coach-consent":
      await saveCoachAgreement(false);
      break;
    case "retry-chat": {
      if (chatIsBusy()) break;
      const message =
        state.messages.find((item) => String(item.id) === id) || optimisticChat;
      if (message && $("#chat-input")) {
        chatResearchMode = message.research === true;
        chatLoggingKind = message.logging_kind || null;
        chatRevisionId = message.revise_draft_id || null;
        $("#chat-input").value = message.text;
        chatComposerDraft = message.text;
        resizeChatComposer();
        await sendChat({ preventDefault() {} }, null, message.request_id);
      }
      break;
    }
    case "activity-day":
      journalDate = el.dataset.date;
      location.hash = "track";
      render();
      break;
    case "activity-prev":
    case "activity-next": {
      const d = dateObj((dashboardMonth || state.today.slice(0, 7)) + "-01");
      d.setMonth(d.getMonth() + (name === "activity-prev" ? -1 : 1));
      const month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      if (month >= "1900-01" && month <= "2050-12") dashboardMonth = month;
      updateActivityCalendar();
      break;
    }
    case "journal-prev":
      journalDate =
        journalDate <= "1900-01-01" ? "1900-01-01" : addDays(journalDate, -1);
      render();
      break;
    case "journal-next":
      journalDate =
        journalDate >= "2050-12-31" ? "2050-12-31" : addDays(journalDate, 1);
      render();
      break;
    case "journal-today":
      journalDate = state.today;
      render();
      break;
    case "reset-dialog":
      resetDialog();
      break;
    case "select-pr":
      prId = id;
      render();
      $("#strength-chart-card").scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "start",
      });
      break;
    case "exercise-history": {
      const entries = state.entries.filter(
        (e) =>
          e.kind === "workout" &&
          e.exercises.some((item) => item.exercise_id === id),
      );
      modal(
        byId[id].name,
        "Edit or delete the original workout to update its sets and calculated records.",
        `<div class="record-history">${entries
          .map(
            (entry) =>
              `<div class="workout-exercise">${workoutRow(entry)}<p class="small muted section-space">${entry.exercises
                .filter((item) => item.exercise_id === id)
                .flatMap((item) => item.sets)
                .map((set) =>
                  set.seconds
                    ? `${n(set.seconds)} sec`
                    : `${set.weight ? n(set.weight) + " kg" : "Bodyweight"} × ${n(set.reps)} reps`,
                )
                .join(" · ")}</p></div>`,
          )
          .join("")}</div>`,
      );
      break;
    }
    case "goal-add-supplement": {
      const input = $("#goal-new-supplement"),
        result = await api("supplements", { name: input.value });
      syncSupplementGoals();
      state.profile.supplements = result.options;
      let option = [
        ...document.querySelectorAll('[name="consistency_supplements"]'),
      ].find((el) => el.value === result.name);
      if (!option) {
        $("#goal-supplement-choices").insertAdjacentHTML(
          "beforeend",
          supplementGoalChoice(result.name, true),
        );
        option = [
          ...document.querySelectorAll('[name="consistency_supplements"]'),
        ].find((el) => el.value === result.name);
      }
      option.checked = true;
      drawSupplementGoals();
      input.value = "";
      $("#goal-supplement-status").textContent =
        "Added to your list. Set its target and save goals.";
      break;
    }
    case "save-supplement-option": {
      const input = $("#new-supplement-name");
      const result = await api("supplements", { name: input.value });
      await refresh(false);
      const select = $("#entry-name");
      if (
        !Array.from(select.options).some(
          (option) => option.value === result.name,
        )
      ) {
        const option = document.createElement("option");
        option.value = result.name;
        option.textContent = result.name;
        select.add(option, select.options[select.options.length - 1]);
      }
      select.value = result.name;
      $("#entry-unit").value = supplementLogUnit(result.name);
      $("#custom-supplement-box").hidden = true;
      input.required = false;
      $("#form-error").textContent = "";
      $("#entry-amount").focus();
      toast("Supplement saved to your list");
      break;
    }
    case "close-modal":
      await closeModal();
      break;
    case "new-workout":
      openWorkout();
      break;
    case "new-plan":
      openWorkout("plan");
      break;
    case "new-sleep":
      simpleForm("sleep");
      break;
    case "new-meal":
      simpleForm("meal");
      break;
    case "new-creatine":
      simpleForm("creatine");
      break;
    case "new-supplement":
      simpleForm("supplement");
      break;
    case "new-body":
      simpleForm("body", { date: state.today });
      break;
    case "quick-supplement":
      simpleForm(
        el.dataset.name.toLowerCase() === "creatine"
          ? "creatine"
          : "supplement",
        {
          name: el.dataset.name,
          amount:
            el.dataset.name.toLowerCase() === "creatine"
              ? state.profile.goals.creatine.unit === "day" &&
                state.profile.goals.creatine.period === 1
                ? state.profile.goals.creatine.amount
                : ""
              : "",
          unit: supplementLogUnit(el.dataset.name),
        },
      );
      break;
    case "edit-entry": {
      if (activeAiPreview?.entries.some((entry) => entry.id === id)) {
        await openAiLog("any", activeAiPreview.draft_id);
        break;
      }
      const e = state.entries.find((e) => e.id === id);
      if (["workout", "plan"].includes(e.kind)) openWorkout(e.kind, e);
      else simpleForm(e.kind, e);
      break;
    }
    case "delete-entry":
      modal(
        "Delete this entry?",
        "This removes the entry from your journal. Export a backup first if you need a copy.",
        `<div class="actions">${button("Keep entry", "close-modal", "secondary")}${button("Delete entry", "confirm-delete", "danger", `data-id="${id}"`)}</div>`,
      );
      break;
    case "confirm-delete":
      await api("delete", { id });
      await closeModal();
      await refresh();
      toast("Entry deleted");
      break;
    case "workout-tab":
      workoutTab = el.dataset.tab;
      render();
      break;
    case "library-next":
      libraryPage++;
      $("#library-results").innerHTML = libraryResults();
      window.scrollTo({ top: 0 });
      break;
    case "library-prev":
      libraryPage--;
      $("#library-results").innerHTML = libraryResults();
      window.scrollTo({ top: 0 });
      break;
    case "exercise-detail":
      detailExercise(id);
      break;
    case "pick-exercise": {
      syncWorkout();
      if (!workoutForm.exercises.some((e) => e.exercise_id === id)) {
        let item = { exercise_id: id };
        if (workoutForm.kind !== "plan") {
          item = WorkoutHistory.makeExercise(el.dataset.recall === "true" ? state.entries : [], id, workoutForm.date, byId, workoutForm.id);
          if (el.dataset.recall !== "true") item.sets = [{ weight: 0, reps: 0, seconds: 0 }];
        }
        workoutForm.exercises.push(item);
      }
      drawWorkout();
      break;
    }
    case "request-blank-workout":
      confirmWorkoutReplace("blank-workout");
      break;
    case "request-previous-workout":
      confirmWorkoutReplace("previous-workout");
      break;
    case "cancel-workout-replace":
      resetWorkoutOptions();
      $("#workout-options").open = false;
      $("#workout-options summary").focus();
      break;
    case "blank-workout":
      syncWorkout();
      workoutForm.exercises = [];
      workoutForm.notes = "";
      workoutForm.duration = "";
      delete workoutForm._copied_from;
      drawWorkout();
      break;
    case "previous-workout": {
      syncWorkout();
      const previous = WorkoutHistory.latestWorkout(
        state.entries,
        workoutForm.date,
        workoutForm.id,
      );
      if (previous) {
        workoutForm.exercises = previous.exercises.map((item) =>
          WorkoutHistory.normalize(item, byId),
        );
        drawWorkout();
      }
      break;
    }
    case "recall-exercise": {
      syncWorkout();
      const index = Number(el.dataset.index),
        id = workoutForm.exercises[index].exercise_id;
      workoutForm.exercises[index] = WorkoutHistory.makeExercise(
        state.entries,
        id,
        workoutForm.date,
        byId,
        workoutForm.id,
      );
      drawWorkout();
      break;
    }
    case "remove-exercise":
      syncWorkout();
      workoutForm.exercises.splice(Number(el.dataset.index), 1);
      drawWorkout();
      break;
    case "add-set": {
      syncWorkout();
      {
        const sets = workoutForm.exercises[el.dataset.index].sets;
        sets.push({
          ...(sets[sets.length - 1] || {
            weight: 0,
            reps:
              workoutForm.exercises[el.dataset.index].tracking === "time"
                ? 0
                : 10,
            seconds:
              workoutForm.exercises[el.dataset.index].tracking === "time"
                ? 30
                : 0,
          }),
        });
      }
      // Append in place: rebuilding the dialog resets its scroll and focus.
      const setDialog = $("#modal"),
        setScroll = setDialog.scrollTop;
      el.insertAdjacentHTML(
        "beforebegin",
        workoutSetRow(
          workoutForm.exercises[el.dataset.index],
          Number(el.dataset.index),
          workoutForm.exercises[el.dataset.index].sets.length - 1,
        ),
      );
      el.previousElementSibling.querySelector("input")?.focus({ preventScroll: true });
      setDialog.scrollTop = setScroll;
      requestAnimationFrame(() => {
        if (setDialog.open) setDialog.scrollTop = setScroll;
      });
      break;
    }
    case "remove-set":
      syncWorkout();
      workoutForm.exercises[el.dataset.index].sets.splice(
        Number(el.dataset.setIndex),
        1,
      );
      drawWorkout();
      break;
    case "copy-plan":
      syncWorkout();
      openWorkout("plan", {
        ...workoutForm,
        id: undefined,
        date: addDays(state.today, 1),
      });
      break;
    case "start-plan": {
      let e = state.entries.find((e) => e.id === id);
      journalDate = e.date;
      openWorkout("workout", { ...e, id: undefined, date: e.date });
      break;
    }
    case "start-current-plan":
      syncWorkout();
      openWorkout("workout", {
        ...workoutForm,
        id: undefined,
        date: journalDate,
      });
      break;
    case "preview-ai-draft":
      await showAiPreview(id);
      break;
    case "approve-chat-draft":
      await sendChat({ preventDefault() {} }, id);
      break;
    case "view-approved-track":
      activeAiPreview = null;
      journalDate = el.dataset.date;
      await refresh(false);
      location.hash = "track";
      render();
      $(".daily-journal")?.scrollIntoView({ block: "start" });
      break;
    case "ai-log-chooser":
      openAiLogChooser();
      break;
    case "body-map-range":
      bodyMapMode = el.dataset.mode === "day" ? "day" : "week";
      $("#insights-body-map").innerHTML = insightsBodyMapInner();
      BodyMap.bind($("#insights-body-map"));
      $(`[data-action="body-map-range"][data-mode="${bodyMapMode}"]`).focus();
      break;
    case "ai-log":
      await openAiLog(el.dataset.kind || "any");
      break;
    case "approve-preview":
      el.disabled = true;
      try {
        await api("approve", { id });
      } catch (error) {
        el.disabled = false;
        throw error;
      }
      activeAiPreview = null;
      await refresh();
      toast("Approved and saved to your journal");
      break;
    case "revert-preview":
      await api("dismiss", { id });
      activeAiPreview = null;
      await refresh();
      break;
    case "change-preview":
      await openAiLog("any", id);
      break;
    case "review-draft": {
      const d = state.drafts.find((d) => d.id === id);
      if (d.kind === "plan") openWorkout("plan", d.data, d);
      else simpleForm(d.kind, d.data, d);
      break;
    }
    case "dismiss-draft":
      await api("dismiss", { id });
      await refresh();
      toast("Draft dismissed");
      break;
    case "coach-cancel-connection":
      cancelCoachConnection();
      break;
    case "coach-load-models":
      await loadCoachModels();
      break;
    case "coach-test-connection":
      await testCoachConnection(
        state.connections.provider || "ollama",
        $("#coach-model-status"),
      );
      break;
    case "test-connection":
      await testCoachConnection(
        el.dataset.provider,
        $(`#${el.dataset.provider}-save-status`),
      );
      break;
    case "load-models": {
      const provider = el.dataset.provider;
      el.disabled = true;
      try {
        await saveConnection(provider);
        const data = await api("models", { provider });
        $(`#${provider}-models`).innerHTML = data.models
          .map((m) => `<option value="${esc(m)}"></option>`)
          .join("");
        $(`#${provider}-model-status`).textContent =
          `${data.models.length} available models loaded. Choose a chat model from the model field, then save.`;
        $(`#${provider}-model`).focus();
      } finally {
        el.disabled = false;
      }
      break;
    }
    case "coach-skills": {
      const skills = await api("coach-skills");
      modal(
        "Your coach’s skill library",
        "Focused guides with source links. Research mode loads relevant guides and searches live evidence; quick chat uses concise general coaching guidance.",
        `<div class="skill-library">${skills.map((skill) => `<details><summary>${esc(skill.title)}</summary><p class="skill-content">${esc(skill.content.replace(/^#.*\n/, ""))}</p>${skill.sources.map((url) => `<a class="link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Read the source ↗</a>`).join("")}</details>`).join("")}</div>`,
      );
      break;
    }
    case "preview-context": {
      const ctx = await api("context", { date: journalDate });
      modal(
        "What your coach receives",
        "Available journal context is shown below. Each message sends only relevant details and up to three recent exchanges. Meals do not attach workout logs or PRs; assessments can use journal summaries. Research adds selected guides and exercise IDs when needed. Older context may be shortened to fit. No API keys or unrelated files.",
        `<pre class="review-data">${esc(JSON.stringify(ctx, null, 2))}</pre>`,
      );
      break;
    }
    case "export": {
      const data = await api("export");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `blaze-athletics-${state.today}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("Journal export downloaded");
      break;
    }
    case "ask-food":
    case "ask-plan":
    case "ask-progress":
      if (name === "ask-plan" && $("#workout-form")) {
        syncWorkout();
        journalDate = workoutForm.date;
      }
      await closeModal();
      prepareCoachMessage(
        name === "ask-food"
          ? "Help me estimate the protein in my meal. I ate "
          : name === "ask-plan"
            ? `Plan an exercise-only session for ${journalDate}, based on my goals and recent sessions. My focus: `
            : "Assess my progress",
      );
      location.hash = "coach";
      break;
  }
}
document.addEventListener("pointerover", event => {
  if (event.pointerType === "touch") return;
  const cell = event.target.closest(".heat-cell[data-date]");
  if (cell) showHabitDetails(cell);
  else if (event.target.closest("#habit-day-tooltip")) clearTimeout(habitTooltipTimer);
});
document.addEventListener("pointerout", event => {
  if (event.target.closest(".heat-cell, #habit-day-tooltip")) deferHideHabitDetails();
});
document.addEventListener("focusin", event => {
  const cell = event.target.closest(".heat-cell[data-date]");
  if (cell) showHabitDetails(cell);
});
document.addEventListener("focusout", event => {
  if (event.target.closest(".heat-cell")) deferHideHabitDetails();
});
document.addEventListener("scroll", event => {
  const tooltip = $("#habit-day-tooltip");
  if (!habitTooltipCell || !tooltip || tooltip.contains(event.target)) return;
  const anchor = habitTooltipCell.getBoundingClientRect();
  if (anchor.bottom < 0 || anchor.top > window.innerHeight) hideHabitDetails();
  else positionHabitDetails(habitTooltipCell, tooltip);
}, true);
window.addEventListener("resize", hideHabitDetails);
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && habitTooltipCell) {
    event.preventDefault();
    event.stopPropagation();
    hideHabitDetails();
  }
}, true);
document.addEventListener("click", (event) => {
  const step = event.target.closest('[data-action="step-set"]');
  if (step) {
    const input = step.closest(".set-number").querySelector("input");
    stepWorkoutNumber(input, Number(step.dataset.direction));
    input.focus({ preventScroll: true });
    return;
  }
  const chatOptions = $(".chat-options");
  if (chatOptions?.open && !chatOptions.contains(event.target))
    chatOptions.open = false;
  const options = $("#workout-options");
  if (options?.open && !options.contains(event.target)) options.open = false;
  const el = event.target.closest("[data-page],[data-action],[data-prompt]");
  if (!el) return;
  if (el.dataset.page) {
    location.hash = el.dataset.page;
    return;
  }
  if (el.dataset.prompt) {
    prepareCoachMessage(el.dataset.prompt);
    return;
  }
  Promise.resolve(action(el.dataset.action, el)).catch((error) =>
    toast(error.message),
  );
});
document.addEventListener(
  "keydown",
  (event) => {
    if (event.target.matches?.("input[data-set]") &&
        ["ArrowUp", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      stepWorkoutNumber(event.target, event.key === "ArrowUp" ? 1 : -1);
      return;
    }
    const prOptions = $("#pr-exercise-options");
    if (event.target.id === "pr-exercise-filter" || event.target.closest?.("#pr-exercise-options")) {
      if (event.key === "Escape" && recordSuggestionsOpen) {
        event.preventDefault();
        event.stopPropagation();
        recordSuggestionsOpen = false;
        updateExerciseRecords("pr-exercise-filter");
        return;
      }
      if (["ArrowDown", "ArrowUp"].includes(event.key) && prOptions && !prOptions.hidden) {
        const options = [...prOptions.querySelectorAll("button")];
        const current = options.indexOf(event.target);
        const next = current < 0 ? (event.key === "ArrowDown" ? 0 : options.length - 1) : current + (event.key === "ArrowDown" ? 1 : -1);
        event.preventDefault();
        options[(next + options.length) % options.length]?.focus();
        return;
      }
    }
    if (
      event.target.id === "chat-input" &&
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.isComposing &&
      event.keyCode !== 229
    ) {
      event.preventDefault();
      if (!event.repeat && !chatIsBusy() && !coachModelBusy)
        $("#chat-form")?.requestSubmit();
      return;
    }
    const options = $("#workout-options");
    if (event.key === "Escape" && options?.open) {
      event.preventDefault();
      event.stopPropagation();
      options.open = false;
      options.querySelector("summary").focus();
    }
  },
  true,
);
// Blur before the browser's native wheel stepping, allowing the page to scroll.
document.addEventListener("wheel", (event) => {
  const input = event.target.closest?.('input[type="number"]');
  if (input === document.activeElement) input.blur();
}, { capture: true, passive: true });
document.addEventListener("input", (event) => {
  const el = event.target;
  if (el.id === "chat-input") {
    chatComposerDraft = el.value;
    resizeChatComposer();
  }
  if (el.id === "coach-custom-model") updateCoachConnectionState();
  if (el.id === "ai-log-input" && $("#ai-log-form"))
    $("#ai-log-form").dataset.requestId = "";
  if (el.id === "entry-unit") { el.dataset.manual = "true"; syncSupplementAmount(); }
  if (el.id === "entry-amount") { el.dataset.manual = "true"; delete el.dataset.default; }
  if (el.id === "exercise-search") {
    libraryQuery = el.value;
    libraryPage = 0;
    $("#library-results").innerHTML = libraryResults();
  }
  if (el.id === "picker-search") {
    $("#picker-results").innerHTML = pickerResults(el.value);
    scheduleExerciseSearch("picker", el.value);
  }
  if (el.id === "pr-exercise-filter") searchExerciseRecords(el.value);
});
document.addEventListener("change", (event) => {
  if (event.target.classList?.contains("review-date")) {
    if (event.target.checkValidity()) {
      reviewDate = event.target.value;
      updateReviewPanels(`#${event.target.id}`);
    }
    return;
  }
  if (["pr-exercise-filter", "pr-body-filter"].includes(event.target.id)) {
    if (event.target.id === "pr-exercise-filter") {
      const exact = Object.keys(state.insights.prs).find(id => byId[id]?.name.toLowerCase() === event.target.value.toLowerCase());
      if (exact) { recordExercise = exact; recordSuggestionsOpen = false; }
      else return;
    } else recordBodyPart = event.target.value;
    updateExerciseRecords(event.target.id);
    if (recordSearchQuery && !recordExercise) scheduleExerciseSearch("records", recordSearchQuery);
    return;
  }
  if (event.target.id === "activity-metric") {
    dashboardMetric = event.target.value;
    updateActivityCalendar();
    return;
  }
  if (event.target.id === "activity-month") {
    if (event.target.checkValidity()) dashboardMonth = event.target.value;
    updateActivityCalendar();
    return;
  }

  if (event.target.id === "body-map-date") {
    if (!event.target.checkValidity()) {
      event.target.value = bodyMapDate || journalDate || state.today;
      return;
    }
    bodyMapDate = event.target.value;
    $("#insights-body-map").innerHTML = insightsBodyMapInner();
    BodyMap.bind($("#insights-body-map"));
    $("#body-map-date").focus();
    return;
  }
  if (event.target.id === "coach-research") {
    chatResearchMode = event.target.checked;
    if ($("#chat-mode-label"))
      $("#chat-mode-label").textContent = chatResearchMode
        ? "Research on"
        : "Quick chat";
  }
  const el = event.target;
  if (el.id === "coach-provider") {
    $("#coach-model").innerHTML = coachModelOptions(el.value);
    $("#coach-custom-model-field").hidden = true;
    $("#coach-custom-model").required = false;
    updateCoachConnectionState();
    loadCoachModels();
  }
  if (el.id === "coach-model") {
    const custom = el.value === "__custom__";
    $("#coach-custom-model-field").hidden = !custom;
    $("#coach-custom-model").required = custom;
    $("#coach-model-status").textContent =
      "New selection is not active yet. Select Switch connection to apply it.";
    updateCoachConnectionState();
  }
  if (el.id === "entry-period") {
    $("#night-sleep-fields").hidden = el.value !== "night";
    if (el.value !== "night") $("#entry-continuous_hours").value = "";
  }
  if (el.name === "consistency_supplements") drawSupplementGoals();
  if (el.dataset.goalField === "unit")
    el
      .closest("[data-supplement-goal]")
      .querySelector('[data-goal-field="period"]').max = {
      day: "365",
      week: "52",
      month: "120",
    }[el.value];
  if (/^goal-(workout|protein|creatine)-unit$/.test(el.id)) {
    $(`#${el.id.replace("-unit", "-period")}`).max = {
      day: "365",
      week: "52",
      month: "120",
    }[el.value];
  }
  if (el.id === "muscle-filter" || el.id === "equipment-filter") {
    libraryMuscle = $("#muscle-filter").value;
    libraryEquipment = $("#equipment-filter").value;
    libraryPage = 0;
    $("#library-results").innerHTML = libraryResults();
  }
  if (el.id === "entry-name" && $("#custom-supplement-box")) {
    const adding = el.value === "__new__";
    $("#custom-supplement-box").hidden = !adding;
    $("#new-supplement-name").required = adding;
    if (adding) $("#new-supplement-name").focus();
    else {
      $("#entry-unit").dataset.manual = "";
      $("#entry-unit").value = supplementLogUnit(el.value);
      syncSupplementAmount();
      refreshSupplementUnit();
    }
  }
  if (el.dataset.loadMode !== undefined) {
    syncWorkout();
    const item = workoutForm.exercises[Number(el.dataset.loadMode)];
    item.load_mode = el.value;
    if (item.load_mode === "bodyweight")
      for (const set of item.sets) set.weight = 0;
    drawWorkout();
  }
  if (el.dataset.tracking !== undefined) {
    syncWorkout();
    const item = workoutForm.exercises[Number(el.dataset.tracking)];
    item.tracking = el.value;
    for (const set of item.sets) {
      if (item.tracking === "time") {
        set.reps = 0;
        set.seconds = 30;
      } else {
        set.seconds = 0;
        set.reps = 10;
      }
    }
    drawWorkout();
  }
  if (el.id === "entry-date" && $("#ai-log-form"))
    $("#ai-log-form").dataset.requestId = "";
  if (el.id === "entry-date" && $("#workout-form")) {
    syncWorkout();
    if (workoutForm.date)
      $("#modal h2").textContent = sessionTitle(workoutForm.date);
  }
  if (el.id === "nutrition-date" || el.id === "journal-date") {
    if (!el.checkValidity()) {
      el.value = journalDate;
      toast("Choose a date from 1900 through 2050.");
      return;
    }
    journalDate = el.value || state.today;
    render();
  }
  if (el.id === "body-area-select") {
    selectedBodyPart = el.value;
    $("#area-breakdown").innerHTML = areaBreakdown(selectedBodyPart);
  }
  if (el.id === "pr-select") {
    prId = el.value;
    render();
  }
  if (el.id === "intake-metric") {
    intakeMetric = el.value === "creatine" ? "creatine" : "protein";
    $("#intake-panel").innerHTML = intakePanel();
    $("#intake-metric").focus({ preventScroll: true });
  }
});
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (form.id === "chat-form") {
    sendChat(event);
    return;
  }
  event.preventDefault();
  const submit = form.querySelector("[type=submit]");
  if (submit) submit.disabled = true;
  try {
    if (form.id === "coach-consent-form") {
      if (!form.elements.agreement.checked)
        throw Error("Tick the agreement to enable the coach.");
      await saveCoachAgreement(true);
    } else if (form.id === "coach-model-form") {
      await saveCoachModel();
    } else if (form.id === "reset-form") {
      await api("reset", {
        confirm: form.elements.confirm.value,
        clear_connections: form.elements.clear_connections.checked,
      });
      journalDate = state.today;
      chatComposerDraft = "";
      chatResearchMode = false;
      chatLoggingKind = null;
      chatRevisionId = null;
      optimisticChat = null;
      prId = undefined;
      workoutForm = null;
      formDraft = null;
      await closeModal();
      await refresh();
      toast("Journal reset. Ready for a fresh start.");
    } else if (form.id === "simple-entry-form") {
      let data = {
        ...Object.fromEntries(new FormData(form)),
        kind: form.dataset.kind,
        source: form.dataset.source,
      };
      if (data.kind === "supplement" && data.name === "__new__")
        throw Error("Save your new supplement name to the list first.");
      if (form.dataset.id) data.id = form.dataset.id;
      if (formDraft) await api("approve", { id: formDraft.id, data });
      else await api("entry", data);
      journalDate = data.date;
      await closeModal();
      await refresh();
      toast("Entry saved to your journal");
    } else if (form.id === "workout-form") {
      syncWorkout();
      if (formDraft)
        await api("approve", { id: formDraft.id, data: workoutForm });
      else await api("entry", workoutForm);
      journalDate = workoutForm.date;
      await closeModal();
      await refresh();
      toast(
        workoutForm.kind === "plan"
          ? "Workout plan saved"
          : "Workout logged. A little stronger.",
      );
    } else if (form.id === "goals-form") {
      const fields = new FormData(form);
      const goals = Object.fromEntries(
        ["workout", "protein", "creatine"].map((key) => [
          key,
          {
            amount: fields.get(key + "_amount"),
            period: fields.get(key + "_period"),
            unit: fields.get(key + "_unit"),
          },
        ]),
      );
      syncSupplementGoals();
      await api("profile", {
        goals,
        sleep_goal: fields.get("sleep_goal"),
        night_hours_goal: fields.get("night_hours_goal"),
        night_sleep_goal: fields.get("night_sleep_goal"),
        supplement_goals: Object.fromEntries(
          Object.entries(supplementGoalDraft).filter(([name]) =>
            fields.getAll("consistency_supplements").includes(name),
          ),
        ),
        consistency_supplements: fields.getAll("consistency_supplements"),
      });
      await refresh();
      toast("Your goals are saved");
    } else if (form.id === "profile-form") {
      const data = Object.fromEntries(new FormData(form));
      data.supplements = data.supplements
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await api("profile", data);
      await refresh();
      toast("Your profile is saved");
    } else if (form.dataset.connection) {
      await saveConnection(form.dataset.connection);
      toast("Connection saved");
    } else if (form.id === "research-form") {
      $("#research-results").innerHTML =
        '<p class="muted section-space">Searching papers…</p>';
      const data = await api("research", {
        query: new FormData(form).get("query"),
      });
      $("#research-results").innerHTML = data.papers.length
        ? papersHtml(data.papers)
        : '<p class="notice section-space">No matching papers. Try a broader search.</p>';
    }
  } catch (error) {
    const err =
      $("#form-error") ||
      $("#goals-error") ||
      (form.id === "coach-model-form" ? $("#coach-model-status") : null) ||
      (form.id === "coach-consent-form" ? $("#coach-consent-error") : null) ||
      (form.dataset.connection
        ? $(`#${form.dataset.connection}-save-status`)
        : null);
    if (err) err.textContent = error.message;
    else toast(error.message);
    if (form.id === "research-form")
      $("#research-results").textContent = error.message;
  } finally {
    if (submit) submit.disabled = false;
    if (form.id === "coach-model-form") updateCoachConnectionState();
  }
});
window.addEventListener("pagehide", () => voiceInput.cancel());
window.addEventListener("hashchange", () => {
  if (state) {
    render();
    window.scrollTo(0, 0);
  }
});
(async () => {
  try {
    await refresh(false);
    catalog = await api("exercises");
    byId = Object.fromEntries(catalog.map((e) => [e.id, e]));
    render();
  } catch (error) {
    $("#content").innerHTML =
      `<div class="notice">Could not load your journal: ${esc(error.message)}. Refresh this page to retry.</div>`;
  }
})();
