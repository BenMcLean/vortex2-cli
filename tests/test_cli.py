import itertools
import json
import re

import pytest
from conftest import ROOT

import vortexlib as vl
from vortex_cli.cli import main

SIM = [
	"--settle",
	"0.55",
]  # the simulated keytar drops Gets for 0.5 s after a write, like the real one


def run(capsys, *argv):
	code = main([str(a) for a in argv])
	out = capsys.readouterr()
	return code, out.out, out.err


@pytest.fixture
def doc(tmp_path):
	f = tmp_path / "p.json"
	f.write_text(json.dumps({"name": "Lead", "fader3": {"cc": 74}}))
	return f


def test_json_to_files_uses_factory_defaults(tmp_path, doc, capsys):
	assert run(capsys, "convert", doc, tmp_path / "o.vw2", "--slot", 4)[0] == 0
	p = vl.load((tmp_path / "o.vw2").read_bytes()).preset
	assert p == vl.apply_doc(vl.factory(4), json.loads(doc.read_text()))[0]


def test_slot_rules(tmp_path, doc, capsys):
	code, _, err = run(capsys, "convert", doc, tmp_path / "o.syx")
	assert code == 2 and "slot" in err
	assert run(capsys, "convert", doc, tmp_path / "o.syx", "-s", 3)[0] == 0
	assert vl.load((tmp_path / "o.syx").read_bytes()).slot == 3
	d2 = tmp_path / "s.json"
	d2.write_text(json.dumps({"slot": 8, "name": "S"}))
	run(capsys, "convert", d2, tmp_path / "a.syx")  # the file's slot is used...
	run(
		capsys, "convert", d2, tmp_path / "b.syx", "--slot", 2
	)  # ...unless the command line overrides it
	assert vl.load((tmp_path / "a.syx").read_bytes()).slot == 8
	assert vl.load((tmp_path / "b.syx").read_bytes()).slot == 2


def test_argument_order_does_not_matter(tmp_path, doc, capsys):
	"""Every permutation of the tokens (options may precede the command and split the positionals)."""
	units = [["--slot", "4"], ["--force"], ["--minimal"], ["--to", "json"]]
	expected = None
	for perm in itertools.permutations(units):
		for pos in ("before", "mid", "after"):
			out = tmp_path / "o.out"
			opts = [t for u in perm for t in u]
			if pos == "before":
				argv = [*opts, "convert", str(doc), str(out)]
			elif pos == "mid":
				argv = ["convert", str(doc), *opts, str(out)]
			else:
				argv = ["convert", str(doc), str(out), *opts]
			assert main(argv) == 0, argv
			capsys.readouterr()
			data = out.read_bytes()
			expected = expected or data
			assert data == expected
	assert json.loads(expected)["slot"] == 4


def test_no_overwrite_without_force(tmp_path, doc, capsys):
	out = tmp_path / "o.vw2"
	assert run(capsys, "convert", doc, out)[0] == 0
	assert run(capsys, "convert", doc, out)[0] == 2
	assert run(capsys, "convert", doc, out, "--force")[0] == 0


def test_validate_reports_all_errors(tmp_path, capsys):
	bad = tmp_path / "bad.json"
	bad.write_text('{"volume": {"cc": 999}, "padd1": {}}')
	code, out, _ = run(capsys, "validate", bad)
	assert code == 1 and "volume.cc" in out and "padd1" in out


