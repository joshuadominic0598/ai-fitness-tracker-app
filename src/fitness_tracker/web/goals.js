/* Calendar windows and progress for overall recurring goals. */
(function (root) {
  "use strict";
  const date = (value) => new Date(value + "T12:00:00Z");
  const iso = (value) => value.toISOString().slice(0, 10);
  function shift(value, days) {
    const result = date(value);
    result.setUTCDate(result.getUTCDate() + days);
    return iso(result);
  }
  function windowFor(goal, reference) {
    let start = reference,
      end = reference;
    if (goal.unit === "month") {
      const value = date(reference);
      start = iso(
        new Date(
          Date.UTC(
            value.getUTCFullYear(),
            value.getUTCMonth() - goal.period + 1,
            1,
            12,
          ),
        ),
      );
      end = iso(
        new Date(
          Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 0, 12),
        ),
      );
    } else if (goal.unit === "week") {
      const weekday = (date(reference).getUTCDay() + 6) % 7;
      end = shift(reference, 6 - weekday);
      start = shift(reference, -weekday - (goal.period - 1) * 7);
    } else start = shift(reference, 1 - goal.period);
    return { start, end };
  }
  function isCreatine(entry) {
    return (
      entry.kind === "creatine" ||
      (entry.kind === "supplement" &&
        entry.name?.trim().toLowerCase() === "creatine")
    );
  }
  function progress(entries, goal, key, reference, today) {
    const { start, end } = windowFor(goal, reference);
    const cutoff = today;
    const records = entries.filter(
      (e) => e.date >= start && e.date <= end && e.date <= cutoff,
    );
    const value =
      key === "workout"
        ? new Set(
            records.filter((e) => e.kind === "workout").map((e) => e.date),
          ).size
        : records.reduce(
            (sum, e) =>
              sum +
              (key === "protein" && e.kind === "meal"
                ? e.protein
                : key === "creatine" && isCreatine(e) && e.unit === "g"
                  ? e.amount
                  : 0),
            0,
          );
    return {
      ...goal,
      start,
      end,
      value,
      percent: goal.amount ? Math.min(100, (value / goal.amount) * 100) : 0,
    };
  }
  const periodLabel = (goal) =>
    goal.period === 1
      ? `per ${goal.unit}`
      : `every ${goal.period} ${goal.unit}s`;
  function cardioProgress(entries, goal, reference, today, highWeight = 2) {
    const window = windowFor({ period: 1, unit: "week" }, reference);
    const totals = { moderate: 0, high: 0 };
    for (const e of entries) {
      if (e.kind === "cardio" && e.date >= window.start && e.date <= window.end && e.date <= today)
        totals[e.intensity] += e.minutes;
    }
    const value = totals.moderate + totals.high * highWeight;
    const target = (goal?.moderate || 0) + (goal?.high || 0) * highWeight;
    return { ...window, ...totals, minutes: totals.moderate + totals.high, value, target,
      percent: target > 0 ? value / target * 100 : null, remaining: Math.max(0, target - value) };
  }
  function calorieMetrics(entries, reference, today) {
    const meals = entries.filter(e => e.kind === "meal" && e.date <= today);
    const summarize = (window) => {
      const rows = meals.filter(e => e.date >= window.start && e.date <= window.end);
      return { ...window, value: rows.reduce((sum, e) => sum + (e.calories ?? 0), 0),
        meals: rows.length, missing: rows.filter(e => e.calories == null).length };
    };
    const week = windowFor({ period: 1, unit: "week" }, reference);
    const history = summarize({ start: week.start, end: week.end < today ? week.end : shift(today, -1) });
    history.days = Math.max(0, Math.round((date(history.end) - date(history.start)) / 86400000) + 1);
    history.average = history.days && !history.missing ? history.value / history.days : null;
    return { day: summarize({ start: reference, end: reference }), week: summarize(week),
      month: summarize(windowFor({ period: 1, unit: "month" }, reference)), history };
  }
  function intakeMetrics(entries, key, goal, reference, today, options = {}) {
    const amounts = {},
      logged = new Set();
    for (const e of entries) {
      if (e.date > today) continue;
      const matches =
        key === "protein" ? e.kind === "meal" : isCreatine(e) && e.unit === "g";
      if (matches) {
        amounts[e.date] =
          (amounts[e.date] || 0) + (key === "protein" ? e.protein : e.amount);
        logged.add(e.date);
      }
    }
    const targetForDay = (day) => {
      const window = windowFor(goal, day);
      const days =
        Math.round((date(window.end) - date(window.start)) / 86400000) + 1;
      return goal.amount / days;
    };
    const dailyTarget = targetForDay(reference);
    const percent = (value, target) =>
      target > 0 ? (value / target) * 100 : null;
    const week = windowFor({ period: 1, unit: "week" }, reference);
    const weekValue = Object.entries(amounts).reduce(
      (sum, [day, value]) =>
        sum +
        (day >= week.start && day <= week.end && day <= today ? value : 0),
      0,
    );
    const first = [...logged].sort()[0];
    const month = windowFor({ period: 1, unit: "month" }, reference);
    const historyWindow = options.historyPeriod === "week" ? week : month;
    let start = historyWindow.start,
      end = historyWindow.end < today ? historyWindow.end : shift(today, -1);
    if (options.historyPeriod !== "week" && first && first > start)
      start = first;
    let days = 0,
      total = 0,
      met = 0,
      attained = 0,
      loggedDays = 0,
      expected = 0;
    if (first || options.historyPeriod === "week")
      for (let day = start; day <= end; day = shift(day, 1)) {
        days++;
        const target = targetForDay(day);
        expected += target;
        const value = amounts[day] || 0;
        total += value;
        if (logged.has(day)) loggedDays++;
        if (target > 0) {
          if (value >= target) met++;
          attained += Math.min(100, (value / target) * 100);
        }
      }
    const monthDays =
      Math.round((date(month.end) - date(month.start)) / 86400000) + 1;
    const monthRecords = [...logged].filter(
      (day) => day >= month.start && day <= month.end && day <= today,
    );
    const monthValue = monthRecords.reduce((sum, day) => sum + amounts[day], 0);
    const weekTarget = Array.from({ length: 7 }, (_, index) =>
      targetForDay(shift(week.start, index)),
    ).reduce((sum, value) => sum + value, 0);
    return {
      month: {
        ...month,
        days: monthDays,
        value: monthValue,
        loggedDays: monthRecords.length,
        target:
          goal.unit === "month" && goal.period === 1
            ? goal.amount
            : dailyTarget * monthDays,
        percent: percent(
          monthValue,
          goal.unit === "month" && goal.period === 1
            ? goal.amount
            : dailyTarget * monthDays,
        ),
      },
      day: {
        date: reference,
        value: amounts[reference] || 0,
        target: dailyTarget,
        percent: percent(amounts[reference] || 0, dailyTarget),
      },
      week: {
        ...week,
        value: weekValue,
        target: weekTarget,
        percent: percent(weekValue, weekTarget),
        open: week.end >= today,
      },
      history: {
        start,
        end,
        days,
        total,
        average: days ? total / days : null,
        loggedDays,
        met,
        percent: days ? percent(total, expected) : null,
        attainment: days && dailyTarget > 0 ? attained / days : null,
      },
      isDailyGoal: goal.period === 1 && goal.unit === "day",
    };
  }
  function monthCoverage(entries, reference, today) {
    const window = windowFor({ period: 1, unit: "month" }, reference);
    const records = entries.filter(
      (e) => e.date >= window.start && e.date <= window.end && e.date <= today,
    );
    return {
      ...window,
      days: Math.round((date(window.end) - date(window.start)) / 86400000) + 1,
      foodDays: new Set(
        records.filter((e) => e.kind === "meal").map((e) => e.date),
      ).size,
      creatineDays: new Set(
        records
          .filter(
            (e) =>
              isCreatine(e) && canonicalUnit(e.unit) === "g" && e.amount > 0,
          )
          .map((e) => e.date),
      ).size,
    };
  }
  function canonicalUnit(unit) {
    const value = unit.trim().toLowerCase().replace(/[µμ]/g, "u");
    return (
      {
        gram: "g",
        grams: "g",
        milligram: "mg",
        milligrams: "mg",
        microgram: "mcg",
        micrograms: "mcg",
        ug: "mcg",
        iu: "IU",
        capsules: "capsule",
        tablets: "tablet",
        softgels: "softgel",
        servings: "serving",
        scoops: "scoop",
        drops: "drop",
        milliliters: "ml",
        milliliter: "ml",
      }[value] || value
    );
  }
  function supplementProgress(entries, goal, name, reference, today) {
    const window = windowFor(goal, reference),
      dates = new Set(),
      mass = { g: 1, mg: 0.001, mcg: 0.000001 };
    let value = 0,
      incompatible = 0;
    for (const e of entries) {
      if (
        (name.toLowerCase() === "creatine"
          ? !isCreatine(e)
          : e.kind !== "supplement" ||
            isCreatine(e) ||
            e.name.toLowerCase() !== name.toLowerCase()) ||
        e.date < window.start ||
        e.date > window.end ||
        e.date > today ||
        e.amount <= 0
      )
        continue;
      if (goal.measure === "days") dates.add(e.date);
      else if (goal.measure === "doses") value++;
      else {
        const source = canonicalUnit(e.unit);
        if (source === goal.measure) value += e.amount;
        else if (mass[source] && mass[goal.measure])
          value += (e.amount * mass[source]) / mass[goal.measure];
        else incompatible++;
      }
    }
    if (goal.measure === "days") value = dates.size;
    return {
      ...window,
      value,
      incompatible,
      percent: Math.min(100, (value / goal.amount) * 100),
    };
  }
  const api = {
    isCreatine,
    windowFor,
    monthCoverage,
    progress,
    periodLabel,
    intakeMetrics,
    cardioProgress,
    calorieMetrics,
    supplementProgress,
    canonicalUnit,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GoalTracking = api;
})(globalThis);
