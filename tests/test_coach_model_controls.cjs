"use strict";
const fs = require("node:fs"),
  vm = require("node:vm"),
  assert = require("node:assert/strict");
const source = fs.readFileSync(
  require.resolve("../src/fitness_tracker/web/app.js"),
  "utf8",
);
const code = source.slice(
  source.indexOf("const coachModelLists"),
  source.indexOf("function coach()"),
);
(async () => {
  const provider = { value: "ollama" },
    model = { value: "qwen3:4b" },
    custom = { value: "" },
    status = {},
    active = {};
  const form = { elements: [provider, model, custom] };
  const input = { value: "Keep my unsent meal and portions" };
  const elements = {
    "#coach-model-form": form,
    "#coach-provider": provider,
    "#coach-model": model,
    "#coach-custom-model": custom,
    "#coach-model-status": status,
    "#coach-active-model": active,
    "#chat-input": input,
    "#coach-quota-info": {},
  };
  const ctx = {
    VoiceInput: require("../src/fitness_tracker/web/voice-input.js"),
    chatBusy: false,
    chatIsBusy: () => ctx.chatBusy,
    state: {
      coach_consent: { accepted: true },
      connections: {
        provider: "ollama",
        ollama_model: "qwen3:8b",
      },
    },
    $: (id) => elements[id],
    esc: (s) => String(s),
    button: () => "",
    quotaSummary: () => "Free tier",
    n: String,
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  const sent = [];
  ctx.api = async (path, data) => {
    sent.push({ path, data });
    if (path === "connections") return { ...ctx.state.connections, ...data };
    if (path === "models") return { models: ["qwen3:4b", "qwen3:14b"] };
    return { model: data.model, latency_ms: 1200 };
  };
  await ctx.saveCoachModel();
  assert.equal(ctx.state.connections.provider, "ollama");
  assert.equal(ctx.state.connections.ollama_model, "qwen3:4b");
  assert.equal(input.value, "Keep my unsent meal and portions");
  assert.equal(ctx.state.coach_consent.accepted, true);
  assert.match(active.textContent, /Using Qwen/);
  assert.equal(provider.disabled, false);
  assert.deepEqual(JSON.parse(JSON.stringify(sent[0].data)), {
    provider: "ollama",
    ollama_model: "qwen3:4b",
  });
  await ctx.loadCoachModels();
  assert.match(model.innerHTML, /qwen3:14b/);
  model.value = "__custom__";
  custom.value = "qwen3:custom";
  await ctx.saveCoachModel();
  assert.equal(ctx.state.connections.ollama_model, "qwen3:custom");
  await ctx.testCoachConnection("ollama", status);
  assert.match(status.textContent, /Qwen.*responded/);
  assert.match(status.textContent, /qwen3:custom/);
  assert.equal(input.value, "Keep my unsent meal and portions");
  elements["#coach-apply-connection"] = {};
  elements["#coach-switch-preview"] = {};
  elements["#coach-cancel-connection"] = {};
  provider.value = "ollama";
  model.value = "qwen3:8b";
  ctx.updateCoachConnectionState();
  assert.equal(ctx.pendingCoachConnection(), true);
  assert.match(elements["#coach-apply-connection"].textContent, /Switch to Qwen/);
  assert.equal(elements["#coach-switch-preview"].hidden, false);
  assert.match(elements["#coach-switch-preview"].textContent, /Not active yet/);
  assert.equal(ctx.state.connections.provider, "ollama", "a pending selection does not switch silently");
  await ctx.saveCoachModel();
  assert.equal(ctx.state.connections.provider, "ollama");
  assert.equal(ctx.pendingCoachConnection(), false);
  assert.equal(elements["#coach-switch-preview"].hidden, true);
  assert.equal(elements["#coach-apply-connection"].disabled, true);
  assert.match(active.textContent, /Using Qwen/);
  assert.match(ctx.coachModelControls(), /ACTIVE CONNECTION/);
  assert.match(ctx.coachModelControls(), /Inference runs on your computer/);
  assert.equal(input.value, "Keep my unsent meal and portions");
  ctx.chatBusy = true;
  await assert.rejects(ctx.saveCoachModel(), /Wait/);
  ctx.chatBusy = false;
  ctx.api = async () => {
    throw Error("Local model unavailable");
  };
  await ctx.testCoachConnection("ollama", status);
  assert.match(status.textContent, /Local model unavailable/);
  assert.equal(model.disabled, false);
  let resolve;
  ctx.api = () => new Promise((r) => (resolve = r));
  const pending = ctx.loadCoachModels();
  elements["#coach-model-form"] = { elements: [] };
  model.innerHTML = "replacement";
  resolve({ models: ["late-result"] });
  await pending;
  assert.equal(model.innerHTML, "replacement");
  console.log(
    "Coach controls passed: scoped model saves, preserved message and saved agreement, live checks, errors and stale-load isolation.",
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