def test_device_merge_dry_run_and_write(tmp_path, doc, capsys):
	port = ["--port", f"sim:{tmp_path / 'kt.json'}"]
	pre = tmp_path / "pre.json"
	pre.write_text(
		json.dumps({"volume": {"cc": 11}, "wheel": {"direction": "Reverse"}})
	)
	assert run(capsys, "convert", pre, "device", "-s", 4, "-y", *port, *SIM)[0] == 0
	code, out, _ = run(
		capsys, "convert", doc, "device", "-s", 4, "--dry-run", *port, *SIM
	)
	assert code == 0 and "dry run" in out and "name" in out and "volume" not in out
	code, out, _ = run(capsys, "convert", doc, "device", "-s", 4, "-y", *port, *SIM)
	assert code == 0 and "verified" in out
	assert not list(tmp_path.glob("**/slot-04.syx"))  # no automatic backups
	# unmentioned fields kept what the keytar held; mentioned ones changed
	code, out, _ = run(capsys, "convert", "device", "-", "-s", 4, *port, *SIM)
	d = json.loads(out)
	assert (
		d["name"] == "Lead"
		and d["volume"]["cc"] == 11
		and d["wheel"]["direction"] == "Reverse"
	)
	assert d["fader3"]["cc"] == 74
	assert (
		"nothing to write"
		in run(capsys, "convert", doc, "device", "-s", 4, "-y", *port, *SIM)[1]
	)


def test_device_needs_slot_and_confirmation(doc, capsys):
	port = ["--port", "sim", *SIM]
	assert run(capsys, "convert", doc, "device", *port)[0] == 2
	code, _, err = run(
		capsys, "convert", doc, "device", "-s", 1, *port
	)  # stdin is not a TTY under pytest
	assert code == 2 and "--yes" in err


def test_slot_out_of_range_is_a_usage_error(doc, capsys):
	for slot in (0, 26):
		code, _, err = run(capsys, "convert", doc, "device", "-s", slot, "--port", "sim")
		assert code == 2 and "1..25" in err


def read_slot(capsys, port, n):
	return json.loads(run(capsys, "convert", "device", "-", "-s", n, *port, *SIM)[1])


def test_reset_pushes_factory_defaults(tmp_path, doc, capsys):
	port = ["--port", f"sim:{tmp_path / 'kt.json'}"]
	assert run(capsys, "convert", doc, "device", "-s", 4, "-y", *port, *SIM)[0] == 0
	assert read_slot(capsys, port, 4)["name"] == "Lead"
	assert run(capsys, "reset", 4, "--dry-run", *port, *SIM)[0] == 0
	assert read_slot(capsys, port, 4)["name"] == "Lead"
	code, out, _ = run(capsys, "reset", 4, "-y", *port, *SIM)
	assert code == 0 and "verified" in out
	assert vl.apply_doc(vl.factory(4), read_slot(capsys, port, 4))[0] == vl.factory(4)
	assert not list(tmp_path.glob("vortex-backups"))


def test_reset_argument_rules(capsys):
	assert run(capsys, "reset", "--port", "sim")[0] == 2  # nothing named
	assert run(capsys, "reset", 3, "--all", "--port", "sim")[0] == 2
	assert run(capsys, "reset", 26, "-y", "--port", "sim")[0] == 2
	assert run(capsys, "reset", 3, "--port", "sim")[0] == 2  # no TTY: needs --yes


def test_complete_input_is_written_without_reading(tmp_path, capsys):
	"""A complete preset replaces the slot; the keytar is not read first (only the verifying read-back)."""
	sent = []

	class Recorder(vl.SimKeytar):
		def send(self, data):
			sent.append(data[6])  # command byte: 0 = Get, 1 = Set
			super().send(data)

	import contextlib

	import vortex_cli.cli as cli

	real = cli.open_device
	cli.open_device = lambda args: contextlib.nullcontext(
		vl.Keytar(Recorder(), vl.Timing(settle=0.55))
	)
	full = tmp_path / "full.json"
	full.write_bytes(vl.dump(vl.factory(5), "json", 5))
	try:
		code, out, _ = run(capsys, "convert", full, "device", "-y")
	finally:
		cli.open_device = real
	assert code == 0 and "replacing the whole preset" in out
	assert sent[0] == 1  # the first message is the Set, not a Get


