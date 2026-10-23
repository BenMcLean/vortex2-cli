"""Binary formats: SysEx messages (spec sections 3, 9) and ``.vw2`` files (section 7)."""

from __future__ import annotations

from . import _spec_data
from . import fields as F
from .preset import Preset

CMD_SET, CMD_GET, CMD_REPLY = 0x01, 0x02, 0x03
HEADER = bytes([0xF0, 0x00, 0x00, 0x0E, 0x52, 0x5E])
MSG_LEN = 182
VW2_SIZE = 1071
MAX_SLOT = 24  # zero-based wire index


class FormatError(ValueError):
	"""A binary input is not a valid message / file."""


# -- SysEx ------------------------------------------------------------------


def build_get(slot: int) -> bytes:
	"""Get message for zero-based wire index ``slot``."""
	return HEADER + bytes([CMD_GET, 0x00, 0x01, slot, 0xF7])


def build_message(cmd: int, slot: int, preset: Preset) -> bytes:
	"""A Set (or Reply) message.  ``slot`` is the zero-based wire index, 0..24."""
	if not 0 <= slot <= MAX_SLOT:
		raise FormatError(f"slot index {slot} outside 0..{MAX_SLOT}")
	return HEADER + bytes([cmd, 0x01, 0x2C, slot]) + bytes(preset.body) + b"\xf7"


def parse_message(data: bytes) -> tuple[int, int, Preset]:
	"""Strict reader for a Set or Reply: returns (command, zero-based slot, preset). Spec 9, item 2."""
	if len(data) != MSG_LEN:
		raise FormatError(f"SysEx message is {len(data)} bytes, expected {MSG_LEN}")
	if data[:6] != HEADER:
		raise FormatError(
			"not an Alesis Vortex Wireless 2 message (manufacturer/device/model bytes differ)"
		)
	if data[-1] != 0xF7:
		raise FormatError("message does not end with F7")
	if data[6] not in (CMD_SET, CMD_REPLY):
		raise FormatError(f"command byte {data[6]:#04x} is not Set (01) or Reply (03)")
	if (data[7] << 7 | data[8]) != 172:
		raise FormatError("length field is not 172")
	if data[9] > MAX_SLOT:
		raise FormatError(f"slot byte {data[9]} is outside 0..{MAX_SLOT}")
	if any(b > 0x7F for b in data[1:-1]):
		raise FormatError("message contains a data byte with the high bit set")
	return data[6], data[9], Preset(data[10:181])


def split_sysex(data: bytes) -> list[bytes]:
	"""Split a ``.syx`` file into its F0..F7 messages (bytes outside messages are an error)."""
	msgs, i = [], 0
	while i < len(data):
		if data[i] != 0xF0:
			raise FormatError(
				f"unexpected byte {data[i]:#04x} at offset {i} outside a SysEx message"
			)
		j = data.find(b"\xf7", i)
		if j < 0:
			raise FormatError("SysEx message is not terminated by F7")
		msgs.append(data[i : j + 1])
		i = j + 1
	return msgs


# -- .vw2 ---------------------------------------------------------------------


def _template() -> bytes:
	t = bytes.fromhex(_spec_data.VW2_TEMPLATE_HEX)
	if len(t) != VW2_SIZE:
		raise RuntimeError("packaged vw2 template has the wrong size")
	return t


TEMPLATE = _template()
_VALUE_MAP = [
	(f["msg_offset"] - F.BODY_START, f["vw2_offset"])
	for f in F.LAYOUT["fields"]
	if f.get("vw2_offset") is not None and f["role"] != "slot"
]
_VALUE_POSITIONS = {off for _, off in _VALUE_MAP}
assert len(_VALUE_MAP) == F.BODY_LEN


def to_vw2(preset: Preset) -> bytes:
	out = bytearray(TEMPLATE)
	for body_i, off in _VALUE_MAP:
		out[off] = preset.body[body_i]
	return bytes(out)


def from_vw2(data: bytes) -> Preset:
	"""Strict reader: exactly 1071 bytes whose constant part equals the template (spec 7.1)."""
	if len(data) != VW2_SIZE:
		raise FormatError(f".vw2 file is {len(data)} bytes, expected {VW2_SIZE}")
	for i, (a, b) in enumerate(zip(data, TEMPLATE)):
		if i not in _VALUE_POSITIONS and a != b:
			raise FormatError(
				f".vw2 file differs from the expected structure at offset {i}"
			)
	return Preset(bytes(data[off] for _, off in sorted(_VALUE_MAP)))
