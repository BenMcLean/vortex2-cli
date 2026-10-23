"""Spec section 9 conformance, run against vortexlib."""

import pytest

import vortexlib as vl
from vortexlib import codec
from vortexlib.fields import ALL_PARAMS


def hx(s):
	return bytes.fromhex(s)


def test_conversion(vectors):
	for v in vectors["vectors"]:
		sysex, vw2 = hx(v["sysex_hex"]), hx(v["vw2_hex"])
		cmd, slot, preset = codec.parse_message(sysex)
		assert codec.to_vw2(preset) == vw2, v["name"]
		assert codec.from_vw2(vw2) == preset, v["name"]
		assert codec.build_message(cmd, slot, preset) == sysex, v["name"]


def test_negative_vw2(vectors):
	for item in vectors["negative"]["vw2"]:
		with pytest.raises(codec.FormatError):
			codec.from_vw2(hx(item["hex"]))


def test_negative_sysex(vectors):
	for item in vectors["negative"]["sysex"]:
		with pytest.raises(codec.FormatError):
			codec.parse_message(hx(item["hex"]))


def test_decoding(field_vectors):
	"""Every field of every vector decodes to the value the spec lists."""
	by_name = {p.spec_name: p for p in ALL_PARAMS}
	for v in field_vectors["vectors"]:
		_, slot, preset = codec.parse_message(hx(v["sysex_hex"]))
		assert v["fields"]["slot"] == slot
		assert v["fields"]["name"] == preset.name
		checked = 0
		for key, shown in v["fields"].items():
			if key in ("slot", "name"):
				continue
			p = by_name[key]
			raw = preset.body[p.index]
			got = p.values[raw] if p.kind == "enum" else raw + p.offset
			assert got == shown, (v["name"], key)
			checked += 1
		assert checked >= 140


def test_factory_defaults(factory_slots):
	for key, h in factory_slots.items():
		if key == "25":
			continue
		slot = int(key)
		msg = b"\xf0" + hx(h) + b"\xf7"
		_, s, preset = codec.parse_message(msg)
		assert s == slot
		assert codec.from_vw2(codec.to_vw2(preset)) == preset
		assert preset == vl.factory(slot + 1)
		assert preset.problems() == []