def test_complete_json_detection():
	full = vl.preset_to_doc(vl.factory(3), slot=3)
	assert vl.is_complete_doc(full)
	assert not vl.is_complete_doc({"name": "x"})
	assert not vl.is_complete_doc({k: v for k, v in full.items() if k != "volume"})


def test_backup_and_restore(tmp_path, capsys):
	port = ["--port", f"sim:{tmp_path / 'kt.json'}", *SIM]
	assert run(capsys, "backup", tmp_path / "b", *port)[0] == 0
	assert len(list((tmp_path / "b").glob("slot-*.syx"))) == 25
	assert (
		run(capsys, "convert", tmp_path / "b" / "slot-07.syx", "device", "-y", *port)[0]
		== 0
	)


def test_indentation_is_tabs():
	"""JSON, TOML and Markdown are indented with tabs (Python is covered by ruff format; YAML cannot be)."""
	import importlib.util

	spec = importlib.util.spec_from_file_location(
		"check_tabs", ROOT / "tools" / "check_tabs.py"
	)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	assert mod.main([]) == 0


def test_generated_files_are_current():
	import importlib.util

	spec = importlib.util.spec_from_file_location(
		"gen_docs", ROOT / "tools" / "gen_docs.py"
	)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	assert (ROOT / "schema" / "preset.schema.json").read_text(
		encoding="utf-8"
	) == mod.schema_text()
	assert (ROOT / "docs" / "fields.md").read_text(
		encoding="utf-8"
	) == mod.fields_text()


def test_embedded_spec_data_matches_spec_folder():
	from vortexlib import _spec_data

	spec = ROOT / "spec"
	assert json.loads(_spec_data.LAYOUT_JSON) == json.loads(
		(spec / "layout.json").read_text(encoding="utf-8")
	)
	assert bytes.fromhex(_spec_data.VW2_TEMPLATE_HEX) == bytes.fromhex(
		(spec / "vw2_template.hex").read_text()
	)
	d = json.loads((spec / "device_factory_defaults.json").read_text(encoding="utf-8"))
	assert bytes.fromhex(_spec_data.FACTORY_SLOT0_HEX) == bytes.fromhex(d["slots"]["0"])


def test_library_is_file_free():
	"""vortexlib must stay usable without a file system or OS: no such imports or calls."""
	for f in (ROOT / "src" / "vortexlib").glob("*.py"):
		text = f.read_text(encoding="utf-8")
		assert not re.search(
			r"^\s*(import|from)\s+(os|pathlib|sys|shutil|io|importlib\.resources)\b",
			text,
			re.M,
		), f
		assert not re.search(
			r"\bopen\(|read_text|write_text|read_bytes|write_bytes", text
		), f


def test_schema_validates_documents(vectors):
	jsonschema = pytest.importorskip("jsonschema")
	schema = vl.json_schema()
	jsonschema.Draft202012Validator.check_schema(schema)
	v = jsonschema.Draft202012Validator(schema)
	from vortexlib import codec

	for item in vectors["vectors"]:
		p = codec.parse_message(bytes.fromhex(item["sysex_hex"]))[2]
		assert not list(v.iter_errors(vl.preset_to_doc(p, slot=3))), item["name"]
	for bad in (
		{"nmae": "x"},
		{"slot": 0},
		{"pad1": {"type": "Panic", "note": 3}},
		{"upper": {"channel": 17}},
		{"volume": {"cc": 128}},
		{"pad1": {"value1": 3}},
	):
		assert list(v.iter_errors(bad)), bad
	assert not list(
		v.iter_errors(
			{
				"pad1": {"type": "Note", "note": 3},
				"ribbon": {"bank2": {"type": "Pitch Bend"}},
			}
		)
	)


def test_examples_are_valid(capsys):
	files = sorted((ROOT / "examples").glob("*.json"))
	assert files
	assert run(capsys, "validate", *files)[0] == 0
	jsonschema = pytest.importorskip("jsonschema")
	v = jsonschema.Draft202012Validator(vl.json_schema())
	for f in files:
		assert not list(v.iter_errors(json.loads(f.read_text()))), f


