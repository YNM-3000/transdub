"""Monitor stage tests: config, API client, state, scanner, notify, CLI."""

from __future__ import annotations

import json

import pytest

from monitor.config import load_config
from monitor.models import NEW, TRENDING, Category, ChannelRef, VideoCandidate, WatchConfig
from monitor.notify import EmailSettings, build_digest, notify, send_email
from monitor.scanner import scan
from monitor.state import SeenStore
from monitor.youtube_api import YouTubeClient, _to_candidate


# --- config ------------------------------------------------------------------

def test_load_config(tmp_path):
    path = tmp_path / "channels.json"
    path.write_text(json.dumps({
        "scan_limit": 8,
        "categories": {
            "life": {"min_trending_views": 50000, "channels": [
                {"id": "UC1", "name": "A"}, {"id": "UC2"}
            ]},
        },
    }), encoding="utf-8")

    cfg = load_config(path)
    assert cfg.scan_limit == 8
    assert len(cfg.categories) == 1
    cat = cfg.categories[0]
    assert cat.name == "life" and cat.min_trending_views == 50000
    assert [c.id for c in cat.channels] == ["UC1", "UC2"]
    assert cat.channels[0].category == "life"


# --- youtube api client ------------------------------------------------------

class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, params):
        self.calls.append((url, params))
        endpoint = url.rsplit("/", 1)[-1]
        return self.responses[endpoint]


def test_to_candidate_parses_fields():
    item = {
        "id": "vid1",
        "snippet": {"title": "T", "description": "D", "channelId": "UC1",
                     "channelTitle": "Zeus", "publishedAt": "2026-01-01T00:00:00Z",
                     "tags": ["a", "b"]},
        "statistics": {"viewCount": "1234", "likeCount": "56"},
        "contentDetails": {"caption": "true"},
    }
    c = _to_candidate(item)
    assert c.video_id == "vid1" and c.view_count == 1234 and c.like_count == 56
    assert c.tags == ("a", "b") and c.has_captions is True
    assert c.url == "https://www.youtube.com/watch?v=vid1"


def test_to_candidate_handles_missing_stats_and_no_caption():
    c = _to_candidate({"id": "x", "snippet": {}, "contentDetails": {"caption": "false"}})
    assert c.view_count is None and c.has_captions is False and c.tags == ()


def test_client_recent_videos_chains_calls():
    transport = FakeTransport({
        "channels": {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]},
        "playlistItems": {"items": [{"contentDetails": {"videoId": "v1"}}]},
        "videos": {"items": [{"id": "v1", "snippet": {"title": "T"},
                               "statistics": {"viewCount": "9"},
                               "contentDetails": {"caption": "true"}}]},
    })
    client = YouTubeClient("KEY", transport=transport)
    vids = client.recent_videos("UC1", 5)
    assert len(vids) == 1 and vids[0].video_id == "v1"
    # API key threaded into every request.
    assert all(params.get("key") == "KEY" for _u, params in transport.calls)


def test_client_no_uploads_playlist_returns_empty():
    client = YouTubeClient("K", transport=FakeTransport({"channels": {"items": []}}))
    assert client.recent_videos("UC1", 5) == []


# --- state -------------------------------------------------------------------

def _cand(vid="v1", views=10, caption=True):
    return VideoCandidate(video_id=vid, title="t", description="", channel_id="UC1",
                          channel="Zeus", view_count=views, has_captions=caption)


def test_seen_store_tracks_seen_and_trending(tmp_path):
    with SeenStore(tmp_path / "s.db") as store:
        assert not store.is_seen("v1")
        store.mark_seen(_cand(), "2026-01-01T00:00:00+00:00")
        assert store.is_seen("v1")
        assert not store.is_trending_notified("v1")
        store.mark_trending("v1", "2026-01-02T00:00:00+00:00")
        assert store.is_trending_notified("v1")


# --- scanner -----------------------------------------------------------------

class FakeClient:
    def __init__(self, by_channel):
        self.by_channel = by_channel

    def recent_videos(self, channel_id, limit):
        return self.by_channel.get(channel_id, [])


def _config(min_views=100):
    return WatchConfig(
        categories=(Category("life", min_views, (ChannelRef("UC1", "A", "life"),)),),
        scan_limit=5,
    )


