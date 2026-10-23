"""Field model: every preset parameter, its JSON path, and its value encoding.

Built from the embedded copy of ``spec/layout.json``.  The JSON
document format is *not* the spec's flat dotted names; this module owns the
mapping between the two (see ``docs/preset-format.md``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import _spec_data

BODY_START = 10  # message offset of the first preset-body byte
BODY_LEN = 171
NAME_LEN = 16


def norm(s: str) -> str:
	"""Normalise a user-typed enum name: case, spaces, '_' and '-' are not significant."""
	return re.sub(r"[\s_\-]+", " ", s.strip().lower())


@dataclass(frozen=True)
class Param:
	spec_name: str  # name in spec/layout.json, e.g. "pad1.type"
	path: tuple[str, ...]  # JSON path, e.g. ("pad1", "type")
	index: int  # index into the 171-byte body
	vw2_offset: int | None
	kind: str  # "enum" | "int" | "raw"
	values: tuple[str, ...] = ()
	bmin: int = 0
	bmax: int = 127
	offset: int = 0  # displayed value = byte + offset (kind "int")
	style: str = "name"  # enums: "bool" | "number" | "name"

	@property
	def key(self) -> str:
		return ".".join(self.path)

	# -- ranges as the user sees them -------------------------------------
	def user_range(self) -> tuple[int, int]:
		if self.kind == "enum" and self.style == "number":
			return 1, len(self.values)
		return self.bmin + self.offset, self.bmax + self.offset

	def valid(self, raw: int) -> bool:
		if self.kind == "enum":
			return 0 <= raw < len(self.values)
		if self.kind == "int":
			return self.bmin <= raw <= self.bmax
		return 0 <= raw <= 127

	# -- byte -> JSON -------------------------------------------------------
	def to_json(self, raw: int):
		if not self.valid(raw):
			return {"raw": raw}
		if self.kind == "enum":
			if self.style == "bool":
				return raw == 0
			if self.style == "number":
				return raw + 1
			return self.values[raw]
		return raw + self.offset

	# -- JSON -> byte -------------------------------------------------------
	def from_json(self, v) -> int:
		"""Return the byte for JSON value ``v`` or raise ValueError with a readable message."""
		if isinstance(v, dict):
			if (
				set(v) == {"raw"}
				and isinstance(v["raw"], int)
				and not isinstance(v["raw"], bool)
				and 0 <= v["raw"] <= 127
			):
				return v["raw"]
			raise ValueError('an object here must be {"raw": 0..127}')
		if self.kind == "enum":
			return self._enum_from_json(v)
		if self.kind == "raw":
			if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 127:
				return v
			raise ValueError("expected an integer 0..127")
		lo, hi = self.user_range()
		if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi:
			return v - self.offset
		raise ValueError(f"expected an integer {lo}..{hi}")

	def _enum_from_json(self, v) -> int:
		if isinstance(v, bool):
			if self.style == "bool":
				return 0 if v else 1
			raise ValueError(self._expected())
		if isinstance(v, int):
			if self.style == "number" and 1 <= v <= len(self.values):
				return v - 1
			raise ValueError(self._expected())
		if (
			isinstance(v, str) and self.style != "number"
		):  # channels, curves and banks are plain integers
			n = norm(v)
			for i, name in enumerate(self.values):
				if norm(name) == n:
					return i
			if self.style == "bool" and n in _BOOL_WORDS:
				return 0 if _BOOL_WORDS[n] else 1
		raise ValueError(self._expected())

	def _expected(self) -> str:
		if self.style == "bool":
			return "expected true or false"
		if self.style == "number":
			return f"expected an integer {1}..{len(self.values)}"
		return "expected one of: " + ", ".join(self.values)

	def describe_byte(self) -> str:
		"""How the JSON value maps to the raw byte on the wire (used by the generated field table)."""
		if self.kind == "enum":
			if self.style == "bool":
				return f"true = 0 ({self.values[0]}), false = 1 ({self.values[1]})"
			if self.style == "number":
				return "value - 1"
			return ", ".join(f"{i} = {v}" for i, v in enumerate(self.values))
		if self.kind == "raw" or self.offset == 0:
			return "same as value"
		return f"value {'+' if self.offset < 0 else '-'} {abs(self.offset)}"

	def describe_type(self) -> str:
		"""Short human description of the accepted values (used by docs and `fields`)."""
		if self.kind == "enum":
			if self.style == "bool":
				return "boolean"
			if self.style == "number":
				return f"integer {1}..{len(self.values)}"
			return " \\| ".join(self.values)
		lo, hi = self.user_range()
		return f"integer {lo}..{hi}"


_BOOL_WORDS = {
	"yes": True,
	"no": False,
	"on": True,
	"off": False,
	"true": True,
	"false": False,
}
_BOOL_PAIRS = {("Yes", "No"), ("On", "Off"), ("Split On", "Split Off")}


def _enum_style(values: tuple[str, ...]) -> str:
	if tuple(values) in _BOOL_PAIRS:
		return "bool"
	m = [re.fullmatch(r"(.+) (\d+)", v) for v in values]
	if (
		all(m)
		and len({x.group(1) for x in m}) == 1
		and [int(x.group(2)) for x in m] == list(range(1, len(values) + 1))
	):
		return "number"
	return "name"


def _json_path(spec_name: str) -> tuple[str, ...]:
	if spec_name == "split.mode":
		return ("split", "enabled")
	parts = spec_name.split(".")
	if parts[0] == "pc":
		parts[0] = "program_change"
	if spec_name.startswith("reserved_after_"):
		return ("reserved", spec_name[len("reserved_after_") :])
	return tuple(parts)


def _load():
	layout = json.loads(_spec_data.LAYOUT_JSON)
	params: list[Param] = []
	for f in layout["fields"]:
		role = f["role"]
		if role not in ("parameter", "reserved"):
			continue
		index = f["msg_offset"] - BODY_START
		if role == "reserved":
			params.append(
				Param(
					f["name"], _json_path(f["name"]), index, f.get("vw2_offset"), "raw"
				)
			)
			continue
		enc = f["encoding"]
		if enc["type"] == "enum":
			vals = tuple(enc["values"])
			params.append(
				Param(
					f["name"],
					_json_path(f["name"]),
					index,
					f.get("vw2_offset"),
					"enum",
					values=vals,
					bmax=len(vals) - 1,
					style=_enum_style(vals),
				)
			)
		else:
			params.append(
				Param(
					f["name"],
					_json_path(f["name"]),
					index,
					f.get("vw2_offset"),
					"int",
					bmin=enc["byte_min"],
					bmax=enc["byte_max"],
					offset=enc["display_offset"],
				)
			)
	return layout, params


LAYOUT, ALL_PARAMS = _load()

_PAD_VALUE = re.compile(r"^pad(\d)\.value([123])$")

# Every parameter that appears directly in the JSON format (pad value bytes are
# exposed only through the type-dependent names in PAD_KEYS).
PARAMS: list[Param] = [p for p in ALL_PARAMS if not _PAD_VALUE.match(p.spec_name)]
BY_PATH: dict[tuple[str, ...], Param] = {p.path: p for p in PARAMS}

# Body indexes of the three type-dependent value bytes of each pad: PAD_VALUE_INDEX[n] = (v1, v2, v3)
PAD_VALUE_INDEX: dict[int, tuple[int, int, int]] = {}
for _p in ALL_PARAMS:
	_m = _PAD_VALUE.match(_p.spec_name)
	if _m:
		PAD_VALUE_INDEX.setdefault(int(_m.group(1)), [None] * 3)[
			int(_m.group(2)) - 1
		] = _p.index
PAD_VALUE_INDEX = {n: tuple(v) for n, v in PAD_VALUE_INDEX.items()}

PAD_TYPES: tuple[str, ...] = BY_PATH[("pad1", "type")].values

_CURVE = BY_PATH[("split", "curve")]

# pad type -> ((json key, value-byte slot 0..2, is_curve), ...)
PAD_KEYS: dict[str, tuple[tuple[str, int, bool], ...]] = {
	"Note": (("note", 0, False), ("velocity", 1, False), ("curve", 2, True)),
	"CC Toggle": (("cc", 0, False), ("on_value", 1, False), ("off_value", 2, False)),
	"CC Momentary": (
		("cc", 0, False),
		("press_value", 1, False),
		("release_value", 2, False),
	),
	"Program Change": (
		("program", 0, False),
		("bank_lsb", 1, False),
		("bank_msb", 2, False),
	),
	"Panic": (),
}
assert set(PAD_KEYS) == set(PAD_TYPES)


def pad_param(pad: int, pad_type: str, key: str) -> Param | None:
	"""The synthetic Param for a type-dependent pad key, or None if ``key`` is not valid for ``pad_type``."""
	for k, slot, is_curve in PAD_KEYS[pad_type]:
		if k == key:
			idx = PAD_VALUE_INDEX[pad][slot]
			if is_curve:
				return Param(
					f"pad{pad}.value{slot + 1}",
					("pad%d" % pad, key),
					idx,
					None,
					"enum",
					values=_CURVE.values,
					bmax=len(_CURVE.values) - 1,
					style="number",
				)
			return Param(
				f"pad{pad}.value{slot + 1}", ("pad%d" % pad, key), idx, None, "int"
			)
	return None


def pad_param_keys(pad_type: str) -> list[str]:
	return [k for k, _, _ in PAD_KEYS[pad_type]]


# Order of top-level JSON groups, following the body layout.
TOP_ORDER: list[str] = []
for _p in PARAMS:
	if _p.path[0] not in TOP_ORDER:
		TOP_ORDER.append(_p.path[0])

PAD_COUNT = 8
FADER_COUNT = 8
SLOT_COUNT = 25