# -- pairing (spec 8.2): example messages laid out as the spec describes -------------------------

PAIR_EXAMPLES = {
	"123456": "f0 00 20 2b 68 3c 00 31 32 33 34 35 36 30 30 30 30 30 30 30 30 30 30 30 30 30 f7",
	"654321": "f0 00 20 2b 68 3c 00 36 35 34 33 32 31 30 30 30 30 30 30 30 30 30 30 30 30 30 f7",
}


def test_build_pair_matches_the_spec_layout():
	from vortexlib import codec

	for dongle_id, hexstr in PAIR_EXAMPLES.items():
		assert codec.build_pair(dongle_id) == bytes.fromhex(hexstr)


@pytest.mark.parametrize("bad", ["", "24681", "24681a", "24 681", "٢٤٦٨١٠", "٢٤٦٨١٠١٢٣٤٥٦"])
def test_build_pair_rejects_bad_ids(bad):
	from vortexlib import codec

	with pytest.raises(ValueError):
		codec.build_pair(bad)


def test_pair_uses_the_rightmost_six_digits(capsys):
	from vortexlib import codec

	for typed in ("123456", "0123456", "99123456", "5551234567890123456"):
		assert codec.build_pair(typed) == codec.build_pair(typed[-6:])
	assert codec.build_pair("99123456") == bytes.fromhex(PAIR_EXAMPLES["123456"])
	code, out, _ = run(capsys, "pair", "99123456", "--dry-run", "--port", "sim")
	assert code == 0 and PAIR_EXAMPLES["123456"] in out


def test_pair_dry_run_and_bad_id(capsys):
	code, out, _ = run(capsys, "pair", "123456", "--dry-run", "--port", "sim")
	assert code == 0 and PAIR_EXAMPLES["123456"] in out
	code, _, err = run(capsys, "pair", "40024", "--port", "sim")
	assert code == 2 and "6 digits" in err


def test_pair_sends_without_prompting(capsys):
	code, out, _ = run(capsys, "pair", "123456", "--port", "sim")
	assert code == 0 and "paired with dongle" in out


def test_pair_sends_the_spec_message(capsys):
	sent = []

	class Recorder(vl.SimKeytar):
		def send(self, data):
			sent.append(data)

	import vortex_cli.cli as cli

	real = cli.open_device
	cli.open_device = lambda args: __import__("contextlib").nullcontext(
		vl.Keytar(Recorder(), vl.Timing(settle=0))
	)
	try:
		code, out, _ = run(capsys, "pair", "654321")
	finally:
		cli.open_device = real
	assert code == 0 and "paired with dongle" in out
	assert sent == [bytes.fromhex(PAIR_EXAMPLES["654321"])]


def test_pair_exports_a_syx_file(tmp_path, capsys):
	out = tmp_path / "pair.syx"
	code, _, err = run(capsys, "pair", "654321", out)
	assert code == 0 and "wrote" in err
	assert out.read_bytes() == bytes.fromhex(PAIR_EXAMPLES["654321"])
	assert run(capsys, "pair", "123456", out)[0] == 2  # no overwrite without --force
	assert run(capsys, "pair", "123456", out, "--force")[0] == 0
	assert out.read_bytes() == bytes.fromhex(PAIR_EXAMPLES["123456"])


def test_pair_export_dry_run_and_bad_dest(tmp_path, capsys):
	out = tmp_path / "pair.syx"
	code, text, _ = run(capsys, "pair", "123456", out, "--dry-run")
	assert code == 0 and not out.exists() and PAIR_EXAMPLES["123456"] in text
	code, _, err = run(capsys, "pair", "123456", tmp_path / "pair.txt")
	assert code == 2 and ".syx" in err
	code, _, err = run(capsys, "pair", "12345", out)
	assert code == 2 and not out.exists()