def test_scan_emits_new_alert_and_skips_no_captions(tmp_path):
    client = FakeClient({"UC1": [
        _cand("v1", views=5, caption=True),
        _cand("v2", views=5, caption=False),  # skipped
    ]})
    with SeenStore(tmp_path / "s.db") as state:
        alerts = scan(_config(), client, state, now="2026-01-01T00:00:00+00:00")
    assert [(a.candidate.video_id, a.reason) for a in alerts] == [("v1", NEW)]
    assert alerts[0].candidate.category == "life"


def test_scan_is_idempotent_for_seen_videos(tmp_path):
    client = FakeClient({"UC1": [_cand("v1", views=5)]})
    with SeenStore(tmp_path / "s.db") as state:
        first = scan(_config(), client, state, now="2026-01-01T00:00:00+00:00")
        second = scan(_config(), client, state, now="2026-01-02T00:00:00+00:00")
    assert len(first) == 1 and second == []


def test_scan_emits_trending_when_threshold_crossed(tmp_path):
    with SeenStore(tmp_path / "s.db") as state:
        # First scan: below threshold -> only NEW.
        scan(_config(min_views=100), FakeClient({"UC1": [_cand("v1", views=10)]}),
             state, now="2026-01-01T00:00:00+00:00")
        # Later: views cross threshold -> TRENDING (once).
        a2 = scan(_config(min_views=100), FakeClient({"UC1": [_cand("v1", views=500)]}),
                  state, now="2026-01-02T00:00:00+00:00")
        a3 = scan(_config(min_views=100), FakeClient({"UC1": [_cand("v1", views=900)]}),
                  state, now="2026-01-03T00:00:00+00:00")
    assert [a.reason for a in a2] == [TRENDING]
    assert a3 == []  # not re-notified


# --- notify ------------------------------------------------------------------

def _alert(reason=NEW, **kw):
    from monitor.models import Alert
    return Alert(VideoCandidate(
        video_id="v1", title="USB-C 真相", description="一段简介", channel_id="UC1",
        channel="Zeus", view_count=1000, like_count=50, tags=("USB-C", "科技"),
        has_captions=True, category="life", **kw,
    ), reason)


def test_build_digest_summarizes_and_formats():
    subject, body = build_digest([_alert(NEW), _alert(TRENDING)])
    assert "新视频 1" in subject and "爆款 1" in subject
    assert "【新视频】" in body and "【爆款】" in body
    assert "https://www.youtube.com/watch?v=v1" in body
    assert "标签: USB-C, 科技" in body
    assert "播放: 1000" in body


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.tls = False
        self.logged_in = None
        self.sent = []
        FakeSMTP.instances.append(self)

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)

    def quit(self):
        self.quit_called = True


def test_send_email_uses_tls_login_and_sends():
    FakeSMTP.instances.clear()
    settings = EmailSettings(host="smtp.x", port=587, sender="a@x", to="b@y",
                             user="u", password="p", use_tls=True)
    send_email("subj", "body", settings, smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[0]
    assert smtp.tls and smtp.logged_in == ("u", "p")
    assert smtp.sent[0]["To"] == "b@y" and smtp.sent[0]["Subject"] == "subj"


def test_notify_returns_false_on_empty():
    assert notify([], EmailSettings("h", 25, "a", "b")) is False


def test_email_settings_is_complete():
    assert EmailSettings("h", 25, "a@x", "b@y").is_complete()
    assert not EmailSettings(None, 25, "a", "b").is_complete()


# --- CLI ---------------------------------------------------------------------

def test_cli_missing_config_returns_2(tmp_path):
    from monitor import cli
    assert cli.main(["--config", str(tmp_path / "no.json"), "--db", str(tmp_path / "d.db")]) == 2


def test_cli_missing_api_key_returns_2(tmp_path, monkeypatch):
    from monitor import cli
    cfg = tmp_path / "c.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    assert cli.main(["--config", str(cfg), "--db", str(tmp_path / "d.db")]) == 2


def test_cli_dry_run_prints_alerts(tmp_path, monkeypatch, capsys):
    from monitor import cli

    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"categories": {"life": {"channels": [{"id": "UC1"}]}}}), encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_API_KEY", "KEY")
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(cli, "YouTubeClient", lambda key: FakeClient({"UC1": [_cand("v1", views=5)]}))

    rc = cli.main(["--config", str(cfg), "--db", str(tmp_path / "d.db"), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run" in out and "v1" in out
