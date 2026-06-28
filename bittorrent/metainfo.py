from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path

from bittorrent.bencode import decode, encode

class MetaInfoError(ValueError):
    pass

@dataclass(frozen=True)
class TorrentMeta:
    announce: str
    name: str
    length: int
    piece_length: int
    piece_hashes: tuple[bytes, ...]
    info_hash: bytes

def parse_metainfo(data: bytes) -> TorrentMeta:
    decoded_data = decode(data)
    if not isinstance(decoded_data, dict):
        raise MetaInfoError("data not dict")
    
    try:
        announce_bytes = decoded_data[b"announce"]
        info = decoded_data[b"info"]
    except KeyError as error:
        raise MetaInfoError(f"missing metainfo field: {error}") from error

    if not isinstance(announce_bytes, bytes):
        raise MetaInfoError("announce must be bytes")

    try:
        announce = announce_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MetaInfoError("announce must be valid UTF-8") from error

    if not isinstance(info, dict):
        raise MetaInfoError("info must be a dictionary")

    try:
        name_bytes = info[b"name"]
        length = info[b"length"]
        piece_length = info[b"piece length"]
        pieces = info[b"pieces"]
    except KeyError as error:
        raise MetaInfoError(f"missing info field: {error}") from error
    
    if not isinstance(name_bytes, bytes):
        raise MetaInfoError("name must be bytes")

    try:
        name = name_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MetaInfoError("name must be valid UTF-8") from error

    if not isinstance(length, int) or isinstance(length, bool):
        raise MetaInfoError("length must be an integer")
    if length < 0:
        raise MetaInfoError("length cannot be negative")
    
    if not isinstance(piece_length, int) or isinstance(piece_length, bool):
        raise MetaInfoError("piece length must be an integer")
    if piece_length <= 0:
        raise MetaInfoError("piece length must be positive")
    
    if not isinstance(pieces, bytes):
        raise MetaInfoError("pieces must be bytes")
    if len(pieces) % 20 != 0:
        raise MetaInfoError("pieces length must be a multiple of 20")
    
    expected_count = (length + piece_length - 1) // piece_length
    actual_count = len(pieces) // 20
    if actual_count != expected_count:
        raise MetaInfoError("incorrect number of piece hashes")
    
    piece_hashes = tuple(pieces[i:i+20] for i in range(0, len(pieces), 20))
    info_hash = sha1(encode(info)).digest()

    return TorrentMeta(
        announce=announce,
        name=name,
        length=length,
        piece_length=piece_length,
        piece_hashes=piece_hashes,
        info_hash=info_hash,
    )

def load_metainfo(path: str | Path) -> TorrentMeta:
    return parse_metainfo(Path(path).read_bytes())
