/* Pure workout recall helpers shared by the browser and Node regression tests. */
(function (root) {
  "use strict";
  const clone = (value) => JSON.parse(JSON.stringify(value));
  function sessions(entries, day, excludeId) {
    return entries
      .filter(
        (e) => ["workout", "home_workout"].includes(e.kind) && e.date <= day && e.id !== excludeId,
      )
      .sort((a, b) => b.date.localeCompare(a.date));
  }
  function latestWorkout(entries, day, excludeId, kind = "workout") {
    return sessions(entries, day, excludeId).find(e => e.kind === kind) || null;
  }
  function latestExercise(entries, id, day, excludeId) {
    for (const session of sessions(entries, day, excludeId)) {
      const item = session.exercises.find((e) => e.exercise_id === id);
      if (item) return { date: session.date, item: clone(item) };
    }
    return null;
  }
  function usualExercises(entries, day) {
    const counts = new Map();
    for (const session of sessions(entries, day)) {
      for (const id of new Set(session.exercises.map((e) => e.exercise_id))) {
        const item = counts.get(id) || {
          id,
          count: 0,
          last_date: session.date,
        };
        item.count++;
        counts.set(id, item);
      }
    }
    return [...counts.values()].sort(
      (a, b) =>
        b.count - a.count ||
        b.last_date.localeCompare(a.last_date) ||
        a.id.localeCompare(b.id),
    );
  }
  function modeFor(item, catalog) {
    if (item.exercise_id === "Plank") return "time";
    if (["reps", "time"].includes(item.tracking)) return item.tracking;
    if (item.sets?.some((s) => s.seconds > 0 && !s.reps)) return "time";
    if (item.sets?.some((s) => s.reps > 0)) return "reps";
    return ["cardio", "stretching"].includes(
      catalog[item.exercise_id]?.category,
    )
      ? "time"
      : "reps";
  }
  function loadModeFor(item, catalog) {
    if (["bodyweight", "weighted"].includes(item.load_mode))
      return item.load_mode;
    if (item.sets?.length)
      return item.sets.some((set) => Number(set.weight || 0) > 0)
        ? "weighted"
        : "bodyweight";
    const exercise = catalog[item.exercise_id];
    return item.exercise_id === "Plank" ||
      exercise?.equipment === "body only" ||
      ["cardio", "stretching"].includes(exercise?.category)
      ? "bodyweight"
      : "weighted";
  }
  function normalize(item, catalog) {
    const result = clone(item);
    result.tracking = modeFor(result, catalog);
    result.load_mode = loadModeFor(result, catalog);
    result.sets = (result.sets || []).map((s) => ({
      weight: result.load_mode === "bodyweight" ? 0 : Number(s.weight || 0),
      reps: result.tracking === "reps" ? Number(s.reps || 0) : 0,
      seconds: result.tracking === "time" ? Number(s.seconds || 0) : 0,
    }));
    return result;
  }
  function makeExercise(entries, id, day, catalog, excludeId) {
    const last = latestExercise(entries, id, day, excludeId);
    if (last)
      return { ...normalize(last.item, catalog), _last_date: last.date };
    const mode = modeFor({ exercise_id: id }, catalog);
    return {
      exercise_id: id,
      tracking: mode,
      load_mode: loadModeFor({ exercise_id: id }, catalog),
      sets: [
        {
          weight: 0,
          reps: mode === "reps" ? 10 : 0,
          seconds: mode === "time" ? 30 : 0,
        },
      ],
    };
  }
  const api = {
    latestWorkout,
    latestExercise,
    usualExercises,
    modeFor,
    loadModeFor,
    normalize,
    makeExercise,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WorkoutHistory = api;
})(globalThis);
