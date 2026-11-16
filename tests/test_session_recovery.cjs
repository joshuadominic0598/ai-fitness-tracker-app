"use strict";
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const source = fs.readFileSync(
  require.resolve("../src/fitness_tracker/web/app.js"),
  "utf8",
);
const code = source.slice(
  source.indexOf("let sessionRenewal;"),
  source.indexOf("async function refresh("),
);
const response = (status, data) => ({
  ok: status < 400,
  status,
  json: async () => data,
});
(async () => {
  const draft = { message: "My unsent meal", consent: true };
  const ctx = { state: { token: "before-restart", draft }, fetch: undefined };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  const calls = [];
  ctx.fetch = async (path, options) => {
    calls.push({ path, options });
    if (path === "/api/session")
      return response(200, { token: "after-restart" });
    if (options.headers["X-App-Token"] === "before-restart")
      return response(403, { code: "session_expired", error: "Expired" });
    return response(200, { ok: true });
  };
  await ctx.api("chat", { message: "Test", consent: true });
  assert.equal(calls.length, 3);
  assert.equal(calls[2].options.headers["X-App-Token"], "after-restart");
  assert.equal(calls[0].options.body, calls[2].options.body);
  assert.equal(ctx.state.draft, draft);
  for (const [status, error] of [
    [403, { error: "Wrong origin" }],
    [400, { error: "Provider failed" }],
    [500, { error: "Server failed" }],
  ]) {
    let count = 0;
    ctx.fetch = async () => {
      count++;
      return response(status, error);
    };
    await assert.rejects(ctx.api("chat", {}));
    assert.equal(count, 1, "unrelated errors are never replayed");
  }
  let count = 0;
  ctx.fetch = async () => {
    count++;
    throw Error("Network uncertain");
  };
  await assert.rejects(ctx.api("entry", {}));
  assert.equal(count, 1, "uncertain writes are never replayed");
  count = 0;
  ctx.fetch = async (path) => {
    count++;
    return path === "/api/session"
      ? response(200, { token: "rotated" })
      : response(403, { code: "session_expired", error: "Expired again" });
  };
  await assert.rejects(ctx.api("chat", {}), /Expired again/);
  assert.equal(count, 3, "one renewal and one replay only");
  let renewals = 0;
  ctx.state.token = "stale";
  ctx.fetch = async (path, options) => {
    if (path === "/api/session") {
      renewals++;
      return response(200, { token: "shared" });
    }
    return options.headers["X-App-Token"] === "stale"
      ? response(403, { code: "session_expired" })
      : response(200, { ok: true });
  };
  await Promise.all([ctx.api("profile", {}), ctx.api("entry", {})]);
  assert.equal(renewals, 1, "concurrent stale requests share renewal");
  console.log(
    "Session recovery checks passed: one safe replay, preserved drafts, shared renewal and no retry of uncertain writes.",
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
