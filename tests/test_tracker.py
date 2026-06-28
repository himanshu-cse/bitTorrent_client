import pytest

from bittorrent.tracker import (Peer, TrackerError, parse_compact_peers,)


def test_parse_empty_compact_peer_list():
    assert parse_compact_peers(b"") == ()


def test_parse_one_compact_peer():
    data = bytes([127, 0, 0, 1]) + (6881).to_bytes(2, "big")

    assert parse_compact_peers(data) == (
        Peer(ip="127.0.0.1", port=6881),
    )


def test_parse_multiple_compact_peers():
    first = bytes([192, 168, 1, 10]) + (6881).to_bytes(2, "big")
    second = bytes([8, 8, 8, 8]) + (51413).to_bytes(2, "big")

    assert parse_compact_peers(first + second) == (
        Peer(ip="192.168.1.10", port=6881),
        Peer(ip="8.8.8.8", port=51413),
    )


def test_reject_incomplete_compact_peer():
    with pytest.raises(TrackerError):
        parse_compact_peers(b"\x7f\x00\x00\x01\x1a")


def test_compact_peers_must_be_bytes():
    with pytest.raises(TypeError):
        parse_compact_peers("not bytes")

from bittorrent.bencode import encode
from bittorrent.tracker import TrackerResponse, parse_tracker_response

def test_parse_tracker_response():
    compact_peers = (bytes([127, 0, 0, 1]) + (6881).to_bytes(2, "big"))

    data = encode({b"interval": 1800, b"peers": compact_peers,})

    assert parse_tracker_response(data) == TrackerResponse(interval=1800, peers=(Peer("127.0.0.1", 6881),),)


def test_parse_tracker_failure():
    data = encode({b"failure reason": b"torrent not registered",})

    with pytest.raises(TrackerError, match="torrent not registered",):
        parse_tracker_response(data)


@pytest.mark.parametrize(
    "response",
    [
        [],
        {},
        {b"interval": 1800},
        {b"peers": b""},
        {b"interval": 0, b"peers": b""},
        {b"interval": b"1800", b"peers": b""},
        {b"interval": 1800, b"peers": b"invalid"},
    ],
)
def test_reject_invalid_tracker_response(response):
    with pytest.raises(TrackerError):
        parse_tracker_response(encode(response))


def test_reject_malformed_bencoded_tracker_response():
    with pytest.raises(TrackerError):
        parse_tracker_response(b"d8:intervali1800e")


from bittorrent.tracker import build_announce_url


def test_build_announce_url():
    info_hash = b" " * 20
    peer_id = b"-PY0001-" + b"A" * 12

    url = build_announce_url(
        announce="http://tracker.test/announce",
        info_hash=info_hash,
        peer_id=peer_id,
        port=6881,
        uploaded=0,
        downloaded=100,
        left=29_900,
    )

    assert url.startswith("http://tracker.test/announce?")
    assert f"info_hash={'%20' * 20}" in url
    assert "peer_id=-PY0001-AAAAAAAAAAAA" in url
    assert "port=6881" in url
    assert "uploaded=0" in url
    assert "downloaded=100" in url
    assert "left=29900" in url
    assert "compact=1" in url
    assert "event=started" in url


@pytest.mark.parametrize(
    ("info_hash", "peer_id", "port"),
    [
        (b"x" * 19, b"y" * 20, 6881),
        (b"x" * 20, b"y" * 19, 6881),
        (b"x" * 20, b"y" * 20, 0),
        (b"x" * 20, b"y" * 20, 65536),
    ],
)
def test_reject_invalid_announce_parameters(
    info_hash,
    peer_id,
    port,
):
    with pytest.raises(TrackerError):
        build_announce_url(
            "http://tracker.test/announce",
            info_hash,
            peer_id,
            port,
            uploaded=0,
            downloaded=0,
            left=100,
        )

from bittorrent.tracker import generate_peer_id

def test_generate_peer_id():
    peer_id = generate_peer_id()

    assert isinstance(peer_id, bytes)
    assert len(peer_id) == 20
    assert peer_id.startswith(b"-PY0001-")


def test_generate_different_peer_ids():
    assert generate_peer_id() != generate_peer_id()

from urllib.error import URLError
from bittorrent.tracker import request_tracker

class FakeHTTPResponse:
    def __init__(self, data: bytes):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False
    
def test_request_tracker(monkeypatch):
    response_data = encode({
        b"interval": 1800,
        b"peers": (
            bytes([127, 0, 0, 1])
            + (6881).to_bytes(2, "big")
        ),
    })

    def fake_urlopen(url, timeout):
        assert url == "http://tracker.test/announce"
        assert timeout == 5.0
        return FakeHTTPResponse(response_data)

    monkeypatch.setattr(
        "bittorrent.tracker.urlopen",
        fake_urlopen,
    )

    response = request_tracker(
        "http://tracker.test/announce",
        timeout=5.0,
    )

    assert response == TrackerResponse(
        interval=1800,
        peers=(Peer("127.0.0.1", 6881),),
    )

def test_request_tracker_network_failure(monkeypatch):
    def failing_urlopen(url, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(
        "bittorrent.tracker.urlopen",
        failing_urlopen,
    )

    with pytest.raises(
        TrackerError,
        match="tracker request failed",
    ):
        request_tracker("http://tracker.test/announce")

from bittorrent.metainfo import TorrentMeta
from bittorrent.tracker import announce_to_tracker


def test_announce_to_tracker(monkeypatch):
    meta = TorrentMeta(
        announce="http://tracker.test/announce",
        name="example.bin",
        length=30_000,
        piece_length=16_384,
        piece_hashes=(b"a" * 20, b"b" * 20),
        info_hash=b"i" * 20,
    )

    expected_response = TrackerResponse(
        interval=1800,
        peers=(Peer("127.0.0.1", 6881),),
    )

    captured = {}

    def fake_request_tracker(url, timeout):
        captured["url"] = url
        captured["timeout"] = timeout
        return expected_response

    monkeypatch.setattr(
        "bittorrent.tracker.request_tracker",
        fake_request_tracker,
    )

    response = announce_to_tracker(
        meta,
        peer_id=b"-PY0001-" + b"A" * 12,
        timeout=5.0,
    )

    assert response == expected_response
    assert captured["timeout"] == 5.0
    assert "info_hash=" in captured["url"]
    assert "left=30000" in captured["url"]
    assert "event=started" in captured["url"]