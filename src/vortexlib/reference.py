"""Generated reference material: the JSON Schema and the field table.

Both are derived from the same field model the converter uses, so they cannot drift from it.
Short descriptions are restated in our own words from spec section 4.4 (non-normative).
"""

from __future__ import annotations

import re

from . import fields as F
from .document import PAD_FIXED, TOP_KEYS, _is_pad
from .preset import factory

GROUP_DESC = {
	"program_change": "Program Change (+ Bank Select) message sent when the preset is loaded on the keytar.",
	"split": "Splits the keybed into a lower and an upper zone.",
	"upper": "Upper keyboard zone.",
	"lower": "Lower keyboard zone.",
	"sustain": "Sustain pedal input.",
	"wheel": "Pitch wheel.",
	"volume": "Volume slider (S1).",
	"ribbon": "Touch ribbon, with three selectable banks.",
	"tilt": "Tilt (accelerometer) control.",
	"fader": "Fader (1..8).",
	"pad": "Pad (1..8).",
	"reserved": "Bytes the vendor editor never shows. Preserved when reading from the keytar; omit unless you know why.",
}

LEAF_DESC = {
	"program_change.send_on_load": "Send Program Change and Bank Select when this preset is loaded.",
	"program_change.msb": "Bank Select MSB.",
	"program_change.lsb": "Bank Select LSB.",
	"program_change.program": "Program number.",
	"split.enabled": "true: keybed is divided at the split key; false: single zone.",
	"split.key": "Number of keys, counting from the lowest, that belong to the lower zone.",
	"split.curve": "Velocity curve applied to the keybed.",
	"upper.transpose": "Semitones; 12 is one octave.",
	"lower.transpose": "Semitones; 12 is one octave.",
	"upper.midi_to_din": "true: this zone's messages also go out of the DIN MIDI output; false: USB only.",
	"lower.midi_to_din": "true: this zone's messages also go out of the DIN MIDI output; false: USB only.",
	"upper.channel": "MIDI channel.",
	"lower.channel": "MIDI channel.",
	"sustain.channel": "MIDI channel.",
	"wheel.channel": "MIDI channel.",
	"wheel.direction": "Normal: turning right raises pitch; Reverse: it lowers it.",
	"volume.cc": "Controller number sent.",
	"volume.min": "Lowest value sent.",
	"volume.max": "Highest value sent.",
	"volume.channel": "MIDI channel.",
	"ribbon.default_bank": "Bank active when the preset loads.",
	"ribbon.release_mode": "Latch: nothing is sent when the finger lifts; Return: the controller's default is sent.",
	"ribbon.bank.type": "Send a controller (CC) or pitch bend.",
	"ribbon.bank.cc": "Controller number (used when type is CC).",
	"ribbon.bank.min": "Lowest value sent.",
	"ribbon.bank.max": "Highest value sent.",
	"ribbon.bank.channel": "MIDI channel.",
	"tilt.type": "Send a controller (CC) or pitch bend.",
	"tilt.cc": "Controller number (used when type is CC).",
	"tilt.min": "Lowest value sent.",
	"tilt.max": "Highest value sent.",
	"tilt.channel": "MIDI channel.",
	"fader.cc": "Controller number sent.",
	"fader.min": "Lowest value sent.",
	"fader.max": "Highest value sent.",
	"fader.channel": "MIDI channel.",
	"pad.type": "What the pad does. Determines which of the value keys below apply.",
	"pad.channel": "MIDI channel the pad sends on.",
	"pad.color1": "LED colour. Note pads: idle. Other types: idle/released.",
	"pad.color2": "LED colour. Note pads: struck with velocity 1-63. Other types: on/pressed.",
	"pad.color3": "LED colour (Note pads only): struck with velocity 64-95.",
	"pad.color4": "LED colour (Note pads only): struck with velocity 96-127.",
	"pad.note": "Note pads: note number.",
	"pad.velocity": "Note pads: fixed velocity; 0 means use the velocity curve.",
	"pad.curve": "Note pads: velocity curve.",
	"pad.cc": "CC Toggle / CC Momentary pads: controller number.",
	"pad.on_value": "CC Toggle pads: value sent when switched on.",
	"pad.off_value": "CC Toggle pads: value sent when switched off.",
	"pad.press_value": "CC Momentary pads: value sent on press.",
	"pad.release_value": "CC Momentary pads: value sent on release.",
	"pad.program": "Program Change pads: program number.",
	"pad.bank_lsb": "Program Change pads: bank LSB.",
	"pad.bank_msb": "Program Change pads: bank MSB.",
}

_PAD_KEYS_ALL = [
	"note",
	"velocity",
	"curve",
	"cc",
	"on_value",
	"off_value",
	"press_value",
	"release_value",
	"program",
	"bank_lsb",
	"bank_msb",
]


def generic(path: str) -> str:
	"""fader3.cc -> fader.cc ; ribbon.bank2.max -> ribbon.bank.max ; pad7.color1 -> pad.color1"""
	return re.sub(r"\b(pad|fader|bank)\d+", r"\1", path)


def describe(path: str) -> str:
	g = generic(path)
	if g.startswith("reserved."):
		return GROUP_DESC["reserved"]
	return LEAF_DESC.get(g, GROUP_DESC.get(g, ""))


# -- JSON Schema ---------------------------------------------------------------------------

_RAW = {"$ref": "#/$defs/raw"}


