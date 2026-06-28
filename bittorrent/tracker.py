# tracker returns address, port of active peers as one byte string
# every peer occupies 6 bytes -> 4 bytes IPv4 address + 2 bytes port, unsigned big-endian
# example:
#  7F 00 00 01 1A E1
# └─ 127.0.0.1 ─┘ └6881┘

from dataclasses import dataclass
from turtle import up
from bittorrent.bencode import BencodeDecodeError, decode

from urllib.parse import quote_from_bytes # used to safely convert bytes into URL-encoded strings

import secrets
import string

from urllib.error import URLError
from urllib.request import urlopen

from bittorrent.metainfo import TorrentMeta

class TrackerError(ValueError):
    pass

@dataclass(frozen=True)
class Peer:
    ip: str
    port: int

def parse_compact_peers(data: bytes) -> tuple[Peer, ...]:
    if not isinstance(data, bytes):
        raise TypeError("data not bytes")
    if len(data)%6 != 0:
        raise TrackerError("data length is supposed to be multiple of 6")
    return tuple(
        Peer(
            ".".join(map(str, data[i:i+4])),
            int.from_bytes(data[i+4:i+6], "big")
        )
        for i in range(0, len(data), 6)
    )

@dataclass(frozen=True)
class TrackerResponse:
    interval: int
    peers: tuple[Peer, ...]

def parse_tracker_response(data: bytes) -> TrackerResponse:
    if not isinstance(data, bytes):
        raise TypeError("data not bytes")
    
    try:
        data_dict = decode(data)
    except BencodeDecodeError as error:
        raise TrackerError("Failed to decode tracker response") from error

    if not isinstance(data_dict, dict):
        raise TrackerError("data not dict")
    
    if b"failure reason" in data_dict:
        reason = data_dict[b"failure reason"].decode("utf-8")
        raise TrackerError(f"failure: {reason}")
    
    try:
        interval = data_dict[b"interval"]
        peers_bytes = data_dict[b"peers"]
    except KeyError as error:
        raise TrackerError("incorrect data dict") from error
    
    if not isinstance(interval, int) or isinstance(interval, bool):
        raise TrackerError("interval not int")
    if interval <= 0:
        raise TrackerError("interval supposed to be positive integer")
    
    peers = parse_compact_peers(peers_bytes)

    return TrackerResponse(interval, peers)

def build_announce_url(
    announce: str, 
    info_hash: bytes, 
    peer_id: bytes, 
    port: int, 
    uploaded: int, 
    downloaded: int, 
    left: int, 
    event: str = "started",
    ) -> str:

    if not isinstance(info_hash, bytes):
        raise TypeError("info hash must be bytes")

    if not isinstance(peer_id, bytes):
        raise TypeError("peer ID must be bytes")

    if len(info_hash) != 20:
        raise TrackerError("info hash must contain 20 bytes")

    if len(peer_id) != 20:
        raise TrackerError("peer ID must contain 20 bytes")

    if not 1 <= port <= 65535:
        raise TrackerError("invalid listening port")

    if min(uploaded, downloaded, left) < 0:
        raise TrackerError("transfer counts cannot be negative")

    encoded_info_hash = quote_from_bytes(info_hash, safe="")
    encoded_peer_id = quote_from_bytes(peer_id, safe="")

    parameters = [
        f"info_hash={encoded_info_hash}",
        f"peer_id={encoded_peer_id}",
        f"port={port}",
        f"uploaded={uploaded}",
        f"downloaded={downloaded}",
        f"left={left}",
        "compact=1",
        f"event={event}",
    ]

    separator = "&" if "?" in announce else "?"

    # eg.- http://tracker/announce?info_hash=<20 binary bytes>&peer_id=<20 bytes>&port=6881&uploaded=0&downloaded=0&left=30000&compact=1&event=started
    return announce + separator + "&".join(parameters)
      
def generate_peer_id() -> bytes:
    prefix = "-PY0001-"
    alphabet = string.ascii_letters + string.digits

    random_part = "".join(secrets.choice(alphabet) for _ in range(12))

    return (prefix + random_part).encode("ascii") # prefix(8 bytes) + random(12 bytes)

def request_tracker(url: str, timeout: float = 10.0) -> TrackerResponse:
    if not isinstance(url, str):
        raise TypeError("tracker URL must be a string")
    if timeout <= 0:
        raise TrackerError("timeout not positive")
    
    try:
        with urlopen(url, timeout=timeout) as response:
            response_data = response.read()
    except (URLError, TimeoutError, OSError) as error:
        raise TrackerError(f"tracker request failed: {error}") from error
    
    return parse_tracker_response(response_data)

def announce_to_tracker(
    meta: TorrentMeta,
    peer_id: bytes,
    port: int = 6881,
    uploaded: int = 0,
    downloaded: int = 0,
    left: int | None = None,
    event: str = "started",
    timeout: float = 10.0,
) -> TrackerResponse:
    
    if left is None:
        left = meta.length

    url = build_announce_url(
        announce=meta.announce, 
        info_hash=meta.info_hash,
        peer_id=peer_id,
        port=port,
        uploaded=uploaded,
        downloaded=downloaded,
        left=left,
        event=event, 
        )
    
    return request_tracker(url=url, timeout=timeout)


    







