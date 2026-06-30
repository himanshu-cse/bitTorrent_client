import pytest

from bittorrent.peer_protocol import (
    HANDSHAKE_LENGTH,
    Handshake,
    PeerProtocolError,
    build_handshake,
    parse_handshake,
)


INFO_HASH = b"i" * 20
PEER_ID = b"-PY0001-" + b"A" * 12


def test_build_handshake():
    data = build_handshake(INFO_HASH, PEER_ID)

    assert len(data) == HANDSHAKE_LENGTH
    assert data[0] == 19
    assert data[1:20] == b"BitTorrent protocol"
    assert data[20:28] == b"\x00" * 8
    assert data[28:48] == INFO_HASH
    assert data[48:68] == PEER_ID


def test_parse_handshake():
    data = build_handshake(INFO_HASH, PEER_ID)

    assert parse_handshake(data, INFO_HASH) == Handshake(
        info_hash=INFO_HASH,
        peer_id=PEER_ID,
        reserved=b"\x00" * 8,
    )


def test_handshake_round_trip():
    data = build_handshake(INFO_HASH, PEER_ID)

    parsed = parse_handshake(data)
    rebuilt = build_handshake(
        parsed.info_hash,
        parsed.peer_id,
        parsed.reserved,
    )

    assert rebuilt == data


@pytest.mark.parametrize(
    "info_hash",
    [b"", b"x" * 19, b"x" * 21],
)
def test_reject_invalid_info_hash(info_hash):
    with pytest.raises(PeerProtocolError):
        build_handshake(info_hash, PEER_ID)


@pytest.mark.parametrize(
    "peer_id",
    [b"", b"x" * 19, b"x" * 21],
)
def test_reject_invalid_peer_id(peer_id):
    with pytest.raises(PeerProtocolError):
        build_handshake(INFO_HASH, peer_id)


def test_reject_wrong_handshake_length():
    with pytest.raises(PeerProtocolError):
        parse_handshake(b"x" * 67)


def test_reject_wrong_protocol_name():
    data = bytearray(build_handshake(INFO_HASH, PEER_ID))
    data[1:20] = b"NotTorrent protocol!"

    with pytest.raises(PeerProtocolError):
        parse_handshake(bytes(data))


def test_reject_unexpected_info_hash():
    data = build_handshake(INFO_HASH, PEER_ID)

    with pytest.raises(PeerProtocolError):
        parse_handshake(data, expected_info_hash=b"x" * 20)


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.requested_sizes = []
        self.sent = bytearray()
        self.closed = False

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, size):
        self.requested_sizes.append(size)

        if not self.chunks:
            return b""

        return self.chunks.pop(0)
    
    def close(self):
        self.closed = True

from bittorrent.peer_protocol import recv_exact


def test_recv_exact_in_one_chunk():
    connection = FakeSocket([b"hello"])

    assert recv_exact(connection, 5) == b"hello"


def test_recv_exact_from_multiple_chunks():
    connection = FakeSocket([
        b"he",
        b"l",
        b"lo",
    ])

    assert recv_exact(connection, 5) == b"hello"
    assert connection.requested_sizes == [5, 3, 2]


def test_recv_exact_zero_bytes():
    connection = FakeSocket([])

    assert recv_exact(connection, 0) == b""


def test_recv_exact_rejects_early_disconnect():
    connection = FakeSocket([b"he", b""])

    with pytest.raises(
        PeerProtocolError,
        match="closed",
    ):
        recv_exact(connection, 5)


def test_recv_exact_rejects_negative_size():
    connection = FakeSocket([])

    with pytest.raises(ValueError):
        recv_exact(connection, -1)

from bittorrent.peer_protocol import exchange_handshake


def test_exchange_handshake():
    remote_peer_id = b"-REMOTE1-" + b"B" * 11
    remote_handshake = build_handshake(
        INFO_HASH,
        remote_peer_id,
    )

    connection = FakeSocket([
        remote_handshake[:10],
        remote_handshake[10:],
    ])

    result = exchange_handshake(
        connection,
        INFO_HASH,
        PEER_ID,
    )

    assert bytes(connection.sent) == build_handshake(
        INFO_HASH,
        PEER_ID,
    )

    assert result == Handshake(
        info_hash=INFO_HASH,
        peer_id=remote_peer_id,
        reserved=b"\x00" * 8,
    )


from bittorrent.peer_protocol import (
    PeerConnection,
    connect_to_peer,
)


def test_connect_to_peer(monkeypatch):
    remote_peer_id = b"-REMOTE1-" + b"B" * 11
    remote_handshake = build_handshake(
        INFO_HASH,
        remote_peer_id,
    )

    fake_socket = FakeSocket([remote_handshake])
    captured = {}

    def fake_create_connection(address, timeout):
        captured["address"] = address
        captured["timeout"] = timeout
        return fake_socket

    monkeypatch.setattr(
        "bittorrent.peer_protocol.socket.create_connection",
        fake_create_connection,
    )

    result = connect_to_peer(
        ip="127.0.0.1",
        port=6881,
        info_hash=INFO_HASH,
        peer_id=PEER_ID,
        timeout=5.0,
    )

    assert isinstance(result, PeerConnection)
    assert result.socket is fake_socket
    assert result.handshake.peer_id == remote_peer_id
    assert captured["address"] == ("127.0.0.1", 6881)
    assert captured["timeout"] == 5.0
    assert fake_socket.closed is False