def _param_schema(p: F.Param, desc: str | None = None) -> dict:
	if p.kind == "enum":
		if p.style == "bool":
			s = {"type": "boolean"}
			alts = [s, _RAW]
		elif p.style == "number":
			alts = [{"type": "integer", "minimum": 1, "maximum": len(p.values)}, _RAW]
		else:
			alts = [{"enum": list(p.values)}, _RAW]
	else:
		lo, hi = p.user_range()
		alts = [{"type": "integer", "minimum": lo, "maximum": hi}, _RAW]
	out: dict = {"anyOf": alts}
	d = desc if desc is not None else describe(p.key)
	if d:
		out["description"] = d
	return out


def _pad_schema(n: int) -> dict:
	props: dict = {}
	for k in PAD_FIXED:
		props[k] = _param_schema(F.BY_PATH[(f"pad{n}", k)])
	for k in _PAD_KEYS_ALL:
		for t in F.PAD_TYPES:
			sp = F.pad_param(n, t, k)
			if sp is not None:
				props[k] = _param_schema(sp, LEAF_DESC.get(f"pad.{k}"))
				break
	allof = []
	for t in F.PAD_TYPES:
		valid = set(F.pad_param_keys(t))
		allof.append(
			{
				"if": {"properties": {"type": {"const": t}}, "required": ["type"]},
				"then": {
					"properties": {k: False for k in _PAD_KEYS_ALL if k not in valid}
				},
			}
		)
	return {
		"type": "object",
		"description": GROUP_DESC["pad"],
		"properties": props,
		"additionalProperties": False,
		"allOf": allof,
	}


def json_schema() -> dict:
	"""JSON Schema (draft 2020-12) for preset documents.

	The schema checks canonical spellings; the tool additionally ignores case, spaces, '_' and '-' in names.
	"""
	props: dict = {
		"$schema": {"type": "string"},
		"description": {
			"type": "string",
			"description": "Free text; ignored by the tool.",
		},
		"slot": {
			"type": "integer",
			"minimum": 1,
			"maximum": F.SLOT_COUNT,
			"description": "Target slot 1..25. Optional; the command line can override it.",
		},
		"name": {
			"type": "string",
			"maxLength": F.NAME_LEN,
			"pattern": "^[\\u0020-\\u007e]*$",
			"description": "Preset name, up to 16 printable ASCII characters.",
		},
	}
	groups: dict[str, dict] = {}
	for p in F.PARAMS:
		top = p.path[0]
		if _is_pad(top):
			continue
		node = groups.setdefault(
			top, {"type": "object", "properties": {}, "additionalProperties": False}
		)
		for k in p.path[1:-1]:
			node = node["properties"].setdefault(
				k, {"type": "object", "properties": {}, "additionalProperties": False}
			)
		node["properties"][p.path[-1]] = _param_schema(p)
	for top, g in groups.items():
		d = GROUP_DESC.get(generic(top))
		if d:
			g["description"] = d
	for top in F.TOP_ORDER:
		props[top] = _pad_schema(int(top[3:])) if _is_pad(top) else groups[top]
	assert set(props) == set(TOP_KEYS)
	return {
		"$schema": "https://json-schema.org/draft/2020-12/schema",
		"title": "Alesis Vortex Wireless 2 preset",
		"description": "A (possibly partial) preset. Omitted fields keep their value in the base preset.",
		"type": "object",
		"properties": props,
		"additionalProperties": False,
		"$defs": {
			"raw": {
				"type": "object",
				"properties": {
					"raw": {"type": "integer", "minimum": 0, "maximum": 127}
				},
				"required": ["raw"],
				"additionalProperties": False,
				"description": "Escape hatch for a byte outside the valid range; tools refuse to write it unless forced.",
			}
		},
	}


# -- field table --------------------------------------------------------------------------------


def field_rows() -> list[tuple[str, str, str, str, str]]:
	"""(key, accepted values, factory default, byte encoding, description) for every key; indexed groups appear once as
	faderN / padN / ribbon.bankN with the default of the first instance."""
	base = factory()
	seen: set[str] = set()
	rows = [
		(
			"slot",
			f"integer 1..{F.SLOT_COUNT}",
			"",
			"wire slot index = value - 1 (0..24)",
			"Target slot. Optional; the command line overrides it.",
		),
		(
			"name",
			f"string, up to {F.NAME_LEN} printable ASCII characters",
			"(empty)",
			"ASCII, padded with 00 to 16 bytes",
			"Preset name.",
		),
	]
	for p in F.PARAMS:
		if _is_pad(p.path[0]) and p.path[0] != "pad1":
			continue
		g = generic(p.key)
		if g in seen or (p.path[0].startswith("fader") and p.path[0] != "fader1"):
			continue
		if len(p.path) == 3 and p.path[1] in ("bank2", "bank3"):
			continue
		seen.add(g)
		key = re.sub(r"^(pad|fader)1\b", r"\1N", p.key).replace("bank1", "bankN")
		default = p.to_json(base.body[p.index])
		rows.append(
			(key, p.describe_type(), _fmt(default), p.describe_byte(), describe(p.key))
		)
		if g == "pad.type":
			for k in _PAD_KEYS_ALL:
				for t in F.PAD_TYPES:
					sp = F.pad_param(1, t, k)
					if sp is not None:
						rows.append(
							(
								f"padN.{k}",
								sp.describe_type(),
								"",
								sp.describe_byte(),
								LEAF_DESC[f"pad.{k}"],
							)
						)
						break
	return rows


def _fmt(v) -> str:
	if isinstance(v, bool):
		return "true" if v else "false"
	return str(v) if v != "" else "(empty)"
