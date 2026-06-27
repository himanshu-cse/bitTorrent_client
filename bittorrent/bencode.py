class BencodeDecodeError(ValueError):
    pass

class BencodeEncodeError(TypeError):
    pass

def _decode_integer(data: bytes, index: int):
    end_index = data.find(b"e", index + 1)
    if end_index == -1:
        raise BencodeDecodeError("unterminated integer")

    raw = data[index + 1:end_index]

    if not raw:
        raise BencodeDecodeError("empty integer")

    if raw == b"-0":
        raise BencodeDecodeError("negative zero is invalid")

    if (raw.startswith(b"0") and len(raw) > 1) or raw.startswith(b"-0"):
        raise BencodeDecodeError("leading zero is invalid")
    
    if raw.startswith(b"+"):
        raise BencodeDecodeError("plus sign is invalid")

    try:
        value = int(raw)
    except ValueError as error:
        raise BencodeDecodeError("invalid integer") from error
    return value, end_index+1

def _decode_bytes(data: bytes, index: int):
    colon = data.find(b":", index)
    if colon == -1:
        raise BencodeDecodeError("missing colon in byte string")

    try:
        length = int(data[index:colon])
    except ValueError as error:
        raise BencodeDecodeError("invalid byte string length") from error
    start = colon + 1
    end = start + length
    if end > len(data):
        raise BencodeDecodeError("unexpected end of byte string")
    return data[start:end], end

def _decode_list(data: bytes, index: int):
    res = []
    index += 1
    while True:
        if index >= len(data):
            raise BencodeDecodeError("unterminated list")
        
        if data[index] == ord("e"):
            return res, index + 1
        
        item, index = _decode_at(data, index)
        res.append(item)

def _decode_dictionary(data: bytes, index: int):
    res = dict()
    previous_key = None
    index += 1

    while True:
        if index >= len(data):
            raise BencodeDecodeError("unterminated dictionary")
        
        if data[index] == ord("e"):
            return res, index + 1
        

        key, index = _decode_at(data, index)
        if not isinstance(key, bytes):
            raise BencodeDecodeError("dictionary keys must be byte strings")
        
        if previous_key is not None and key <= previous_key:
            raise BencodeDecodeError("dictionary keys must be sorted")

        previous_key = key

        if index >= len(data):
            raise BencodeDecodeError("dictionary key has no value")
        
        value, index = _decode_at(data, index)

        res[key] = value
    
def _decode_at(data: bytes, index: int):
    if index >= len(data):
        raise BencodeDecodeError("unexpected end of data")
    
    marker = data[index]

    if marker == ord("i"):
        return _decode_integer(data, index)
    
    if marker == ord("l"):
        return _decode_list(data, index)
    
    if marker == ord("d"):
        return _decode_dictionary(data, index)
    
    if ord("0") <= marker <= ord("9"):
        return _decode_bytes(data, index)
    
    raise BencodeDecodeError(f"Invalid marker at index {index}")

def decode(data: bytes):
    if not isinstance(data, bytes):
        raise TypeError("bencoded data must be bytes")
    
    value, next_index = _decode_at(data, 0)

    if next_index != len(data):
        raise BencodeDecodeError("trailing data")
    
    return value

def encode(value):
    if isinstance(value, bool):
        raise BencodeEncodeError("Booleans cannot be encoded")
    
    if isinstance(value, int):
        return b"i" + str(value).encode("ascii") + b"e"
    
    if isinstance(value, bytes):
        length = str(len(value)).encode("ascii")
        return length + b":" + value
    
    if isinstance(value, list):
        return b"l" + b"".join(encode(v) for v in value) + b"e"
    
    if isinstance(value, dict):
        res = b"d"
        for key in sorted(value):
            if not isinstance(key, bytes):
                raise BencodeEncodeError("dictionary keys must be bytes")
            res += encode(key) + encode(value[key])
        res += b"e"
        return res
    
    raise BencodeEncodeError(f"unsupported type: {type(value).__name__}")
         
