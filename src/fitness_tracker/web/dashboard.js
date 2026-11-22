/* Calendar goal coverage. Missing logs stay neutral; logged percentages use explicit bands. */
(function (root) {
  "use strict";
  const goals =
    typeof module !== "undefined" && module.exports
      ? require("./goals.js")
      : root.GoalTracking;
  const date = (day) => new Date(day + "T12:00:00Z"),
    iso = (d) => d.toISOString().slice(0, 10);
  function dailyTarget(goal, day) {
    const w = goals.windowFor(goal, day);
    return (
      goal.amount / (Math.round((date(w.end) - date(w.start)) / 86400000) + 1)
    );
  }
  function tone(ratio, logged, future) {
    return future
      ? "future"
      : !logged
        ? "unlogged"
        : ratio >= 0.9
          ? "met"
          : ratio >= 0.8
            ? "near"
            : ratio >= 0.7
              ? "partial"
              : ratio >= 0.6
                ? "mid"
                : ratio >= 0.5
                  ? "low"
                  : "critical";
  }
  function dayProgress(entries, profile, day, metric, today) {
    const rows = entries.filter((e) => e.date === day),
      future = day > today;
    let value = 0,
      target = 1,
      logged = false,
      unit = "",
      note = "";
    if (metric === "workout") {
      logged = rows.some((e) => e.kind === "workout");
      value = logged ? 1 : 0;
      note = logged ? "Gym day logged" : "Rest day or no workout logged";
    }
    if (metric === "cardio") {
      const selected = rows.filter(e => e.kind === "cardio");
      logged = selected.length > 0;
      value = selected.reduce((sum, e) => sum + e.minutes * (e.intensity === "high" ? 2 : 1), 0);
      target = ((profile.cardio_goal?.moderate || 0) + 2 * (profile.cardio_goal?.high || 0)) / 7;
      note = selected.map(e => `${e.activity}: ${e.minutes} min, ${e.intensity}`).join(" · ") || "No cardio logged";
      unit = "moderate-equivalent min";
    }
    if (metric === "protein" || metric === "creatine") {
      const selected = rows.filter((e) =>
        metric === "protein"
          ? e.kind === "meal"
          : goals.isCreatine(e) && e.unit === "g",
      );
      value = selected.reduce(
        (sum, e) => sum + (metric === "protein" ? e.protein : e.amount),
        0,
      );
      target = dailyTarget(profile.goals[metric], day);
      logged = selected.length > 0;
      unit = "g";
      note =
        target > 0
          ? `${Math.round((value / target) * 100)}% · ${value.toFixed(1)} / ${target.toFixed(1)} g daily target`
          : "Goal disabled";
    }
    if (metric === "supplements") {
      const names = (profile.consistency_supplements || []).filter(
          (n) => n.toLowerCase() !== "creatine",
        ),
        ratios = [];
      for (const name of names) {
        const g = profile.supplement_goals?.[name] || {
          amount: 1,
          period: 1,
          unit: "day",
          measure: "days",
        };
        if (!(g.amount > 0)) continue;
        const one = {
          ...g,
          amount: dailyTarget(g, day),
          period: 1,
          unit: "day",
        };
        const p = goals.supplementProgress(rows, one, name, day, today);
        ratios.push(p.value / one.amount);
        if (
          rows.some(
            (e) =>
              e.kind === "supplement" &&
              e.name.toLowerCase() === name.toLowerCase(),
          )
        )
          logged = true;
      }
      value = ratios.length
        ? ratios.reduce((a, b) => a + b, 0) / ratios.length
        : 0;
      note = ratios.length
        ? `${Math.round(value * 100)}% of selected supplement targets`
        : "No other supplements selected";
    }
    if (metric === "sleep") {
      const selected = rows.filter((e) => e.kind === "sleep"),
        total = selected.reduce((s, e) => s + e.hours, 0),
        night = selected
          .filter((e) => e.period === "night")
          .reduce((s, e) => s + e.hours, 0);
      value = Math.min(
        total / (profile.sleep_goal || 7),
        night / (profile.night_hours_goal || 6),
      );
      logged = selected.length > 0;
      note = `${total}h total · ${night}h night · ${Math.round(value * 100)}% of sleep goals`;
    }
    const ratio = target > 0 ? Math.max(0, value / target) : 0;
    return {
      day,
      number: Number(day.slice(-2)),
      logged: logged && !future,
      ratio: future ? 0 : ratio,
      tone: tone(ratio, logged, future),
      note: future ? "Future day" : note,
      value,
      target,
      unit,
    };
  }
  function calendar(entries, profile, month, metric, today) {
    const first = month + "-01",
      start = date(first),
      days = new Date(
        Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0, 12),
      ).getUTCDate();
    const list = [];
    for (let i = 1; i <= days; i++) {
      list.push(
        dayProgress(
          entries,
          profile,
          month + "-" + String(i).padStart(2, "0"),
          metric,
          today,
        ),
      );
    }
    const weeks = weeklyScores(entries, profile, first, list, metric, today);
    return {
      days: weeks.flatMap((w) => w.days).filter((d) => !d.outsideMonth),
      offset: (start.getUTCDay() + 6) % 7,
      loggedDays: list.filter((d) => d.logged).length,
      weeks,
    };
  }
  function shift(day, amount) {
    const d = date(day);
    d.setUTCDate(d.getUTCDate() + amount);
    return iso(d);
  }
  function weeklyScores(entries, profile, first, visibleDays, metric, today) {
    const offset = (date(first).getUTCDay() + 6) % 7;
    const monday = shift(first, -offset);
    const rowCount = Math.ceil((offset + visibleDays.length) / 7);
    const cache = new Map(visibleDays.map((d) => [d.day, d]));
    const gymGoal = profile.goals?.workout || {
      amount: profile.weekly_goal ?? 3,
      period: 1,
      unit: "week",
    };
    const enabled =
      metric === "workout"
        ? gymGoal.amount > 0
        : ["protein", "creatine"].includes(metric)
          ? profile.goals[metric].amount > 0
          : metric === "supplements"
            ? (profile.consistency_supplements || []).some(
                (n) =>
                  n.toLowerCase() !== "creatine" &&
                  (profile.supplement_goals?.[n]?.amount ?? 1) > 0,
              )
            : true;
    return Array.from({ length: rowCount }, (_, row) => {
      const start = shift(monday, row * 7),
        end = shift(start, 6);
      const days = Array.from({ length: 7 }, (_, n) => {
        const day = shift(start, n);
        return {
          ...(cache.get(day) ||
            dayProgress(entries, profile, day, metric, today)),
          outsideMonth: day.slice(0, 7) !== first.slice(0, 7),
        };
      });
      const elapsed = days.filter((d) => d.day <= today);
      if (metric === "cardio") {
        const progress = goals.cardioProgress(entries, profile.cardio_goal, start, today);
        const hasTarget = progress.target > 0;
        const weekLogged = elapsed.some(d => d.logged);
        for (const d of days) {
          const cumulative = goals.cardioProgress(entries, profile.cardio_goal, start, d.day < today ? d.day : today);
          d.ratio = hasTarget && d.day <= today ? cumulative.value / progress.target : 0;
          d.tone = d.day > today ? "future" : !hasTarget || !weekLogged ? "unlogged" : progress.percent >= 100 ? "met" : "building";
          d.note = `${d.note}. ${cumulative.value} / ${progress.target} moderate-equivalent minutes for the week by this day.`;
        }
        return { start, end, days, percent: progress.percent,
          note: `${progress.moderate} moderate + ${progress.high} high-intensity minutes. 1 high = 2 moderate. ${hasTarget ? `${progress.value} / ${progress.target} moderate-equivalent minutes.` : "No weekly cardio target set."}`,
          inProgress: start <= today && end >= today,
          tone: !hasTarget || !weekLogged ? "unlogged" : progress.percent >= 100 ? "met" : "building" };
      }
      const logged = elapsed.some((d) => d.logged),
        future = !elapsed.length,
        inProgress = start <= today && end >= today;
      const gymTarget = days.reduce(
        (sum, d) => sum + dailyTarget(gymGoal, d.day),
        0,
      );
      const actual = elapsed.filter((d) => d.logged).length;
      const supplements = metric === "supplements";
      const completed = supplements
        ? supplementWeekRatio(entries, profile, start, today)
        : null;
      const hasTarget = enabled && (!supplements || completed !== null);
      if (supplements) {
        for (const d of days) {
          const cutoff = d.day < today ? d.day : today;
          const cumulative = supplementWeekRatio(
            entries,
            profile,
            start,
            cutoff,
          );
          d.ratio = cumulative ?? 0;
          d.tone =
            d.day > today
              ? "future"
              : !hasTarget
                ? "unlogged"
                : completed >= 0.9
                  ? "met"
                  : "building";
          d.note =
            cumulative == null
              ? "No weekly supplement targets selected"
              : `${Number((d.ratio * 100).toFixed(1))}% of weekly supplement targets logged by ${d.day}. Unlogged days add zero.`;
        }
      }
      const rawRatio = !hasTarget
        ? null
        : supplements
          ? completed
          : metric === "workout"
            ? actual / gymTarget
            : days.reduce((sum, d) => sum + d.ratio, 0) / 7;
      const ratio = rawRatio == null ? null : Number(rawRatio.toFixed(12));
      const percent = ratio == null ? null : ratio * 100;
      const note = !hasTarget
        ? "No active target."
        : supplements
          ? `${Number(percent.toFixed(1))}% of selected weekly supplement targets. Each goal contributes equally; extra doses do not replace another supplement's goal.`
          : metric === "workout"
            ? `${actual} / ${Number(gymTarget.toFixed(2))} gym days toward this week's target.`
            : `${Number(percent.toFixed(1))}% across all 7 Monday–Sunday days. Every unlogged day, including future days, counts as zero.`;
      return {
        start,
        end,
        days,
        percent,
        note,
        inProgress,
        tone: supplements
          ? !hasTarget || future
            ? "unlogged"
            : completed >= 0.9
              ? "met"
              : "building"
          : tone(ratio || 0, logged && hasTarget, false),
      };
    });
  }
  function supplementWeekRatio(entries, profile, reference, cutoff) {
    const selected = new Set(
      (profile.consistency_supplements || [])
        .map((n) => n.toLowerCase())
        .filter((n) => n !== "creatine"),
    );
    const rows = weeklySupplements(
      entries,
      profile,
      reference,
      cutoff,
    ).rows.filter((r) => selected.has(r.name.toLowerCase()) && r.target > 0);
    return rows.length
      ? Number(
          (
            rows.reduce((sum, r) => sum + Math.min(1, r.value / r.target), 0) /
            rows.length
          ).toFixed(12),
        )
      : null;
  }
  function weeklyTargets(entries, profile, reference, today) {
    const week = goals.windowFor({ period: 1, unit: "week" }, reference);
    const logs = entries.filter(
      (e) => e.date >= week.start && e.date <= week.end && e.date <= today,
    );
    const rows = ["workout", "protein", "creatine"].map((key) => {
      const goal =
        profile.goals?.[key] ||
        (key === "workout"
          ? { amount: profile.weekly_goal ?? 3, period: 1, unit: "week" }
          : { amount: 0, period: 1, unit: "day" });
      const target =
        goal.amount > 0
          ? Number(
              Array.from({ length: 7 }, (_, i) =>
                dailyTarget(goal, shift(week.start, i)),
              )
                .reduce((a, b) => a + b, 0)
                .toFixed(10),
            )
          : null;
      const value =
        key === "workout"
          ? new Set(logs.filter((e) => e.kind === "workout").map((e) => e.date))
              .size
          : key === "protein"
            ? logs
                .filter((e) => e.kind === "meal")
                .reduce((sum, e) => sum + e.protein, 0)
            : goals.supplementProgress(
                logs,
                { amount: target || 1, period: 1, unit: "week", measure: "g" },
                "Creatine",
                reference,
                today,
              ).value;
      return {
        key,
        name: { workout: "Gym days", protein: "Protein", creatine: "Creatine" }[
          key
        ],
        value,
        target,
        percent: target ? (value / target) * 100 : null,
        remaining: target ? Math.max(0, target - value) : null,
        measure: key === "workout" ? "days" : "g",
      };
    });
    return { ...week, rows };
  }
  function weeklySupplements(entries, profile, reference, today) {
    const week = goals.windowFor({ period: 1, unit: "week" }, reference);
    const logs = entries.filter(
      (e) =>
        e.kind === "supplement" &&
        e.date >= week.start &&
        e.date <= week.end &&
        e.date <= today &&
        e.amount > 0,
    );
    const names = new Map();
    for (const name of [
      ...(profile.supplements || []),
      ...Object.keys(profile.supplement_goals || {}),
      ...logs.map((e) => e.name),
    ])
      names.set(name.toLowerCase(), names.get(name.toLowerCase()) || name);
    const rows = [...names.values()].map((name) => {
      const consumed = new Map();
      for (const entry of logs.filter(
        (e) => e.name.toLowerCase() === name.toLowerCase(),
      )) {
        const unit = goals.canonicalUnit(entry.unit);
        consumed.set(unit, (consumed.get(unit) || 0) + entry.amount);
      }
      const goal =
        name.toLowerCase() === "creatine"
          ? profile.goals?.creatine && {
              ...profile.goals.creatine,
              measure: "g",
            }
          : profile.supplement_goals?.[name];
      const target =
        goal?.amount > 0
          ? Number(
              Array.from({ length: 7 }, (_, index) =>
                dailyTarget(goal, shift(week.start, index)),
              )
                .reduce((sum, amount) => sum + amount, 0)
                .toFixed(10),
            )
          : null;
      const progress =
        target > 0
          ? goals.supplementProgress(
              entries,
              { ...goal, amount: target, period: 1, unit: "week" },
              name,
              reference,
              today,
            )
          : null;
      return {
        name,
        goal,
        target,
        consumed: [...consumed].map(([unit, amount]) => ({ unit, amount })),
        value: progress?.value ?? null,
        percent: progress?.percent ?? 0,
        remaining: progress
          ? Number(Math.max(0, target - progress.value).toFixed(10))
          : null,
        achieved: progress ? progress.value + 1e-9 >= target : false,
        incompatible: progress?.incompatible || 0,
        equivalent: Boolean(
          goal && (goal.unit !== "week" || goal.period !== 1),
        ),
      };
    });
    return { ...week, rows };
  }
  function intakeSeries(entries, metric, mode, today) {
    const points = new Map();
    for (const entry of entries) {
      if (entry.date > today || !(metric === "protein" || metric === "calories" ? entry.kind === "meal" && (metric !== "calories" || entry.calories != null) : goals.isCreatine(entry) && entry.unit === "g")) continue;
      const start = mode === "weekly" ? shift(entry.date, -((date(entry.date).getUTCDay() + 6) % 7)) : entry.date;
      const point = points.get(start) || { start, end: mode === "weekly" ? shift(start, 6) : start, value: 0 };
      point.value += metric === "protein" ? entry.protein : metric === "calories" ? entry.calories : entry.amount;
      points.set(start, point);
    }
    return [...points.values()].sort((a, b) => a.start.localeCompare(b.start)).slice(-20);
  }
  const api = { calendar, dailyTarget, tone, weeklySupplements, weeklyTargets, intakeSeries };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Dashboard = api;
})(globalThis);
