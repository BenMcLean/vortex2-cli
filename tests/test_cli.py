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
	assert (
		run(
			capsys, "convert", pre, "device", "-s", 4, "-y", "--no-backup", *port, *SIM
		)[0]
		== 0
	)
	code, out, _ = run(
		capsys, "convert", doc, "device", "-s", 4, "--dry-run", *port, *SIM
	)
	assert code == 0 and "dry run" in out and "name" in out and "volume" not in out
	code, out, _ = run(
		capsys,
		"convert",
		doc,
		"device",
		"-s",
		4,
		"-y",
		"--backup-dir",
		tmp_path / "bk",
		*port,
		*SIM,
	)
	assert code == 0 and "verified" in out
	assert list((tmp_path / "bk").glob("*/slot-04.syx"))
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


def test_backup_and_restore(tmp_path, capsys):
	port = ["--port", f"sim:{tmp_path / 'kt.json'}", *SIM]
	assert run(capsys, "backup", tmp_path / "b", *port)[0] == 0
	assert len(list((tmp_path / "b").glob("slot-*.syx"))) == 25
	assert (
		run(capsys, "convert", tmp_path / "b" / "slot-07.syx", "device", "-y", *port)[0]
		== 0
	)


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
