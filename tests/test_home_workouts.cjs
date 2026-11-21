"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm");
const G = require("../src/fitness_tracker/web/goals.js");
const D = require("../src/fitness_tracker/web/dashboard.js");
const B = require("../src/fitness_tracker/web/body-map.js");
const H = require("../src/fitness_tracker/web/workout-history.js");
const day = "2026-11-21";
const exercise = (id, reps, weight = 0) => ({ exercise_id: id, tracking: "reps", load_mode: weight ? "weighted" : "bodyweight", sets: [{ reps, weight, seconds: 0 }] });
const gym = { id: "gym", kind: "workout", date: day, exercises: [exercise("pushups", 10)] };
const home = { id: "home", kind: "home_workout", date: day, exercises: [exercise("pushups", 10), exercise("curl", 10, 5)] };
const profile = { weekly_goal: 3, goals: { workout: { amount: 3, period: 1, unit: "week" } } };
const catalog = {
  pushups: { id: "pushups", name: "Push-ups", bodyParts: ["Chest"], primaryMuscles: ["chest"], secondaryBodyParts: ["Triceps"], equipment: "body only" },
  curl: { id: "curl", name: "Dumbbell curl", bodyParts: ["Biceps"], primaryMuscles: ["biceps"], secondaryBodyParts: [], equipment: "dumbbell" },
};
assert.equal(G.progress([home], profile.goals.workout, "workout", day, day).value, 0);
assert.equal(G.progress([gym, home], profile.goals.workout, "workout", day, day).value, 1);
assert.equal(D.weeklyTargets([home], profile, day, day).rows[0].value, 0);
assert.equal(D.calendar([home], profile, "2026-11", "workout", day).loggedDays, 0);
assert.equal(G.cardioProgress([home], { moderate: 150, high: 0 }, day, day).minutes, 0);
const report = B.summarize([gym, home], catalog);
assert.equal(report.areas.Chest.primary, 2, "gym and home sets both train the body map");
assert.equal(report.areas.Biceps.primary, 1);
assert.equal(B.summarize([home], catalog).areas.Biceps.reps, 10);
assert.equal(H.latestWorkout([home], day), null, "whole gym-session recall does not pick a home session");
assert.equal(H.latestWorkout([gym, home], day, undefined, "home_workout").id, "home");
assert.equal(H.latestExercise([home], "curl", day).item.sets[0].weight, 5);
assert.equal(H.usualExercises([gym, home], day).find(e => e.id === "pushups").count, 2);
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
const ctx = { state: { today: day, insights: { daily: { [day]: { workouts: 0, home_workouts: 1 } } } },
  icon: () => "", button: (label, action) => `<button data-action="${action}">${label}</button>`,
  dayWorkout: e => `<p>${e.id}</p>`, verificationFooter: kind => `<p>verify:${kind}</p>` };
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf("function homeWorkoutJournal("), source.indexOf("function dailyJournal(")), ctx);
const html = ctx.homeWorkoutJournal([home]);
assert.match(html, /Home workouts/);
assert.match(html, /1 session · 2 sets/);
assert.match(html, /does not count as a gym day/);
assert.match(html, /verify:home_workout/);
assert.match(html, /data-action="new-home-workout"/);
vm.runInContext(source.slice(source.indexOf("function heatmap("), source.indexOf("function habitDayDetails(")), ctx);
assert.match(ctx.heatmap(), /class="heat-cell home/);
assert.match(ctx.heatmap(), /Home workout, no gym day/);
console.log("Home workouts passed: body-map training, gym/cardio isolation, separate session recall, journal controls and home-day markers.");
