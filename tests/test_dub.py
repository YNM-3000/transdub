"""Dub-stage tests: pure timeline/assread/naming logic (no TTS, no ffmpeg)."""

from __future__ import annotations

from pathlib import Path

import pysubs2

from dub.assread import chinese_cues
from dub.audio import default_dub_output
from dub.models import VoiceCue
from dub.timeline import plan_timeline, tempo_for


def _bilingual_ass(tmp_path):
    subs = pysubs2.SSAFile()
    subs.append(pysubs2.SSAEvent(start=0, end=2000, text=r"{\fs22}你好世界\N{\fs13}Hello world"))
    subs.append(pysubs2.SSAEvent(start=2000, end=4000, text=r"{\fs22}第二行\N{\fs13}Second line"))
    path = tmp_path / "b.ass"
    subs.save(str(path))
    return path


def test_chinese_cues_takes_first_line_and_strips_tags(tmp_path):
    cues = chinese_cues(_bilingual_ass(tmp_path))
    assert [c.text for c in cues] == ["你好世界", "第二行"]
    assert cues[0].start == 0.0 and cues[0].end == 2.0


def test_english_cues_takes_second_line(tmp_path):
    from dub.assread import english_cues

    cues = english_cues(_bilingual_ass(tmp_path))
    assert [c.text for c in cues] == ["Hello world", "Second line"]


def test_pick_reference_window_merges_to_min_length():
    from dub.reference import pick_reference_window

    cues = [VoiceCue(i * 2.0, i * 2.0 + 2.0, f"line{i}") for i in range(9)]
    win = pick_reference_window(cues)  # starts a third in (idx 3), merges to >=4s
    assert win.end - win.start >= 4.0
    assert win.end - win.start <= 10.0
    assert "line3" in win.text


def test_ensure_reference_cuts_then_caches(tmp_path):
    from dub.reference import ensure_reference

    video = tmp_path / "Chan" / "clip.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")
    cues = [VoiceCue(i * 2.0, i * 2.0 + 2.0, f"word{i}") for i in range(9)]
    refs = tmp_path / "refs"
    calls = {"n": 0}

    def fake_ffmpeg(cmd, capture_output=True, text=True):
        calls["n"] += 1
        Path(cmd[-1]).write_bytes(b"RIFFfake")  # "extract" the clip
        return __import__("types").SimpleNamespace(returncode=0, stdout="", stderr="")

    ref, prompt = ensure_reference(video, cues, refs_dir=refs, runner=fake_ffmpeg)
    assert ref == refs / "Chan.wav" and ref.is_file()
    assert prompt and calls["n"] == 1

    ref2, prompt2 = ensure_reference(video, cues, refs_dir=refs, runner=fake_ffmpeg)
    assert ref2 == ref and prompt2 == prompt and calls["n"] == 1  # cached, not re-cut


def test_get_voice_backend_gpt_sovits_engine():
    from dub.backend import get_voice_backend
    from dub.gptsovits_backend import GPTSoVITSBackend

    assert isinstance(get_voice_backend(engine="gpt-sovits"), GPTSoVITSBackend)


def test_register_reference_writes_clip_text_and_lang(tmp_path):
    from dub.reference import register_reference

    media = tmp_path / "Test Speaker.mp4"
    media.write_bytes(b"x")
    refs = tmp_path / "refs"

    class FakeTranscriber:
        detected_language = "ja"

        def transcribe(self, path):
            return [VoiceCue(0, 2, "仕事だ。"), VoiceCue(2, 4, "以上。")]

    def fake_ffmpeg(cmd, capture_output=True, text=True):
        Path(cmd[-1]).write_bytes(b"RIFFfake")
        return __import__("types").SimpleNamespace(returncode=0, stdout="", stderr="")

    wav, text, lang = register_reference(
        media, FakeTranscriber(), refs_dir=refs, runner=fake_ffmpeg
    )
    assert wav == refs / "Test Speaker.wav" and wav.is_file()
    assert text == "仕事だ。 以上。" and lang == "ja"
    assert (refs / "Test Speaker.txt").read_text(encoding="utf-8") == "仕事だ。 以上。"
    assert (refs / "Test Speaker.lang").read_text(encoding="utf-8") == "ja"


