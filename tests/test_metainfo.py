from hashlib import sha1

from bittorrent.bencode import encode
from bittorrent.metainfo import parse_metainfo

def test_parse_single_file_metainfo():
    first_hash = b"a" * 20
    second_hash = b"b" * 20

    info = {
        b"length": 30_000,
        b"name": b"example.bin",
        b"piece length": 16_384,
        b"pieces": first_hash + second_hash,
    }

    torrent_data = encode({
        b"announce": b"http://tracker.test/announce",
        b"info": info,
    })

    meta = parse_metainfo(torrent_data)

    assert meta.announce == "http://tracker.test/announce"
    assert meta.name == "example.bin"
    assert meta.length == 30_000
    assert meta.piece_length == 16_384
    assert meta.piece_hashes == (first_hash, second_hash)
    assert meta.info_hash == sha1(encode(info)).digest()

import pytest

from bittorrent.metainfo import MetaInfoError


def make_torrent(info_changes=None):
    info = {
        b"length": 30_000,
        b"name": b"example.bin",
        b"piece length": 16_384,
        b"pieces": b"a" * 40,
    }

    if info_changes:
        info.update(info_changes)

    return encode({
        b"announce": b"http://tracker.test/announce",
        b"info": info,
    })

@pytest.mark.parametrize(
    "changes",
    [
        {b"length": -1},
        {b"length": b"30000"},
        {b"piece length": 0},
        {b"piece length": b"16384"},
        {b"pieces": b"a" * 19},
        {b"pieces": b"a" * 20},  # should contain two hashes
        {b"name": 42},
        {b"name": b"\xff"},
    ],
)
def test_reject_invalid_info(changes):
    with pytest.raises(MetaInfoError):
        parse_metainfo(make_torrent(changes))

@pytest.mark.parametrize(
    "missing_key",
    [
        b"name",
        b"length",
        b"piece length",
        b"pieces",
    ],
)
def test_reject_missing_info_field(missing_key):
    decoded = {
        b"length": 30_000,
        b"name": b"example.bin",
        b"piece length": 16_384,
        b"pieces": b"a" * 40,
    }

    del decoded[missing_key]

    torrent = encode({
        b"announce": b"http://tracker.test/announce",
        b"info": decoded,
    })

    with pytest.raises(MetaInfoError):
        parse_metainfo(torrent)

def test_reject_non_dictionary_info():
    torrent = encode({
        b"announce": b"http://tracker.test/announce",
        b"info": 42,
    })

    with pytest.raises(MetaInfoError):
        parse_metainfo(torrent)


def test_reject_non_bytes_announce():
    torrent = encode({
        b"announce": 42,
        b"info": {
            b"length": 0,
            b"name": b"empty",
            b"piece length": 16_384,
            b"pieces": b"",
        },
    })

    with pytest.raises(MetaInfoError):
        parse_metainfo(torrent)