import base64
import io
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fitness_tracker.transcription import (
    MAX_AUDIO_BYTES,
    LocalTranscriber,
    audio_payload,
    decode_audio,
)


def wav(seconds=1, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * int(rate * seconds))
    return output.getvalue()


class TranscriptionTests(unittest.TestCase):
    def test_payload_rejects_missing_malformed_and_oversized_audio(self):
        for value in (None, 4, "", "not base64!", "A" * (MAX_AUDIO_BYTES * 2)):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                audio_payload({"audio": value})
        self.assertEqual(audio_payload({"audio": "YWJj"}), b"abc")

    def test_decoder_resamples_and_bounds_real_audio_before_loading_model(self):
        audio = decode_audio(wav(rate=44100))
        self.assertEqual(len(audio), 16000)
        self.assertEqual(str(audio.dtype), "float32")
        for raw in (b"not audio", wav(0.1), wav(121)):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                decode_audio(raw)
        transcriber = LocalTranscriber()
        with patch.object(transcriber, "load_model") as load:
            with self.assertRaisesRegex(ValueError, "longer than 2 minutes"):
                transcriber.transcribe({"audio": base64.b64encode(wav(121)).decode()})
            load.assert_not_called()

    def test_inference_is_local_and_returns_only_text_metadata(self):
        transcriber = LocalTranscriber()
        transcriber.model = Mock()
        transcriber.model.transcribe.return_value = (
            iter(
                [SimpleNamespace(text=" Bench press, "), SimpleNamespace(text="50 kg, eight reps.")]
            ),
            SimpleNamespace(language="en"),
        )
        result = transcriber.transcribe({"audio": base64.b64encode(wav()).decode()})
        self.assertEqual(
            result,
            {
                "text": "Bench press, 50 kg, eight reps.",
                "language": "en",
                "model": "Whisper base (local)",
            },
        )
        options = transcriber.model.transcribe.call_args.kwargs
        self.assertTrue(options["vad_filter"])
        self.assertFalse(options["condition_on_previous_text"])
        self.assertFalse(transcriber.lock.locked())

    def test_silence_errors_and_concurrent_calls_release_lock(self):
        transcriber = LocalTranscriber()
        transcriber.model = Mock()
        transcriber.model.transcribe.return_value = ([], SimpleNamespace(language="en"))
        body = {"audio": base64.b64encode(wav()).decode()}
        with self.assertRaisesRegex(ValueError, "No speech"):
            transcriber.transcribe(body)
        self.assertFalse(transcriber.lock.locked())
        transcriber.model.transcribe.side_effect = RuntimeError("private diagnostic")
        with self.assertRaisesRegex(ValueError, "Local transcription failed"):
            transcriber.transcribe(body)
        self.assertFalse(transcriber.lock.locked())
        with transcriber.lock, self.assertRaisesRegex(ValueError, "still running"):
            transcriber.transcribe(body)

    def test_cached_model_stays_offline_and_first_use_download_is_explicit(self):
        with patch("faster_whisper.WhisperModel") as model:
            transcriber = LocalTranscriber()
            transcriber.load_model()
            transcriber.load_model()
            model.assert_called_once()
            self.assertEqual(model.call_args.args, ("base",))
            self.assertEqual(model.call_args.kwargs["device"], "cpu")
            self.assertTrue(model.call_args.kwargs["local_files_only"])
        with patch("faster_whisper.WhisperModel", side_effect=[OSError(), Mock()]) as model:
            LocalTranscriber().load_model()
            self.assertEqual(model.call_count, 2)
            self.assertNotIn("local_files_only", model.call_args.kwargs)
        with patch("faster_whisper.WhisperModel", side_effect=OSError()):
            with self.assertRaisesRegex(ValueError, "first download needs internet"):
                LocalTranscriber().load_model()
