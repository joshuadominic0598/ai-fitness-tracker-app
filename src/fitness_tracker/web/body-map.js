/* Original SVG anatomy illustration and user-relative training-emphasis calculations. */
(function (root) {
  "use strict";
  const groups = [
    "Chest",
    "Shoulders",
    "Back",
    "Biceps",
    "Triceps",
    "Forearms",
    "Abs",
    "Glutes",
    "Quads",
    "Hamstrings",
    "Adductors",
    "Abductors",
    "Calves",
    "Neck",
  ];
  const muscles = {
    chest: "Chest",
    "upper chest": "Chest",
    "lower chest": "Chest",
    shoulders: "Shoulders",
    lats: "Back",
    "middle back": "Back",
    "lower back": "Back",
    traps: "Back",
    biceps: "Biceps",
    triceps: "Triceps",
    forearms: "Forearms",
    abdominals: "Abs",
    "upper abs": "Abs",
    "lower abs": "Abs",
    obliques: "Abs",
    glutes: "Glutes",
    quadriceps: "Quads",
    hamstrings: "Hamstrings",
    adductors: "Adductors",
    abductors: "Abductors",
    calves: "Calves",
    neck: "Neck",
  };
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const n = (value) =>
    Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
  const median = (values) => {
    if (!values.length) return 1;
    const sorted = [...values].sort((a, b) => a - b),
      middle = Math.floor(sorted.length / 2);
    return sorted.length % 2
      ? sorted[middle]
      : (sorted[middle - 1] + sorted[middle]) / 2;
  };
  function period(day, mode = "day") {
    const d = new Date(day + "T12:00:00Z");
    if (mode === "week")
      d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    const start = d.toISOString().slice(0, 10);
    if (mode === "week") d.setUTCDate(d.getUTCDate() + 6);
    return { start, end: d.toISOString().slice(0, 10) };
  }
  function empty() {
    return Object.fromEntries(
      groups.map((group) => [
        group,
        {
          name: group,
          primary: 0,
          secondary: 0,
          reps: 0,
          seconds: 0,
          exposure: 0,
          exercises: [],
        },
      ]),
    );
  }
  function summarize(workouts, catalog, history = workouts, options = {}) {
    const end =
      options.end ||
      workouts
        .map((w) => w.date)
        .sort()
        .at(-1) ||
      "2050-12-31";
    const since = new Date(end + "T12:00:00Z");
    since.setUTCDate(since.getUTCDate() - 83);
    const recent = history.filter(
      (w) =>
        w.kind === "workout" &&
        w.date <= end &&
        w.date >= since.toISOString().slice(0, 10),
    );
    const calibration = {};
    for (const w of recent)
      for (const ex of w.exercises || []) {
        const c = (calibration[ex.exercise_id] ||= { reps: [], seconds: [] });
        for (const s of ex.sets || []) {
          if (s.seconds > 0) c.seconds.push(s.seconds);
          else if (s.reps > 0) c.reps.push(s.reps);
        }
      }
    function tally(list) {
      const areas = empty();
      for (const workout of list.filter((w) => w.kind === "workout"))
        for (const ex of workout.exercises || []) {
          const exercise = catalog[ex.exercise_id];
          if (!exercise) continue;
          const primary = new Set(
            exercise.bodyParts ||
              (exercise.primaryMuscles || []).map((m) => muscles[m]),
          );
          const secondary = new Set(
            (exercise.secondaryMuscles || [])
              .map((m) => muscles[m])
              .filter((g) => !primary.has(g)),
          );
          const c = calibration[ex.exercise_id] || { reps: [], seconds: [] };
          const repsBase = median(c.reps),
            secondsBase = median(c.seconds);
          const sets = (ex.sets || []).filter(
            (s) => s.reps > 0 || s.seconds > 0,
          );
          const reps = sets.reduce(
            (sum, s) => sum + (s.seconds > 0 ? 0 : s.reps || 0),
            0,
          );
          const seconds = sets.reduce((sum, s) => sum + (s.seconds || 0), 0);
          const exposure = sets.reduce(
            (sum, s) =>
              sum +
              (s.seconds > 0
                ? s.seconds / secondsBase
                : (s.reps || 0) / repsBase),
            0,
          );
          for (const [set, isPrimary] of [
            [primary, true],
            [secondary, false],
          ])
            for (const group of set) {
              if (!areas[group] || !sets.length) continue;
              const area = areas[group];
              area[isPrimary ? "primary" : "secondary"] += sets.length;
              area.reps += reps;
              area.seconds += seconds;
              area.exposure += exposure * (isPrimary ? 1 : 0.5);
              const existing = area.exercises.find(
                (e) => e.id === ex.exercise_id,
              );
              if (existing) {
                existing.sets += sets.length;
                existing.reps += reps;
                existing.seconds += seconds;
              } else
                area.exercises.push({
                  id: ex.exercise_id,
                  name: exercise.name,
                  primary: isPrimary,
                  sets: sets.length,
                  reps,
                  seconds,
                });
            }
        }
      return areas;
    }
    const areas = tally(workouts),
      windows = new Map();
    for (const w of recent) {
      const key = period(w.date, options.mode || "day").start;
      if (!windows.has(key)) windows.set(key, []);
      windows.get(key).push(w);
    }
    const peaks = [...windows.values()].map((ws) =>
      Math.max(...Object.values(tally(ws)).map((a) => a.exposure)),
    );
    const currentMax = Math.max(
      0,
      ...Object.values(areas).map((a) => a.exposure),
    );
    const reference = Math.max(
      currentMax,
      windows.size > 1 ? median(peaks) : 0,
      1,
    );
    for (const a of Object.values(areas)) a.level = a.exposure / reference;
    return {
      areas,
      reference,
      personalized: windows.size > 1,
      mode: options.mode || "day",
      active: Object.values(areas)
        .filter((a) => a.primary + a.secondary > 0)
        .sort((a, b) => b.exposure - a.exposure),
      sessions: new Set(
        workouts.filter((w) => w.kind === "workout").map((w) => w.date),
      ).size,
    };
  }

  // Original illustration: one neutral silhouette, with independently interactive muscle regions.
  const silhouette =
    "M88 44L88 53Q84 59 73 62L60 67Q48 72 44 87L35 120L28 153L18 187L10 204Q7 211 12 216L22 220Q27 217 29 210L35 193L45 168L54 137L62 116L65 144L63 172Q59 189 62 212L65 253L70 294Q72 310 69 328L70 367L74 407L71 430L58 438Q55 444 64 446L84 443Q90 442 88 433L87 410L92 368L96 332L95 302L100 250L105 302L104 332L108 368L113 410L112 433Q110 442 116 443L136 446Q145 444 142 438L129 430L126 407L130 367L131 328Q128 310 130 294L135 253L138 212Q141 189 137 172L135 144L138 116L146 137L155 168L165 193L171 210Q173 217 178 220L188 216Q193 211 190 204L182 187L172 153L165 120L156 87Q152 72 140 67L127 62Q116 59 112 53L112 44Z";
  const front = {
    Neck: ["M91 47L109 47L111 59L100 65L89 59Z"],
    Shoulders: ["M75 64Q55 66 48 88L44 103Q51 92 65 85L84 72Z"],
    Chest: ["M98 75Q86 67 73 75Q62 81 65 98Q77 111 98 103Z"],
    Biceps: ["M56 100Q45 111 42 133L41 144Q54 142 60 119L63 103Z"],
    Triceps: ["M43 105L38 124L34 140L39 145L44 125L51 105Z"],
    Forearms: ["M39 149Q33 148 29 160L19 190L25 198L36 178L43 153Z"],
    Abs: ["M98 111L85 111Q78 124 83 144L83 164Q86 178 98 187Z"],
    Quads: ["M69 209Q79 207 94 215L94 240L88 280Q78 295 73 276L68 233Z"],
    Adductors: ["M96 201L99 226L96 253L91 235L89 215Z"],
    Abductors: ["M65 184L72 190L69 206L65 215L63 201Z"],
    Calves: ["M76 314Q85 320 87 335L82 386L77 393L74 350Z"],
  };
  const back = {
    Neck: ["M91 47L109 47L111 59L100 65L89 59Z"],
    Back: [
      "M98 62L79 67L63 77L81 88L90 122L98 136Z",
      "M65 91L79 93L94 140L88 165L79 177L65 152Z",
      "M98 147L89 169L98 182Z",
    ],
    Shoulders: ["M59 76Q48 81 44 103L57 96L70 85Z"],
    Triceps: ["M44 110Q53 101 59 104L61 120L51 143L39 149Z"],
    Forearms: ["M39 154Q33 153 29 164L19 190L25 198L36 178L43 156Z"],
    Glutes: ["M97 185Q77 178 68 193L65 212Q79 225 97 216Z"],
    Hamstrings: ["M67 222L96 225L92 266Q85 287 77 289L72 268Z"],
    Adductors: ["M97 224L100 241L96 268L92 275L93 247Z"],
    Abductors: ["M64 183L70 188L66 203L63 211L61 199Z"],
    Calves: ["M77 310Q91 311 91 339L83 379Q79 392 76 375L72 339Z"],
  };
  const colors = ["#527bda", "#8370ed", "#b17af3", "#e28ccf"];
  const color = (area) =>
    area.exposure > 0
      ? colors[Math.min(3, Math.floor(area.level * 4))]
      : "#353348";
  function figure(view, report, selected) {
    const shapes = view === "Front" ? front : back;
    return `<figure class="body-map-figure"><figcaption>${view}</figcaption><svg viewBox="0 0 200 455" aria-label="${view} body muscle map"><ellipse class="body-silhouette" cx="100" cy="25" rx="18" ry="22"/><path class="body-silhouette" d="${silhouette}"/>${Object.entries(
      shapes,
    )
      .map(([group, paths]) => {
        const a = report.areas[group];
        const mirrored = group !== "Neck";
        const pathMarkup = paths
          .map(
            (d) =>
              `<path d="${d}"/>${mirrored ? `<path d="${d}" transform="translate(200 0) scale(-1 1)"/>` : ""}`,
          )
          .join("");
        return `<g class="body-region ${a.exposure ? "has-work" : ""} ${group === selected ? "is-selected" : ""}" role="button" tabindex="0" data-muscle="${group}" aria-pressed="${group === selected}" aria-label="${group}: ${a.primary} primary sets, ${a.secondary} secondary sets" style="--muscle-fill:${color(a)}"><title>${group} · ${a.primary} primary sets · ${a.secondary} secondary sets</title>${pathMarkup}</g>`;
      })
      .join(
        "",
      )}<path class="body-detail-line" d="M100 69V185${view === "Front" ? "M84 131H116M84 153H116" : "M100 184V216"}"/></svg></figure>`;
  }
  function detail(area) {
    return `<div class="eyebrow">BODY AREA</div><h3>${esc(area.name)}</h3><div class="body-area-stats"><div><strong>${n(area.primary)}</strong><span>primary sets</span></div><div><strong>${n(area.secondary)}</strong><span>secondary sets</span></div><div><strong>${n(area.reps)}</strong><span>reps${area.seconds ? ` · ${n(area.seconds)} sec` : ""}</span></div></div>${area.exercises.length ? `<ul class="body-area-exercises">${area.exercises.map((e) => `<li><span>${esc(e.name)}</span><small>${e.sets} ${e.primary ? "primary" : "secondary"} ${e.sets === 1 ? "set" : "sets"}</small></li>`).join("")}</ul>` : '<p class="small muted">No targeting sets recorded for this area in this period.</p>'}`;
  }
  const reports = new Map();
  function render(report, options = {}) {
    const id = options.id || "workout-body-map",
      selected = report.active[0]?.name || "Chest";
    reports.set(id, report);
    return `<section class="body-map-card" data-body-map="${esc(id)}" data-default-muscle="${selected}" aria-label="${esc(options.title || "Workout body map")}"><div class="card-head"><div><div class="eyebrow">YOUR TRAINING, MAPPED</div><h2>${esc(options.title || "Where this workout went")}</h2><p>${esc(options.subtitle || "")}</p></div>${options.preview ? '<span class="pill">AI PREVIEW · NOT SAVED</span>' : ""}${options.controls || ""}</div><div class="body-map-layout"><div><div class="body-map-figures">${figure("Front", report, selected)}${figure("Back", report, selected)}</div><div class="body-map-legend"><span>Less</span><span class="body-map-scale"></span><span>More emphasis</span></div></div><div class="body-map-info"><div class="body-map-detail" aria-live="polite" aria-atomic="true">${detail(report.areas[selected])}</div><div class="body-map-chips" aria-label="Body areas">${groups.map((group) => `<button class="body-map-chip ${group === selected ? "is-selected" : ""}" data-muscle="${group}" aria-pressed="${group === selected}"><span style="background:${color(report.areas[group])}"></span>${group}</button>`).join("")}</div></div></div><p class="body-map-note">${report.personalized ? "Scaled to your own recent training range." : "Relative to this period; your scale adapts as you log more."} Reps and timed holds are normalized to your usual sets; secondary sets carry half the emphasis. Shading shows logged training volume, not measured effort or muscle activation.</p></section>`;
  }
  function bind(container) {
    for (const map of container.querySelectorAll("[data-body-map]")) {
      const report = reports.get(map.dataset.bodyMap);
      if (!report) continue;
      function select(group) {
        if (!report.areas[group]) return;
        for (const el of map.querySelectorAll("[data-muscle]")) {
          el.classList.toggle("is-selected", el.dataset.muscle === group);
          el.setAttribute("aria-pressed", String(el.dataset.muscle === group));
        }
        map.querySelector(".body-map-detail").innerHTML = detail(
          report.areas[group],
        );
      }
      for (const type of ["pointerover", "focusin"])
        map.addEventListener(type, (event) => {
          const target = event.target.closest(
            type === "pointerover" ? "g[data-muscle]" : "[data-muscle]",
          );
          if (target) select(target.dataset.muscle);
        });
      map.addEventListener("pointerleave", () =>
        select(map.dataset.pinnedMuscle || map.dataset.defaultMuscle),
      );
      map.addEventListener("click", (event) => {
        const target = event.target.closest("[data-muscle]");
        if (target) {
          map.dataset.pinnedMuscle = target.dataset.muscle;
          select(target.dataset.muscle);
        }
      });
      map.addEventListener("keydown", (event) => {
        if (
          (event.key === "Enter" || event.key === " ") &&
          event.target.matches("g[data-muscle]")
        ) {
          event.preventDefault();
          map.dataset.pinnedMuscle = event.target.dataset.muscle;
          select(event.target.dataset.muscle);
        }
      });
    }
  }
  const api = { summarize, period, render, bind };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BodyMap = api;
})(globalThis);