def test_connect_to_peer_closes_failed_connection(monkeypatch):
    remote_handshake = build_handshake(
        b"x" * 20,  # wrong torrent
        b"-REMOTE1-" + b"B" * 11,
    )

    fake_socket = FakeSocket([remote_handshake])

    monkeypatch.setattr(
        "bittorrent.peer_protocol.socket.create_connection",
        lambda address, timeout: fake_socket,
    )

    with pytest.raises(PeerProtocolError):
        connect_to_peer(
            "127.0.0.1",
            6881,
            INFO_HASH,
            PEER_ID,
        )

    assert fake_socket.closed is True


from bittorrent.peer_protocol import (build_message, read_message, PeerMessage)

def test_build_keepalive():
    assert build_message(None) == b"\x00\x00\x00\x00"


def test_build_interested_message():
    assert build_message(2) == (
        b"\x00\x00\x00\x01"
        b"\x02"
    )


def test_build_message_with_payload():
    assert build_message(4, b"\x00\x00\x00\x07") == (
        b"\x00\x00\x00\x05"
        b"\x04"
        b"\x00\x00\x00\x07"
    )


def test_read_keepalive():
    connection = FakeSocket([b"\x00\x00\x00\x00"])

    assert read_message(connection) == PeerMessage(
        message_id=None,
        payload=b"",
    )


def test_read_message():
    connection = FakeSocket([
        b"\x00\x00\x00\x05",
        b"\x04\x00\x00\x00\x07",
    ])

    assert read_message(connection) == PeerMessage(
        message_id=4,
        payload=b"\x00\x00\x00\x07",
    )

from bittorrent.peer_protocol import (
    MessageID,
    build_have,
    parse_have,
)


def test_build_have():
    assert build_have(7) == (
        b"\x00\x00\x00\x05"
        b"\x04"
        b"\x00\x00\x00\x07"
    )


def test_parse_have():
    message = PeerMessage(
        message_id=MessageID.HAVE,
        payload=b"\x00\x00\x00\x07",
    )

    assert parse_have(message) == 7


def test_reject_have_with_wrong_payload_size():
    message = PeerMessage(
        message_id=MessageID.HAVE,
        payload=b"\x00\x07",
    )

    with pytest.raises(PeerProtocolError):
        parse_have(message)


def test_reject_wrong_message_as_have():
    message = PeerMessage(
        message_id=MessageID.INTERESTED,
        payload=b"",
    )

    with pytest.raises(PeerProtocolError):
        parse_have(message)


@pytest.mark.parametrize("piece_index", [-1, True, 2**32])
def test_reject_invalid_have_index(piece_index):
    with pytest.raises(PeerProtocolError):
        build_have(piece_index)



from bittorrent.peer_protocol import parse_bitfield


def test_parse_bitfield():
    message = PeerMessage(
        message_id=MessageID.BITFIELD,
        payload=bytes([0b10110000]),
    )

    assert parse_bitfield(message, 8) == (
        True,
        False,
        True,
        True,
        False,
        False,
        False,
        False,
    )


def test_parse_bitfield_with_partial_final_byte():
    message = PeerMessage(
        message_id=MessageID.BITFIELD,
        payload=bytes([
            0b10110000,
            0b01000000,
        ]),
    )

    assert parse_bitfield(message, 10) == (
        True,
        False,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        True,
    )


def test_parse_empty_bitfield():
    message = PeerMessage(
        message_id=MessageID.BITFIELD,
        payload=b"",
    )

    assert parse_bitfield(message, 0) == ()


def test_reject_wrong_bitfield_size():
    message = PeerMessage(
        message_id=MessageID.BITFIELD,
        payload=b"\x00",
    )

    with pytest.raises(PeerProtocolError):
        parse_bitfield(message, 9)


def test_reject_nonzero_spare_bits():
    message = PeerMessage(
        message_id=MessageID.BITFIELD,
        payload=bytes([0b10000001]),
    )

    with pytest.raises(PeerProtocolError):
        parse_bitfield(message, 1)

from bittorrent.peer_protocol import (PeerState, apply_peer_message)


def test_peer_state_initial_values():
    state = PeerState(piece_count=4)

    assert state.peer_choking_us is True
    assert state.peer_interested_in_us is False
    assert state.peer_pieces == [False] * 4


def test_apply_unchoke():
    state = PeerState(piece_count=4)

    apply_peer_message(
        state,
        PeerMessage(MessageID.UNCHOKE, b""),
    )

    assert state.peer_choking_us is False


def test_apply_have():
    state = PeerState(piece_count=4)

    apply_peer_message(
        state,
        PeerMessage(
            MessageID.HAVE,
            (2).to_bytes(4, "big"),
        ),
    )

    assert state.peer_pieces == [
        False,
        False,
        True,
        False,
    ]


def test_apply_bitfield():
    state = PeerState(piece_count=4)

    apply_peer_message(
        state,
        PeerMessage(
            MessageID.BITFIELD,
            bytes([0b10100000]),
        ),
    )

    assert state.peer_pieces == [
        True,
        False,
        True,
        False,
    ]


def test_reject_out_of_range_have():
    state = PeerState(piece_count=4)

    with pytest.raises(PeerProtocolError):
        apply_peer_message(
            state,
            PeerMessage(
                MessageID.HAVE,
                (4).to_bytes(4, "big"),
            ),
        )