def test_set_reference_from_path_resolves_name_and_lang(tmp_path, monkeypatch):
    from dub.gptsovits_backend import GPTSoVITSBackend

    refs = tmp_path / "models" / "refs"
    refs.mkdir(parents=True)
    (refs / "Speaker.wav").write_bytes(b"x")
    (refs / "Speaker.txt").write_text("仕事だ。", encoding="utf-8")
    (refs / "Speaker.lang").write_text("ja", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    b = GPTSoVITSBackend()
    b.set_reference_from_path("Speaker")  # bare name → models/refs/Speaker.wav
    assert b.ref_audio.endswith("Speaker.wav")
    assert b.ref_text == "仕事だ。" and b.ref_lang == "ja"
    assert b.voice_label == "Speaker"


def test_voice_server_uses_running_server_without_starting(monkeypatch):
    import dub.server as srv

    monkeypatch.setattr(srv, "reachable", lambda url: True)
    started = {"n": 0}
    monkeypatch.setattr(srv, "_launch", lambda url: started.__setitem__("n", started["n"] + 1))

    s = srv.VoiceServer("http://x")
    assert s.ensure() is True
    assert started["n"] == 0  # already up → not started
    s.close()  # no-op (we didn't start it)


def test_voice_server_skips_when_not_installed(monkeypatch):
    import dub.server as srv

    monkeypatch.setattr(srv, "reachable", lambda url: False)
    monkeypatch.setattr(srv, "is_installed", lambda: False)
    assert srv.VoiceServer("http://x").ensure() is False


def test_voice_server_starts_and_stops_when_down_but_installed(monkeypatch):
    import dub.server as srv

    state = {"up": False, "stopped": False}
    monkeypatch.setattr(srv, "reachable", lambda url: state["up"])
    monkeypatch.setattr(srv, "is_installed", lambda: True)

    class FakeProc:
        def terminate(self): state["stopped"] = True
        def wait(self, timeout=0): return 0
        def kill(self): state["stopped"] = True

    def fake_launch(url):
        state["up"] = True  # server becomes reachable
        return FakeProc()

    monkeypatch.setattr(srv, "_launch", fake_launch)

    s = srv.VoiceServer("http://x")
    assert s.ensure() is True
    s.close()
    assert state["stopped"] is True  # we started it → we stop it


def test_gptsovits_synthesize_posts_reference_and_text(tmp_path, monkeypatch):
    import dub.gptsovits_backend as gs

    sent = {}
    monkeypatch.setattr(gs, "_to_wav", lambda audio, out: Path(out).write_bytes(audio))

    def transport(body):
        sent.update(body)
        return b"WAVE"

    b = gs.GPTSoVITSBackend(transport=transport)
    b.set_reference(tmp_path / "ref.wav", "the reference transcript", "en")
    b.synthesize("你好，世界", tmp_path / "out.wav")

    assert sent["text"] == "你好，世界"
    assert sent["prompt_text"] == "the reference transcript"
    assert sent["prompt_lang"] == "en" and sent["text_lang"] == "zh"
    assert sent["ref_audio_path"].endswith("ref.wav")
    assert (tmp_path / "out.wav").read_bytes() == b"WAVE"


def test_gptsovits_synthesize_requires_reference(tmp_path):
    from dub.gptsovits_backend import GPTSoVITSBackend

    import pytest

    with pytest.raises(RuntimeError, match="reference"):
        GPTSoVITSBackend(transport=lambda b: b"x").synthesize("hi", tmp_path / "o.wav")


def test_dub_video_injects_channel_reference(tmp_path, monkeypatch):
    import dub.pipeline as pipe
    import dub.reference as ref_mod

    ass = _bilingual_ass(tmp_path)
    video = tmp_path / "Chan" / "v.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")

    monkeypatch.setattr(ref_mod, "ensure_reference",
                        lambda v, cues, **k: (tmp_path / "ref.wav", "ref text"))
    monkeypatch.setattr(pipe, "build_dub_track", lambda *a, **k: tmp_path / "dub.wav")
    monkeypatch.setattr(pipe, "mux_audio", lambda v, a, o: Path(o).write_bytes(b"y"))

    got = {}

    class CloneBackend:
        name = "gpt-sovits"
        needs_reference = True
        ref_audio = None
        voice = ""

        def set_reference(self, audio, text, lang="en"):
            got["ref"] = (str(audio), text, lang)
            self.ref_audio = str(audio)

        def synthesize(self, text, out):
            pass

    res = pipe.dub_video(video, ass, CloneBackend(), tmp_path / "out.mp4")
    assert res.ok
    assert got["ref"][1] == "ref text" and got["ref"][2] == "en"


def test_tempo_for_speeds_up_only_when_too_long():
    assert tempo_for(1.0, 2.0) == 1.0            # shorter than window → no change
    assert tempo_for(3.0, 2.0) == 1.5            # 3s into 2s → 1.5x
    assert tempo_for(10.0, 2.0, max_tempo=1.6) == 1.6  # capped
    assert tempo_for(1.0, 0.0) == 1.0            # degenerate window


