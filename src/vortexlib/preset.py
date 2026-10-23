"""The in-memory preset: the 171-byte body of spec section 1, plus factory defaults."""

from __future__ import annotations

from . import _spec_data
from . import fields as F


class Preset:
	"""A preset body.  The bytes are authoritative; everything else is a view of them."""

	__slots__ = ("body",)

	def __init__(self, body: bytes | bytearray | None = None):
		if body is None:
			body = bytes(F.BODY_LEN)
		if len(body) != F.BODY_LEN:
			raise ValueError(f"preset body must be {F.BODY_LEN} bytes, got {len(body)}")
		self.body = bytearray(body)

	def copy(self) -> "Preset":
		return Preset(self.body)

	def __eq__(self, other) -> bool:
		return isinstance(other, Preset) and self.body == other.body

	def __hash__(self):
		return hash(bytes(self.body))

	# -- name ---------------------------------------------------------------
	@property
	def name(self) -> str:
		raw = bytes(self.body[: F.NAME_LEN])
		end = raw.find(0)
		return "".join(chr(b) for b in (raw if end < 0 else raw[:end]))

	@name.setter
	def name(self, value: str) -> None:
		enc = value.encode("ascii")
		if len(enc) > F.NAME_LEN:
			raise ValueError(f"name is longer than {F.NAME_LEN} characters")
		self.body[: F.NAME_LEN] = enc.ljust(F.NAME_LEN, b"\0")

	# -- validity (spec 4.2, 4.3) ---------------------------------------------
	def problems(self) -> list[str]:
		"""Everything that makes this preset unsafe to write (the device validates nothing)."""
		out: list[str] = []
		if any(b > 0x7F for b in self.body):
			out.append("body contains a byte with the high bit set")
		raw = bytes(self.body[: F.NAME_LEN])
		end = raw.find(0)
		used = raw if end < 0 else raw[:end]
		if any(not 0x20 <= b <= 0x7E for b in used):
			out.append("name contains non-printable or non-ASCII bytes")
		if end >= 0 and any(raw[end:]):
			out.append("name has data after its first NUL byte")
		for p in F.PARAMS:
			if p.kind != "raw" and not p.valid(self.body[p.index]):
				out.append(
					f"{p.key}: byte {self.body[p.index]:#04x} is outside the valid range"
				)
		return out

	def pad_type(self, pad: int) -> str | None:
		p = F.BY_PATH[(f"pad{pad}", "type")]
		raw = self.body[p.index]
		return p.values[raw] if p.valid(raw) else None


def factory(slot: int | None = None) -> Preset:
	"""Alesis's factory defaults (spec 5.2).

	The factory Program Change number equals the slot index, so when ``slot``
	(1..25) is known it is applied; otherwise the program number is 0.
	"""
	msg = bytes.fromhex(
		_spec_data.FACTORY_SLOT0_HEX
	)  # without F0 / F7: 00 00 0E 52 5E 03 01 2C <slot> <body>
	p = Preset(msg[9 : 9 + F.BODY_LEN])
	prog = F.BY_PATH[("program_change", "program")]
	p.body[prog.index] = 0 if slot is None else slot - 1
	return p
