"""Codecs for Valve's KeyValues (VDF) formats.

Steam stores non-Steam shortcuts in a binary VDF file and account data in the
text variant. Both decode into :class:`KeyValues`, an ordered mapping that keeps
each value's binary type so files can be rewritten without losing information.
"""

from __future__ import annotations

import struct
from typing import Iterator, List, Optional, Tuple

MAP = 0x00
STRING = 0x01
INT32 = 0x02
FLOAT32 = 0x03
POINTER = 0x04
WSTRING = 0x05
COLOR = 0x06
UINT64 = 0x07
END = 0x08
INT64 = 0x0A
END_ALT = 0x0B

_FIXED = {
    INT32: struct.Struct("<i"),
    FLOAT32: struct.Struct("<f"),
    POINTER: struct.Struct("<I"),
    COLOR: struct.Struct("<I"),
    UINT64: struct.Struct("<Q"),
    INT64: struct.Struct("<q"),
}

_ENCODING = "utf-8"
_ERRORS = "surrogateescape"


class VdfError(ValueError):
    """Raised when VDF data cannot be decoded or encoded."""


class KeyValues:
    """Ordered, typed key/value mapping with case-insensitive key lookups."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: List[list] = []

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[str]:
        return (entry[0] for entry in self._entries)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._index(key) is not None

    def __repr__(self) -> str:
        return f"KeyValues({list(self.items())!r})"

    def _index(self, key: str) -> Optional[int]:
        folded = key.casefold()
        for index, entry in enumerate(self._entries):
            if entry[0].casefold() == folded:
                return index
        return None

    def get(self, key: str, default=None):
        index = self._index(key)
        return default if index is None else self._entries[index][2]

    def type_of(self, key: str) -> Optional[int]:
        index = self._index(key)
        return None if index is None else self._entries[index][1]

    def set(self, key: str, value, vtype: Optional[int] = None) -> None:
        """Assign ``value`` to ``key``, keeping the original key spelling and type if present."""
        index = self._index(key)
        if vtype is None:
            current = None if index is None else self._entries[index][1]
            vtype = current if current is not None and _accepts(current, value) else _infer_type(value)
        if index is None:
            self._entries.append([key, vtype, value])
        else:
            self._entries[index][1] = vtype
            self._entries[index][2] = value

    def remove(self, key: str) -> bool:
        index = self._index(key)
        if index is None:
            return False
        del self._entries[index]
        return True

    def items(self) -> Iterator[Tuple[str, object]]:
        return ((entry[0], entry[2]) for entry in self._entries)

    def typed_items(self) -> Iterator[Tuple[str, int, object]]:
        return ((entry[0], entry[1], entry[2]) for entry in self._entries)

    def values(self) -> Iterator[object]:
        return (entry[2] for entry in self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def to_dict(self) -> dict:
        """Return a plain nested ``dict`` copy, mainly for debugging and tests."""
        return {
            key: value.to_dict() if isinstance(value, KeyValues) else value
            for key, value in self.items()
        }


def _accepts(vtype: int, value) -> bool:
    if vtype == MAP:
        return isinstance(value, KeyValues)
    if vtype in (STRING, WSTRING):
        return isinstance(value, str)
    if vtype == FLOAT32:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return vtype in _FIXED and isinstance(value, int)


def _infer_type(value) -> int:
    if isinstance(value, KeyValues):
        return MAP
    if isinstance(value, str):
        return STRING
    if isinstance(value, bool):
        return INT32
    if isinstance(value, int):
        return INT32 if -(2 ** 31) <= value < 2 ** 31 else INT64
    if isinstance(value, float):
        return FLOAT32
    raise VdfError(f"cannot infer a VDF type for {type(value).__name__}")


class _Reader:
    __slots__ = ("data", "pos")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def byte(self) -> Optional[int]:
        if self.pos >= len(self.data):
            return None
        value = self.data[self.pos]
        self.pos += 1
        return value

    def cstring(self) -> str:
        end = self.data.find(b"\x00", self.pos)
        if end < 0:
            raise VdfError(f"unterminated string at offset {self.pos}")
        raw = self.data[self.pos:end]
        self.pos = end + 1
        return raw.decode(_ENCODING, _ERRORS)

    def wstring(self) -> str:
        end = self.pos
        while True:
            end = self.data.find(b"\x00\x00", end)
            if end < 0:
                raise VdfError(f"unterminated wide string at offset {self.pos}")
            if (end - self.pos) % 2 == 0:
                break
            end += 1
        raw = self.data[self.pos:end]
        self.pos = end + 2
        return raw.decode("utf-16-le", _ERRORS)

    def fixed(self, codec: struct.Struct):
        end = self.pos + codec.size
        if end > len(self.data):
            raise VdfError(f"truncated value at offset {self.pos}")
        (value,) = codec.unpack_from(self.data, self.pos)
        self.pos = end
        return value


def loads_binary(data: bytes) -> KeyValues:
    """Decode binary VDF ``data`` (for example ``shortcuts.vdf``)."""
    reader = _Reader(bytes(data))
    root = _read_map(reader, top_level=True)
    if reader.pos < len(reader.data) and reader.data[reader.pos:].strip(b"\x00\x08"):
        raise VdfError(f"unexpected trailing data at offset {reader.pos}")
    return root


def _read_map(reader: _Reader, top_level: bool = False) -> KeyValues:
    node = KeyValues()
    while True:
        vtype = reader.byte()
        if vtype is None:
            if top_level:
                return node
            raise VdfError("unexpected end of data inside a map")
        if vtype in (END, END_ALT):
            return node
        key = reader.cstring()
        if vtype == MAP:
            value = _read_map(reader)
        elif vtype == STRING:
            value = reader.cstring()
        elif vtype == WSTRING:
            value = reader.wstring()
        elif vtype in _FIXED:
            value = reader.fixed(_FIXED[vtype])
        else:
            raise VdfError(f"unknown value type 0x{vtype:02x} at offset {reader.pos - 1}")
        node._entries.append([key, vtype, value])


def dumps_binary(root: KeyValues) -> bytes:
    """Encode ``root`` as binary VDF, terminated the same way Steam does."""
    out = bytearray()
    _write_map(out, root)
    out.append(END)
    return bytes(out)


def _write_map(out: bytearray, node: KeyValues) -> None:
    for key, vtype, value in node.typed_items():
        out.append(vtype)
        out += key.encode(_ENCODING, _ERRORS) + b"\x00"
        if vtype == MAP:
            if not isinstance(value, KeyValues):
                raise VdfError(f"key {key!r} is typed as a map but holds {type(value).__name__}")
            _write_map(out, value)
            out.append(END)
        elif vtype == STRING:
            out += str(value).encode(_ENCODING, _ERRORS) + b"\x00"
        elif vtype == WSTRING:
            out += str(value).encode("utf-16-le", _ERRORS) + b"\x00\x00"
        elif vtype in _FIXED:
            try:
                out += _FIXED[vtype].pack(value)
            except struct.error as exc:
                raise VdfError(f"value for {key!r} does not fit its type: {exc}") from exc
        else:
            raise VdfError(f"cannot encode value type 0x{vtype:02x} for key {key!r}")


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}


def _tokenize(text: str) -> Iterator[Tuple[str, str]]:
    length = len(text)
    pos = 0
    while pos < length:
        char = text[pos]
        if char.isspace():
            pos += 1
        elif text.startswith("//", pos):
            newline = text.find("\n", pos)
            pos = length if newline < 0 else newline + 1
        elif char in "{}":
            yield char, char
            pos += 1
        elif char == '"':
            pos += 1
            chunks = []
            while True:
                if pos >= length:
                    raise VdfError("unterminated quoted string")
                char = text[pos]
                if char == "\\" and pos + 1 < length:
                    chunks.append(_ESCAPES.get(text[pos + 1], "\\" + text[pos + 1]))
                    pos += 2
                elif char == '"':
                    pos += 1
                    break
                else:
                    chunks.append(char)
                    pos += 1
            yield "str", "".join(chunks)
        else:
            start = pos
            while pos < length and not text[pos].isspace() and text[pos] not in '{}"':
                pos += 1
            token = text[start:pos]
            if token.startswith("[") and token.endswith("]"):
                yield "cond", token
            else:
                yield "str", token


def loads_text(text: str) -> KeyValues:
    """Decode text VDF such as ``loginusers.vdf``; every leaf is a string."""
    tokens = [token for token in _tokenize(text) if token[0] != "cond"]
    root = KeyValues()
    stack = [root]
    index = 0
    while index < len(tokens):
        kind, value = tokens[index]
        if kind == "}":
            if len(stack) == 1:
                raise VdfError("unbalanced closing brace")
            stack.pop()
            index += 1
            continue
        if kind != "str":
            raise VdfError(f"expected a key, found {value!r}")
        if index + 1 >= len(tokens):
            raise VdfError(f"key {value!r} has no value")
        next_kind, next_value = tokens[index + 1]
        if next_kind == "{":
            child = KeyValues()
            stack[-1].set(value, child, MAP)
            stack.append(child)
        elif next_kind == "str":
            stack[-1].set(value, next_value, STRING)
        else:
            raise VdfError(f"unexpected {next_value!r} after key {value!r}")
        index += 2
    if len(stack) != 1:
        raise VdfError("unbalanced opening brace")
    return root
