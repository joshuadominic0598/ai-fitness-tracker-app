"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
const frames = [];
let shows = 0, focused = null;
const active = { dataset: { action: "remove-set", index: "4", setIndex: "2" } };
const replacement = { focus(options) { assert.equal(options.preventScroll, true); focused = "replacement"; } };
let nextControl = replacement;
const dialog = { open: true, scrollTop: 1700, contains: el => el === active,
 querySelector: selector => { assert.ok(selector.includes('data-index="4"')); return nextControl; },
 focus(options) { assert.equal(options.preventScroll, true); focused = "dialog"; } };
let body = { scrollTop: 80 };
const content = { firstElementChild: {} };
Object.defineProperty(content, "innerHTML", { set(value) {
 this.firstElementChild = {}; body = { scrollTop: 0 }; dialog.scrollTop = 0;
} });
const ctx = { document: { activeElement: active }, CSS: { escape: s => s },
 $: selector => ({ "#modal": dialog, "#modal-content": content, "#modal .modal-body": body })[selector],
 esc: String, dialogLifecycle: { show() { shows++; dialog.open = true; dialog.scrollTop = 0; } },
 requestAnimationFrame: fn => frames.push(fn) };
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf("function modal("), source.indexOf("function field(")), ctx);
ctx.modal("Workout", "", "New rows", "", true);
assert.equal(shows, 0, "editing must not invoke the opening lifecycle/reset");
assert.equal(dialog.scrollTop, 1700);
assert.equal(body.scrollTop, 80);
assert.equal(focused, "replacement");
dialog.scrollTop = 10; frames.shift()();
assert.equal(dialog.scrollTop, 1700, "restore after browser layout/anchoring");
nextControl = null; dialog.scrollTop = 2200;
ctx.modal("Workout", "", "Exercise deleted", "", true);
assert.equal(dialog.scrollTop, 2200);
assert.equal(focused, "dialog", "deleted control can fall back without focus scrolling");
ctx.modal("Different editor", "", "Other form");
assert.equal(shows, 1);
assert.equal(dialog.scrollTop, 0, "new editors still open at top");
frames.shift()();
assert.equal(dialog.scrollTop, 0, "stale restoration must not move a different editor");
console.log("Workout scroll passed: open-editor redraw retains dialog/body position and focus; new editors reset; stale frames are ignored.");
