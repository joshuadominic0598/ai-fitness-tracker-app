/* Audio is transcribed locally, then inserted as editable text. Never sends a chat. */
(function (root) {
  "use strict";
  const MAX_BYTES = 8 * 1024 * 1024;
  const encode = (blob) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(",")[1]);
      reader.onerror = () => reject(Error("The audio file could not be read."));
      reader.readAsDataURL(blob);
    });
  function create(options) {
    let phase = "idle",
      message = "Record or upload audio · 2 min / 8 MB max",
      pendingText = "";
    let version = 0,
      stream = null,
      recorder = null,
      timer = null;
    const media = options.media || (() => navigator.mediaDevices);
    const Recorder = options.Recorder || root.MediaRecorder;
    const onChange = () => options.onChange?.();
    const state = () => ({ phase, message, pendingText });
    const isBusy = () => ["requesting", "recording", "transcribing"].includes(phase);
    function cleanup() {
      clearTimeout(timer);
      timer = null;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      stream?.getTracks().forEach((track) => track.stop());
      stream = null;
      recorder = null;
    }
    function cancel() {
      version++;
      cleanup();
      phase = "idle";
      message = "Record or upload audio · 2 min / 8 MB max";
      pendingText = "";
      onChange();
    }
    function fail(error, ticket) {
      if (ticket !== version) return;
      version++;
      cleanup();
      phase = "error";
      message = error.message || "Audio could not be transcribed. Try again.";
      onChange();
    }
    function insert() {
      if (!pendingText) return;
      if (options.onTranscript(pendingText) === false) {
        message = "Your message is full. Shorten it, then insert the transcript below.";
      } else {
        pendingText = "";
        message = "Transcript added. Review it, then press Send.";
      }
      onChange();
    }
    async function transcribe(blob, ticket) {
      if (ticket !== version) return;
      phase = "transcribing";
      message =
        "Transcribing on your computer… First use downloads the speech model; this may take a few minutes.";
      onChange();
      try {
        if (!blob.size || blob.size > MAX_BYTES)
          throw Error("Choose an audio file up to 8 MB and 2 minutes long.");
        const audio = await (options.encode || encode)(blob);
        if (ticket !== version) return;
        const result = await options.transcribe({ audio });
        if (ticket !== version) return;
        if (!result.text?.trim())
          throw Error("No speech was detected. Try recording again.");
        pendingText = result.text.trim();
        phase = "idle";
        insert();
      } catch (error) {
        fail(error, ticket);
      }
    }
    async function upload(file) {
      if (!file || isBusy()) return;
      pendingText = "";
      await transcribe(file, ++version);
    }
    async function record() {
      if (isBusy()) return;
      const ticket = ++version;
      pendingText = "";
      phase = "requesting";
      message = "Allow microphone access to start recording…";
      onChange();
      try {
        if (!Recorder || !media()?.getUserMedia)
          throw Error("This browser cannot record audio. Use Upload audio instead.");
        const acquired = await media().getUserMedia({ audio: true });
        if (ticket !== version) {
          acquired.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = acquired;
        const mimeType = [
          "audio/webm;codecs=opus",
          "audio/mp4",
          "audio/ogg;codecs=opus",
        ].find((type) => Recorder.isTypeSupported?.(type));
        recorder = new Recorder(stream, mimeType ? { mimeType } : undefined);
        const active = recorder,
          chunks = [];
        let bytes = 0;
        active.ondataavailable = (event) => {
          if (ticket !== version || !event.data.size) return;
          bytes += event.data.size;
          if (bytes > MAX_BYTES)
            return fail(Error("Recording reached 8 MB. Try a shorter clip."), ticket);
          chunks.push(event.data);
        };
        active.onerror = () =>
          fail(Error("Microphone recording failed. Try again or upload audio."), ticket);
        active.onstop = () => {
          if (ticket !== version) return;
          cleanup();
          void transcribe(new Blob(chunks, { type: active.mimeType }), ticket);
        };
        active.start(1000);
        phase = "recording";
        message =
          "Recording… Stop to transcribe. Stops automatically after 2 minutes.";
        timer = setTimeout(stop, 119000);
        onChange();
      } catch (error) {
        if (error.name === "NotAllowedError")
          error = Error(
            "Microphone access was denied. Allow it in your browser or use Upload audio.",
          );
        fail(error, ticket);
      }
    }
    function stop() {
      if (phase !== "recording") return;
      phase = "transcribing";
      message = "Finishing recording…";
      clearTimeout(timer);
      onChange();
      recorder.stop();
      stream?.getTracks().forEach((track) => track.stop());
    }
    return { state, isBusy, record, stop, cancel, upload, insert };
  }
  root.VoiceInput = { create };
  if (typeof module === "object") module.exports = root.VoiceInput;
})(typeof window === "object" ? window : globalThis);
