from dataclasses import dataclass, field
import socket

from enum import IntEnum

PROTOCOL_NAME = b"BitTorrent protocol"
HANDSHAKE_LENGTH = 68

# 1 byte    protocol-name length: 19
# 19 bytes  b"BitTorrent protocol"
# 8 bytes   reserved extension flags
# 20 bytes  info_hash
# 20 bytes  peer_id
# --------------------------------
# 68 bytes total

class PeerProtocolError(ValueError):
    pass

@dataclass(frozen=True)
class Handshake:
    info_hash: bytes
    peer_id: bytes
    reserved: bytes 

def build_handshake(info_hash: bytes, peer_id: bytes, reserved: bytes = b"\x00" * 8) -> bytes:
    if not isinstance(info_hash, bytes) or not isinstance(peer_id, bytes) or not isinstance(reserved, bytes):
        raise PeerProtocolError("incorrect data format")
    
    if len(info_hash) != 20 or len(peer_id) != 20 or len(reserved) != 8:
        raise PeerProtocolError("incorrect handshake attempt")
    
    return bytes([len(PROTOCOL_NAME)]) + PROTOCOL_NAME + reserved + info_hash + peer_id 

def parse_handshake(data: bytes, expected_info_hash: bytes | None = None) -> Handshake:
    if not isinstance(data, bytes):
        raise TypeError("handshake data must be bytes")
    
    if len(data) != 68:
        raise PeerProtocolError("incorrect data")

    protocol_length = data[0]
    protocol_name = data[1:20]
    reserved = data[20:28]
    info_hash = data[28:48]
    peer_id = data[48:68]
    
    if protocol_length != len(PROTOCOL_NAME):
        raise PeerProtocolError("incorrect protocol name length")
    
    if protocol_name != PROTOCOL_NAME:
        raise PeerProtocolError("incorrect protocol name")
    
    if expected_info_hash is not None and info_hash != expected_info_hash:
        raise PeerProtocolError("recieved info hash does not match expected info hash")
    
    return Handshake(info_hash=info_hash, peer_id=peer_id, reserved=reserved)

def recv_exact(connection: socket.socket, size: int) -> bytes:
    if size < 0:
        raise ValueError("size cannot be negative")
    
    received = bytearray()
    
    while len(received) < size:
        remaining = size - len(received)
        chunk = connection.recv(remaining)

        if not chunk:
            raise PeerProtocolError("peer closed the connection unexpectedly")
        
        received.extend(chunk)

    return bytes(received)

def exchange_handshake(connection: socket.socket, info_hash: bytes, peer_id: bytes) -> Handshake:
    outgoing = build_handshake(info_hash, peer_id)
    connection.sendall(outgoing)

    incoming = recv_exact(connection, HANDSHAKE_LENGTH)

    return parse_handshake(incoming, expected_info_hash=info_hash)

@dataclass
class PeerConnection:
    socket: socket.socket
    handshake: Handshake

    def close(self):
        self.socket.close()

def connect_to_peer(
    ip: str,
    port: int,
    info_hash: bytes,
    peer_id: bytes,
    timeout: float = 10.0,
) -> PeerConnection:
    
    connection = None
    
    try: 
        connection = socket.create_connection((ip, port), timeout=timeout)
        handshake = exchange_handshake(connection, info_hash, peer_id)
        return PeerConnection(connection, handshake)
    
    except Exception:
        if connection is not None:
            connection.close()

        raise 

# After the handshake, the connection becomes a stream of messages 
# 4-byte length prefix | 1-byte message ID | payload
# message_id = None means keepalive and requires empty payload
@dataclass(frozen=True)
class PeerMessage:
    message_id: int | None
    payload: bytes

def build_message(message_id: int | None, payload: bytes = b"") -> bytes:
    
    if not isinstance(payload, bytes):
        raise PeerProtocolError("Payload must be bytes")
    
    if message_id is None and payload != b"":
        raise PeerProtocolError("message_id = None means keepalive and requires empty payload")
    
    body = bytes()

    if message_id is not None:
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise PeerProtocolError("message ID must be an integer")
        
        if not (message_id <= 255 and message_id >= 0):
            raise PeerProtocolError("Message ID must be between 0 and 255")
        else:
            body = message_id.to_bytes(1, byteorder="big")

    body += payload

    body_length = len(body).to_bytes(4, byteorder="big")
    message = body_length + body
    return message

def read_message(connection: socket.socket) -> PeerMessage:
    length_bytes = recv_exact(connection, 4)
    length = int.from_bytes(length_bytes, "big")

    if length == 0:
        return PeerMessage(None, b"")
    
    body = recv_exact(connection, length)

    return PeerMessage(message_id=body[0], payload=body[1:])
    

