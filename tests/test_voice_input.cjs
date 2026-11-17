"use strict";
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm");
const VoiceInput = require("../src/fitness_tracker/web/voice-input.js");
const tick = () => new Promise((resolve) => setImmediate(resolve));
let stoppedTracks = 0, activeRecorder;
const stream = { getTracks: () => [{ stop: () => stoppedTracks++ }] };
class Recorder {
  static isTypeSupported(type) { return type.startsWith("audio/webm"); }
  constructor() {
    activeRecorder = this;
    this.state = "inactive";
    this.mimeType = "audio/webm";
  }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["recorded speech"]) });
    queueMicrotask(() => this.onstop?.());
  }
}
const create = (options = {}) => VoiceInput.create({
  Recorder,
  media: () => ({ getUserMedia: async () => stream }),
  encode: async () => "local-audio",
  ...options,
});
async function recordAndStop(voice) {
  await voice.record();
  assert.equal(voice.state().phase, "recording");
  voice.stop();
  await tick();
}
(async () => {
  let draft = "Log my workout:", requests = 0, resolve;
  const voice = create({
    transcribe: async (payload) => {
      requests++;
      assert.deepEqual(payload, { audio: "local-audio" });
      return new Promise((done) => resolve = done);
    },
    onTranscript: (text) => { draft += "\n" + text; },
  });
  assert.equal(voice.state().message, "", "idle audio adds no toolbar text");
  await recordAndStop(voice);
  assert.equal(voice.isBusy(), true);
  draft += " Warmup: 8 pushups.";
  resolve({ text: "Bench press, 50 kg, 8 reps." });
  await tick();
  assert.equal(draft, "Log my workout: Warmup: 8 pushups.\nBench press, 50 kg, 8 reps.");
  assert.match(voice.state().message, /Review it/);
  assert.equal(requests, 1, "recording only calls the transcription endpoint");
  assert.ok(stoppedTracks > 0);

  await recordAndStop(voice);
  voice.cancel(); draft = "New chat";
  resolve({ text: "Old transcript" }); await tick();
  assert.equal(draft, "New chat", "late transcription never enters a new chat");
  await voice.record(); voice.cancel(); await tick();
  assert.equal(requests, 2, "canceled recording is discarded without transcribing");
  assert.equal(activeRecorder.state, "inactive");

  let accepted = false;
  const full = create({
    transcribe: async () => ({ text: "Retained transcript" }),
    onTranscript: () => accepted,
  });
  await recordAndStop(full);
  assert.equal(full.state().pendingText, "Retained transcript");
  accepted = true; full.insert();
  assert.equal(full.state().pendingText, "");
  const oversized = create({ transcribe: () => assert.fail("oversized recording cannot be sent") });
  await oversized.record();
  activeRecorder.ondataavailable({ data: { size: 8 * 1024 * 1024 + 1 } });
  await tick(); assert.equal(oversized.state().phase, "error");

  let grant;
  const requesting = create({ media: () => ({ getUserMedia: () => new Promise((resolve) => grant = resolve) }) });
  const acquiring = requesting.record(); requesting.cancel(); const before = stoppedTracks;
  grant(stream); await acquiring;
  assert.ok(stoppedTracks > before, "late permission stops acquired microphone tracks");
  const denied = create({ media: () => ({ getUserMedia: async () => {
    throw Object.assign(Error(), { name: "NotAllowedError" });
  } }) });
  await denied.record(); assert.match(denied.state().message, /denied/);
  assert.equal(denied.isBusy(), false);

  const source = fs.readFileSync(require.resolve("../src/fitness_tracker/web/app.js"), "utf8");
  const input = { value: "Existing workout:", maxLength: 6000, style: {}, scrollHeight: 140, focus() {} };
  let calls = 0;
  const context = {
    VoiceInput: { create }, chatComposerDraft: "", coachModelBusy: false,
    chatIsBusy: () => false, esc: String, icon: () => "<svg></svg>",
    $: (id) => id === "#chat-input" ? input : null,
    api: async (path) => {
      assert.equal(path, "transcribe"); calls++; return { text: "8 pushups" };
    },
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf("const voiceInput ="), source.indexOf("function coach()")), context);
  await vm.runInContext("voiceInput.record()", context);
  assert.match(context.chatVoiceButton(), /Stop recording and transcribe/);
  vm.runInContext("voiceInput.stop()", context); await tick();
  assert.equal(input.value, "Existing workout:\n8 pushups");
  assert.equal(context.chatComposerDraft, input.value);
  assert.equal(calls, 1);
  assert.equal(input.style.height, "142px", "transcribed text resizes the composer");
  assert.match(context.chatVoiceButton(), /aria-label="Record audio"/);
  assert.doesNotMatch(context.chatVoiceButton(), />Record audio</);
  assert.doesNotMatch(source, /chat-audio-file|voice-upload|Upload audio/);
  assert.match(source, /Stop or cancel audio and review the transcript before sending/);
  console.log("Voice input passed: microphone control, recording, cancellation, permission denial, editable transcript and no auto-send.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
