import pytest

import vortexlib as vl
from vortexlib import codec


def all_presets(vectors):
	return [
		codec.parse_message(bytes.fromhex(v["sysex_hex"]))[2]
		for v in vectors["vectors"]
	]


def has_panic(p):
	return any(p.pad_type(n) == "Panic" for n in range(1, 9))


def test_full_doc_reproduces_preset(vectors):
	"""A preset's full document applied onto any base gives the preset back.  The one exception is a Panic
	pad's three unused value bytes, which the JSON format cannot express and so inherits from the base."""
	for p in all_presets(vectors):
		doc = vl.preset_to_doc(p)
		assert vl.apply_doc(p, doc)[0] == p
		if not has_panic(p):
			assert vl.apply_doc(vl.factory(), doc)[0] == p


def test_minimal_doc_reconstructs(vectors):
	base = vl.factory(3)
	for p in all_presets(vectors):
		if has_panic(p):
			continue
		assert vl.apply_doc(base, vl.preset_to_doc(p, reference=base))[0] == p


def test_partial_keeps_everything_else():
	base = vl.factory(2)
	new, slot = vl.apply_doc(base, {"slot": 9, "volume": {"cc": 11}})
	assert slot == 9
	assert vl.diff_presets(base, new) == [("volume.cc", 7, 11)]


def test_friendly_values():
	new, _ = vl.apply_doc(
		vl.factory(),
		{
			"program_change": {"send_on_load": "no"},
			"upper": {"channel": 10, "transpose": -12},
			"wheel": {"direction": "REVERSE"},
			"split": {"enabled": True, "key": 36, "curve": 8},
			"pad2": {"color1": "led off", "channel": 16},
		},
	)
	doc = vl.preset_to_doc(new)
	assert doc["program_change"]["send_on_load"] is False
	assert doc["upper"] == {"transpose": -12, "midi_to_din": True, "channel": 10}
	assert doc["split"] == {"curve": 8, "enabled": True, "key": 36}
	assert doc["pad2"]["color1"] == "LED Off"


def test_pad_type_change_resets_values():
	base, _ = vl.apply_doc(
		vl.factory(),
		{"pad1": {"type": "Note", "note": 60, "velocity": 100, "curve": 3}},
	)
	new, _ = vl.apply_doc(base, {"pad1": {"type": "CC Toggle"}})
	d = vl.preset_to_doc(new)["pad1"]
	assert (d["cc"], d["on_value"], d["off_value"]) == (0, 0, 0)
	# restating the same type does not reset; values given with a new type win
	same, _ = vl.apply_doc(base, {"pad1": {"type": "Note", "channel": 4}})
	assert vl.preset_to_doc(same)["pad1"]["note"] == 60
	pc, _ = vl.apply_doc(base, {"pad1": {"type": "Program Change", "program": 5}})
	assert vl.preset_to_doc(pc)["pad1"]["program"] == 5


def test_pad_key_must_match_type():
	with pytest.raises(vl.DocError) as e:
		vl.apply_doc(vl.factory(), {"pad1": {"note": 5, "cc": 3}})
	msg = "\n".join(e.value.errors)
	assert "pad1.cc" in msg and "CC Toggle" in msg
	with pytest.raises(vl.DocError, match="value1"):
		vl.apply_doc(vl.factory(), {"pad1": {"value1": 3}})


def test_all_errors_reported_with_paths_and_hints():
	with pytest.raises(vl.DocError) as e:
		vl.apply_doc(
			vl.factory(),
			{
				"slot": 26,
				"nmae": "x",
				"volume": {"ccc": 1, "max": 200},
				"upper": {"channel": 17},
				"name": "seventeen chars!!",
			},
		)
	errs = e.value.errors
	assert len(errs) == 6
	assert any("did you mean 'name'" in x for x in errs)
	assert any(x.startswith("volume.max") for x in errs)


def test_base_not_modified():
	base = vl.factory()
	before = bytes(base.body)
	vl.apply_doc(base, {"name": "X"})
	assert bytes(base.body) == before


def test_type_strictness():
	for bad in (
		{"volume": {"cc": True}},
		{"volume": {"cc": 1.5}},
		{"volume": {"cc": "7"}},
		{"wheel": {"direction": True}},
		{"upper": {"channel": 0}},
		{"slot": True},
		[],
		"x",
	):
		with pytest.raises(vl.DocError):
			vl.apply_doc(vl.factory(), bad)


def test_raw_escape_roundtrip_and_validation():
	new, _ = vl.apply_doc(vl.factory(), {"upper": {"channel": {"raw": 127}}})
	assert new.problems()
	assert vl.preset_to_doc(new)["upper"]["channel"] == {"raw": 127}


def test_json_syntax_error():
	with pytest.raises(vl.DocError, match="line 1"):
		vl.load(b"{ nope")


def test_name_rules():
	p = vl.factory()
	p.name = "A" * 16
	assert p.name == "A" * 16 and not p.problems()
	with pytest.raises(ValueError):
		p.name = "A" * 17


def test_channels_are_integers_only():
	assert vl.apply_doc(vl.factory(), {"upper": {"channel": 16}})[0].body[25] == 15
	for bad in ("Channel 10", "10", 0, 17, True):
		with pytest.raises(vl.DocError):
			vl.apply_doc(vl.factory(), {"upper": {"channel": bad}})