def test_plan_timeline_places_clips_and_never_drifts():
    cues = [VoiceCue(0.0, 2.0, "a"), VoiceCue(5.0, 6.0, "b")]
    # clip 0 fits (1.5s <= 2s); clip 1 too long (2s into 1s → 2.0x cap)
    pieces = plan_timeline(cues, [1.5, 2.0])

    kinds = [(p.kind, round(p.seconds, 3)) for p in pieces]
    # cue0 at t=0 (no leading gap), then silence until t=5, then cue1
    assert kinds[0][0] == "clip"
    assert kinds[1] == ("silence", 3.5)          # 5.0 - 1.5 placed
    assert kinds[2][0] == "clip"
    assert pieces[2].tempo == 2.0                 # capped speed-up (MAX_TEMPO)
    # running position stays anchored: last clip fitted = 2.0/2.0 = 1.0
    assert round(pieces[2].seconds, 3) == 1.0


def test_plan_timeline_absorbs_carried_over_drift():
    # Back-to-back cues, no gaps. Clip 0 overruns its 1s window (3s @ 2.0x cap
    # → 1.5s), landing 0.5s late. Clip 1 must then compress harder to catch up:
    # it fits into what's left of its own window (2.0 - 1.5 = 0.5s), not its
    # nominal 1.0s window.
    cues = [VoiceCue(0.0, 1.0, "a"), VoiceCue(1.0, 2.0, "b")]
    pieces = plan_timeline(cues, [3.0, 1.0])

    clips = [p for p in pieces if p.kind == "clip"]
    assert clips[0].tempo == 2.0                  # first clip hits the cap
    assert round(clips[0].seconds, 3) == 1.5      # 3.0 / 2.0
    # second clip: 1.0s of audio into the 0.5s remaining → 2.0x cap, 0.5s
    assert clips[1].tempo == 2.0
    assert round(clips[1].seconds, 3) == 0.5
    # total = 2.0s, exactly the second cue's end — drift fully absorbed
    assert round(sum(p.seconds for p in pieces), 3) == 2.0


def test_merge_into_sentences_groups_until_terminator():
    from dub.segment import merge_into_sentences

    cues = [
        VoiceCue(0.0, 2.0, "他刚刚解决了"),
        VoiceCue(2.0, 4.0, "最难的问题之一。"),
        VoiceCue(4.0, 6.0, "这真是不可思议"),
        VoiceCue(6.0, 8.0, "对吧？"),
    ]
    merged = merge_into_sentences(cues)

    assert len(merged) == 2
    assert merged[0] == VoiceCue(0.0, 4.0, "他刚刚解决了最难的问题之一。")
    assert merged[1] == VoiceCue(4.0, 8.0, "这真是不可思议对吧？")


def test_merge_into_sentences_caps_span_without_terminator():
    from dub.segment import merge_into_sentences

    # No terminators at all; must still flush once the span exceeds max_span.
    cues = [VoiceCue(float(i), float(i + 1), "字") for i in range(20)]
    merged = merge_into_sentences(cues, max_span=5.0)

    assert len(merged) > 1
    assert all((c.end - c.start) <= 5.0 for c in merged)
    # nothing dropped: concatenated text is preserved in order
    assert "".join(c.text for c in merged) == "字" * 20


def test_default_dub_output_is_sibling_variant():
    out = default_dub_output(Path("output/x/Clip.final.mp4"))
    assert out == Path("output/x/Clip.final.dubbed.mp4")


def test_synthesize_all_parallel_preserves_order(tmp_path):
    from dub.audio import _synthesize_all

    cues = [VoiceCue(0, 1, f"line{i}") for i in range(12)]
    clips = [tmp_path / f"c{i}.wav" for i in range(12)]

    class FakeBackend:
        max_workers = 4  # exercise the concurrent path

        def synthesize(self, text, out):
            Path(out).write_text(text)

    seen: list[int] = []
    _synthesize_all(cues, clips, FakeBackend(), seen.append)

    assert all(clips[i].read_text() == f"line{i}" for i in range(12))  # order kept
    assert len(seen) == 12 and max(seen) <= 99  # 100 is emitted later, after concat


def test_synthesize_all_falls_back_to_silence_on_failure(tmp_path):
    import wave

    from dub.audio import _synthesize_all

    cues = [VoiceCue(0, 1, f"line{i}") for i in range(3)]
    clips = [tmp_path / f"c{i}.wav" for i in range(3)]

    class FlakyBackend:
        max_workers = 1

        def synthesize(self, text, out):
            if text == "line1":
                raise RuntimeError("No audio was received")
            Path(out).write_text(text)

    failures = _synthesize_all(cues, clips, FlakyBackend(), None)

    assert failures == 1  # one cue fell back to silence
    assert clips[0].read_text() == "line0"  # good cues synthesized
    assert clips[2].read_text() == "line2"
    with wave.open(str(clips[1]), "rb") as w:  # bad cue → valid silence wav
        assert w.getframerate() == 24_000 and w.getnframes() > 0


