"""Ephemeral, bounded audio decoding and on-device Whisper transcription."""

import base64
import binascii
import io
import os
import threading

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_AUDIO_SECONDS = 120
SAMPLE_RATE = 16_000
MODEL = "base"


def audio_payload(body):
    encoded = body.get("audio")
    if not isinstance(encoded, str) or not 0 < len(encoded) <= 4 * ((MAX_AUDIO_BYTES + 2) // 3):
        raise ValueError("Choose an audio file up to 8 MB and 2 minutes long.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError(
            "The audio could not be read. Record again or choose another file."
        ) from error
    if not raw or len(raw) > MAX_AUDIO_BYTES:
        raise ValueError("Choose an audio file up to 8 MB and 2 minutes long.")
    return raw


def decode_audio(raw):
    # Decode incrementally: compressed media must not expand into unbounded audio.
    import av
    import numpy as np

    chunks, count = [], 0
    try:
        with av.open(io.BytesIO(raw), options={"protocol_whitelist": "pipe"}) as container:
            if not container.streams.audio:
                raise ValueError("This file has no audio. Choose an audio recording.")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)

            def collect(frame):
                nonlocal count
                for converted in resampler.resample(frame):
                    count += converted.samples
                    if count > MAX_AUDIO_SECONDS * SAMPLE_RATE:
                        raise ValueError(
                            "Audio is longer than 2 minutes. Split it into shorter clips."
                        )
                    chunks.append(converted.to_ndarray().flatten())

            for frame in container.decode(audio=0):
                collect(frame)
            collect(None)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "The audio format could not be read. Try WAV, MP3, M4A, OGG or WebM."
        ) from error
    if count < SAMPLE_RATE // 4:
        raise ValueError("The recording is too short. Record a few seconds of speech.")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


class LocalTranscriber:
    def __init__(self):
        self.lock = threading.Lock()
        self.model = None

    def load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel

            options = dict(
                device="cpu", compute_type="int8", cpu_threads=min(os.cpu_count() or 2, 4)
            )
            try:
                # Cached weights require no network, including on later app launches.
                self.model = WhisperModel(MODEL, local_files_only=True, **options)
            except Exception:
                try:
                    self.model = WhisperModel(MODEL, **options)
                except Exception as error:
                    raise ValueError(
                        "The local speech model is not ready. Its first download needs internet. "
                        "Check your connection and try again; your message is unchanged."
                    ) from error
        return self.model

    def transcribe(self, body):
        raw = audio_payload(body)
        if not self.lock.acquire(blocking=False):
            raise ValueError("A local transcription is still running. Wait a moment and try again.")
        try:
            try:
                audio = decode_audio(raw)
                model = self.load_model()
            except ImportError as error:
                raise ValueError(
                    "Local transcription needs an app update. Close and reopen with "
                    "Start Blaze Athletics, or run python3 scripts/start.py."
                ) from error
            try:
                segments, info = model.transcribe(
                    audio, beam_size=5, vad_filter=True, condition_on_previous_text=False
                )
                parts, size = [], 0
                for segment in segments:
                    text = segment.text.strip()
                    size += len(text) + 1
                    if size > 6000:
                        raise ValueError(
                            "The transcript is too long. Split the recording into shorter clips."
                        )
                    if text:
                        parts.append(text)
            except ValueError:
                raise
            except Exception as error:
                raise ValueError(
                    "Local transcription failed. Try another recording; your message is unchanged."
                ) from error
            text = " ".join(parts)
            if not text:
                raise ValueError("No speech was detected. Try speaking closer to the microphone.")
            # Audio and decoded samples stay in memory only; this never touches the journal or coach.
            return {"text": text, "language": info.language, "model": "Whisper base (local)"}
        finally:
            self.lock.release()
