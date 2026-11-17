"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm");
const VoiceInput = require("../src/fitness_tracker/web/voice-input.js");
const deferred = () => { let resolve; const promise = new Promise((r) => resolve = r); return { promise, resolve }; };
const tick = () => new Promise((r) => setImmediate(r));
(async () => {
  let draft = "Log my workout for 2026-11-17:", sent = 0, payload, resolve;
  const voice = VoiceInput.create({
    encode: async () => "local-audio",
    transcribe: async (data) => { sent++; payload = data; return new Promise((r) => resolve = r); },
    onTranscript: (text) => { draft += "\n" + text; },
  });
  const upload = voice.upload(new Blob(["recording"]));
  await tick();
  assert.equal(voice.isBusy(), true);
  draft += " Warmup: 8 pushups.";
  resolve({ text: "Bench press, 50 kg, 8 reps." });
  await upload;
  assert.equal(draft, "Log my workout for 2026-11-17: Warmup: 8 pushups.\nBench press, 50 kg, 8 reps.");
  assert.deepEqual(payload, { audio: "local-audio" });
  assert.match(voice.state().message, /Review it/);
  assert.equal(sent, 1, "only the transcription endpoint is called");
  const stale = voice.upload(new Blob(["recording"]));
  await tick(); voice.cancel(); draft = "New chat";
  resolve({ text: "Old transcript" }); await stale;
  assert.equal(draft, "New chat", "a late result never enters a new chat");

  let accepted = false;
  const full = VoiceInput.create({ encode: async () => "audio", transcribe: async () => ({ text: "Retained transcript" }), onTranscript: () => accepted });
  await full.upload(new Blob(["speech"]));
  assert.equal(full.state().pendingText, "Retained transcript");
  accepted = true; full.insert();
  assert.equal(full.state().pendingText, "");
  await full.upload(new Blob([]));
  assert.equal(full.state().phase, "error");

  let stopped = 0, rec;
  const stream = { getTracks: () => [{ stop: () => stopped++ }] };
  class Recorder {
    static isTypeSupported(type) { return type.startsWith("audio/webm"); }
    constructor() { rec = this; this.state = "inactive"; this.mimeType = "audio/webm"; }
    start() { this.state = "recording"; }
    stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["voice"]) }); queueMicrotask(() => this.onstop?.()); }
  }
  let records = 0;
  const recording = VoiceInput.create({ Recorder, media: () => ({ getUserMedia: async () => stream }), encode: async () => "voice", transcribe: async () => { records++; return { text: "Recorded exercise" }; }, onTranscript: (text) => assert.equal(text, "Recorded exercise") });
  await recording.record(); assert.equal(recording.state().phase, "recording");
  recording.stop(); await tick();
  assert.equal(records, 1); assert.ok(stopped > 0);
  await recording.record(); recording.cancel(); await tick();
  assert.equal(records, 1, "canceled recording is discarded");
  assert.equal(rec.state, "inactive");

  const mic = deferred();
  const requesting = VoiceInput.create({ Recorder, media: () => ({ getUserMedia: () => mic.promise }) });
  const acquiring = requesting.record(); requesting.cancel(); const before = stopped;
  mic.resolve(stream); await acquiring;
  assert.ok(stopped > before, "late microphone permission stops all acquired tracks");
  const denied = VoiceInput.create({ Recorder, media: () => ({ getUserMedia: async () => { throw Object.assign(Error(), { name: "NotAllowedError" }); } }) });
  await denied.record(); assert.match(denied.state().message, /denied/);
  assert.equal(denied.isBusy(), false);

  // Verify actual composer integration preserves text and exposes the controls.
  const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
  const input = { value: "Existing workout:", maxLength: 6000, focus: () => {} };
  let chatCalls = 0;
  const context = { VoiceInput: { create: (options) => VoiceInput.create({ ...options, encode: async () => "voice" }) }, Blob, chatComposerDraft: "", coachModelBusy: false, chatIsBusy: () => false, esc: String, $: (id) => id === "#chat-input" ? input : null, api: async (path) => { assert.equal(path, "transcribe"); chatCalls++; return { text: "8 pushups" }; } };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf("const voiceInput ="), source.indexOf("function coach()")), context);
  await vm.runInContext('voiceInput.upload(new Blob(["voice"]))', context);
  assert.equal(input.value, "Existing workout:\n8 pushups");
  assert.equal(context.chatComposerDraft, input.value);
  assert.equal(chatCalls, 1);
  assert.match(context.chatVoiceControls(), /Record audio/);
  assert.match(context.chatVoiceControls(), /Upload audio/);
  assert.match(source, /Stop or cancel audio and review the transcript before sending/);
})().then(() => console.log("Voice input tests passed")).catch((error) => { console.error(error); process.exitCode = 1; });