class MessageID(IntEnum):
    CHOKE = 0 # No payload
    UNCHOKE = 1
    INTERESTED = 2 # No payload
    NOT_INTERESTED = 3
    HAVE = 4 # One 4-byte piece index
    BITFIELD = 5 # Bits representing available pieces
    REQUEST = 6 # Piece index + block offset + block length
    PIECE = 7 # Piece index + block offset + raw file bytes
    CANCEL = 8

def build_have(piece_index: int) -> bytes:
    if not isinstance(piece_index, int) or isinstance(piece_index, bool):
        raise PeerProtocolError("Must be an integer")
    
    if not 0 <= piece_index <= 0xFFFFFFFF:
        raise PeerProtocolError("Must fit in four unsigned bytes")
    
    payload = piece_index.to_bytes(4, "big")
    message = build_message(MessageID.HAVE, payload)
    return message

# 00 00 00 05 | 04 | 00 00 00 07
# length=5      ID    payload
#                     piece index 7

def parse_have(message: PeerMessage) -> int:
    if not isinstance(message, PeerMessage):
        raise PeerProtocolError("Incorrect message type")

    message_id = message.message_id
    payload = message.payload

    if message_id != MessageID.HAVE:
        raise PeerProtocolError("Not a have message")
    
    if len(payload) != 4:
        raise PeerProtocolError("Incorrect payload size")

    return int.from_bytes(message.payload, "big") 

# Bitfield byte: 10110000
# Piece index:   01234567
# Peer has pieces 0, 2, and 3.

# If there are ten pieces, the bitfield needs two bytes:
# First byte:  pieces 0–7
# Second byte: pieces 8–9 + six unused bits

def parse_bitfield(message: PeerMessage, piece_count: int) -> tuple[bool, ...]:
    if not isinstance(message, PeerMessage):
        raise PeerProtocolError("Incorrect message type")
    
    if not isinstance(piece_count, int) or isinstance(piece_count, bool):
        raise PeerProtocolError("Incorrect piece_count type")

    message_id = message.message_id
    payload = message.payload

    if message_id != MessageID.BITFIELD:
        raise PeerProtocolError("Not a bitfield message")
    
    if piece_count < 0:
        raise PeerProtocolError("piece count must be non negative integer")
    
    expected_bytes = (piece_count + 7) // 8

    if len(payload) != expected_bytes:
        raise PeerProtocolError("incorrect payload length")

    pieces = []

    for piece_index in range(piece_count):
        byte_index = piece_index // 8
        bit_position = 7 - (piece_index % 8)

        has_piece = bool(payload[byte_index] & (1 << bit_position))
        pieces.append(has_piece)

    remainder = piece_count % 8
    if remainder and payload:
        unused_count = 8 - remainder
        unused_mask = (1 << unused_count) - 1

        if message.payload[-1] & unused_mask:
            raise PeerProtocolError("bitfield spare bits must be zero")

    return tuple(pieces)

# Connect
#   → peer initially chokes us
#   → peer sends bitfield
#   → peer sends unchoke
#   → peer sends have(7)

# We need to remember the result of peer choking us and peer pieces 

@dataclass
class PeerState:
    piece_count: int
    peer_choking_us: bool = True
    peer_interested_in_us: bool = False 
    peer_pieces: list[bool] = field(init=False) # means callers don’t supply peer_pieces

    def __post_init__(self):
        if (
            not isinstance(self.piece_count, int)
            or isinstance(self.piece_count, bool)
            or self.piece_count < 0
        ):
            raise PeerProtocolError("piece count must be a non negative integer")
        
        self.peer_pieces = [False] * self.piece_count
        

def apply_peer_message(state: PeerState, message: PeerMessage) -> None:
    if message.message_id is None:
        # Keepalive changes no state
        return 
    
    if message.message_id in {
        MessageID.CHOKE,
        MessageID.UNCHOKE,
        MessageID.INTERESTED,
        MessageID.NOT_INTERESTED,
    }:
        if message.payload: 
            raise PeerProtocolError("control messages cannot have a payload")
        
        if message.message_id == MessageID.CHOKE:
            state.peer_choking_us = True

        elif message.message_id == MessageID.UNCHOKE:
            state.peer_choking_us = False

        elif message.message_id == MessageID.INTERESTED:
            state.peer_interested_in_us = True

        elif message.message_id == MessageID.NOT_INTERESTED:
            state.peer_interested_in_us = False

    elif message.message_id == MessageID.HAVE:
        piece_index = parse_have(message)

        if piece_index >= state.piece_count:
            raise PeerProtocolError("have piece index is out of range")

        state.peer_pieces[piece_index] = True

    elif message.message_id == MessageID.BITFIELD:
        pieces = parse_bitfield(message, state.piece_count,)
        state.peer_pieces = list(pieces)