def test_build_dub_track_fails_when_most_cues_fail(tmp_path):
    import pytest

    from dub.audio import build_dub_track

    # Every cue fails synthesis (e.g. TTS server down / edge-tts 403) — the dub
    # must raise instead of emitting a near-silent track.
    cues = [VoiceCue(i, i + 1, f"line{i}") for i in range(4)]

    class DeadBackend:
        max_workers = 1

        def synthesize(self, text, out):
            raise RuntimeError("server unreachable")

    with pytest.raises(RuntimeError, match="mostly silent"):
        build_dub_track(cues, DeadBackend(), tmp_path / "out.wav", workdir=tmp_path)


def test_scale_remaps_progress_band():
    from dub.audio import _scale

    seen: list[int] = []
    s = _scale(seen.append, 0, 80)
    s(0); s(50); s(100)
    assert seen == [0, 40, 80]
    assert _scale(None, 0, 80) is None


def test_dub_video_reports_actual_voice(tmp_path, monkeypatch):
    import dub.pipeline as pipe

    ass = _bilingual_ass(tmp_path)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(pipe, "build_dub_track", lambda *a, **k: tmp_path / "dub.wav")
    monkeypatch.setattr(pipe, "mux_audio", lambda v, a, o: Path(o).write_bytes(b"y"))

    class FakeVoice:
        name = "edge-tts"
        voice = "zh-CN-YunxiNeural"

        def synthesize(self, text, out):
            pass

    res = pipe.dub_video(video, ass, FakeVoice(), tmp_path / "out.mp4")
    assert res.ok
    assert res.voice == "zh-CN-YunxiNeural"  # the voice, not the engine name


def test_get_voice_backend_engine_selection(monkeypatch):
    import dub.backend as db

    monkeypatch.setattr(db, "_try_gptsovits", lambda v, *, auto: None)  # server down
    monkeypatch.setattr(db, "_try_edge", lambda v: "EDGE")
    monkeypatch.setattr(db, "_try_kokoro", lambda v: "KOKORO")
    monkeypatch.delenv("DUB_ENGINE", raising=False)

    assert db.get_voice_backend() == "EDGE"  # auto → edge when GPT-SoVITS unreachable
    assert db.get_voice_backend(engine="kokoro") == "KOKORO"

    monkeypatch.setenv("DUB_ENGINE", "kokoro")
    assert db.get_voice_backend() == "KOKORO"

    monkeypatch.delenv("DUB_ENGINE", raising=False)
    monkeypatch.setattr(db, "_try_edge", lambda v: None)
    assert db.get_voice_backend() == "KOKORO"  # auto falls back when edge absent


def test_get_voice_backend_auto_prefers_gptsovits_when_reachable(monkeypatch):
    import dub.backend as db

    monkeypatch.setattr(db, "_try_gptsovits", lambda v, *, auto: "SOVITS")
    monkeypatch.setattr(db, "_try_edge", lambda v: "EDGE")
    monkeypatch.delenv("DUB_ENGINE", raising=False)
    assert db.get_voice_backend() == "SOVITS"  # auto default is now GPT-SoVITS


def test_gptsovits_voice_override_sets_reference(tmp_path):
    from dub.backend import _try_gptsovits

    ref = tmp_path / "myvoice.wav"
    ref.write_bytes(b"x")
    (tmp_path / "myvoice.txt").write_text("hand picked transcript", encoding="utf-8")

    b = _try_gptsovits(str(ref), auto=False)
    assert b.ref_audio.endswith("myvoice.wav")
    assert b.ref_text == "hand picked transcript"
    assert b.voice_label == "myvoice"


def test_ollama_unload_calls_generate_keepalive_zero(monkeypatch):
    import json as _json
    from translate import ollama_backend as ob

    calls = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b""

        @staticmethod
        def _ps():
            return _json.dumps({"models": [{"name": "qwen3.5:9b"}]}).encode()

    def fake_urlopen(req, timeout=0):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/api/ps"):
            r = Resp(); r.read = lambda: Resp._ps(); return r
        calls.append(_json.loads(req.data))  # the /api/generate unload body
        return Resp()

    monkeypatch.setattr(ob.urllib.request, "urlopen", fake_urlopen)
    freed = ob.unload()
    assert freed == ["qwen3.5:9b"]
    assert calls == [{"model": "qwen3.5:9b", "keep_alive": 0}]
