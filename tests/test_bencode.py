import pytest

from bittorrent.bencode import BencodeDecodeError, decode


# Integers

@pytest.mark.parametrize(
    ("encoded", "expected"),
    [
        (b"i0e", 0),
        (b"i42e", 42),
        (b"i-42e", -42),
    ],
)
def test_decode_integer(encoded, expected):
    assert decode(encoded) == expected


@pytest.mark.parametrize(
    "encoded",
    [
        b"ie",       # empty integer
        b"i-0e",     # negative zero
        b"i03e",     # leading zero
        b"i-03e",    # negative leading zero
        b"i+3e",     # plus sign
        b"i4.2e",    # not an integer
        b"i12",      # missing terminator
    ],
)
def test_reject_invalid_integer(encoded):
    with pytest.raises(BencodeDecodeError):
        decode(encoded)


# Byte strings

@pytest.mark.parametrize(
    ("encoded", "expected"),
    [
        (b"0:", b""),
        (b"4:spam", b"spam"),
        (b"5:hello", b"hello"),
        (b"3:\xff\x00a", b"\xff\x00a"),
    ],
)
def test_decode_bytes(encoded, expected):
    assert decode(encoded) == expected


@pytest.mark.parametrize(
    "encoded",
    [
        b"4spam",     # missing colon
        b"5:spam",    # content too short
        b"2:a",       # content too short
        b"1x:a",      # invalid length
    ],
)
def test_reject_invalid_byte_string(encoded):
    with pytest.raises(BencodeDecodeError):
        decode(encoded)


# Lists

def test_decode_empty_list():
    assert decode(b"le") == []


def test_decode_list():
    assert decode(b"l4:spami42ee") == [b"spam", 42]


def test_decode_nested_list():
    assert decode(b"lli1ei2eel1:a1:bee") == [
        [1, 2],
        [b"a", b"b"],
    ]


@pytest.mark.parametrize(
    "encoded",
    [
        b"l",
        b"li1e",
        b"l4:spam",
    ],
)
def test_reject_unterminated_list(encoded):
    with pytest.raises(BencodeDecodeError):
        decode(encoded)


# Dictionaries

def test_decode_empty_dictionary():
    assert decode(b"de") == {}


def test_decode_dictionary():
    assert decode(b"d3:cow3:moo4:spam4:eggse") == {
        b"cow": b"moo",
        b"spam": b"eggs",
    }


def test_decode_nested_dictionary():
    assert decode(b"d4:listli1ei2ee4:name4:spame") == {
        b"list": [1, 2],
        b"name": b"spam",
    }


def test_dictionary_keys_must_be_bytes():
    with pytest.raises(BencodeDecodeError):
        decode(b"di1e3:onee")


def test_dictionary_keys_must_be_sorted():
    with pytest.raises(BencodeDecodeError):
        decode(b"d4:spam1:a3:cow1:be")


@pytest.mark.parametrize(
    "encoded",
    [
        b"d",
        b"d3:key",
        b"d3:keyi1e",
    ],
)
def test_reject_unterminated_dictionary(encoded):
    with pytest.raises(BencodeDecodeError):
        decode(encoded)


# Top-level validation

def test_reject_trailing_data():
    with pytest.raises(BencodeDecodeError):
        decode(b"i1ei2e")


def test_reject_empty_input():
    with pytest.raises(BencodeDecodeError):
        decode(b"")


def test_input_must_be_bytes():
    with pytest.raises(TypeError):
        decode("4:spam")


from bittorrent.bencode import BencodeEncodeError, encode


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, b"i0e"),
        (42, b"i42e"),
        (-42, b"i-42e"),
        (b"", b"0:"),
        (b"spam", b"4:spam"),
        ([b"spam", 42], b"l4:spami42ee"),
        ({}, b"de"),
        (
            {b"spam": b"eggs", b"cow": b"moo"},
            b"d3:cow3:moo4:spam4:eggse",
        ),
    ],
)
def test_encode(value, expected):
    assert encode(value) == expected


def test_encode_nested_value():
    value = {b"numbers": [1, 2], b"title": b"demo"}

    assert decode(encode(value)) == value


@pytest.mark.parametrize(
    "value",
    [
        "text",
        None,
        True,
        3.14,
        {1: b"invalid key"},
    ],
)
def test_reject_unsupported_encode_value(value):
    with pytest.raises(BencodeEncodeError):
        encode(value)