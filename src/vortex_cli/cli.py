"""Command-line interface.  All file and port I/O lives here; conversion logic lives in ``vortexlib``."""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
from typing import Sequence

import vortexlib as vl

from . import __version__
from .ports import DEFAULT_PORT_NAME, PortError, find_port, list_ports, open_keytar

EXT_FORMATS = {".json": "json", ".vw2": "vw2", ".syx": "syx"}
DEVICE = "device"
STDIO = "-"


class UsageError(Exception):
	"""A problem with the command line itself (exit status 2)."""


def eprint(*a) -> None:
	print(*a, file=sys.stderr)


# -- helpers ----------------------------------------------------------------------------------


def format_of(path: str, override: str | None) -> str | None:
	return override or EXT_FORMATS.get(pathlib.Path(path).suffix.lower())


def read_input(src: str, fmt: str | None) -> vl.Loaded:
	data = sys.stdin.buffer.read() if src == STDIO else pathlib.Path(src).read_bytes()
	try:
		return vl.load(data, fmt or (None if src == STDIO else format_of(src, None)))
	except vl.DocError as e:
		raise vl.DocError([f"{src}: {m}" for m in e.errors]) from None
	except vl.FormatError as e:
		raise vl.FormatError(f"{src}: {e}") from None


def timing_from(args) -> vl.Timing:
	return vl.Timing(settle=args.settle, reply_timeout=args.timeout)


def open_device(args):
	return open_keytar(args.port, args.in_port, args.out_port, timing_from(args))


def show_diff(rows) -> None:
	for key, old, new in rows:
		o = "(unset)" if old is None else json.dumps(old)
		n = "(unset)" if new is None else json.dumps(new)
		print(f"  {key}: {o} -> {n}")


def write_backup(directory: pathlib.Path, slot: int, preset: vl.Preset) -> pathlib.Path:
	"""Save a restorable copy: ``slot-NN.syx`` (a Set message) and a readable ``slot-NN.json``."""
	directory.mkdir(parents=True, exist_ok=True)
	stem = directory / f"slot-{slot:02d}"
	stem.with_suffix(".syx").write_bytes(vl.dump(preset, "syx", slot))
	stem.with_suffix(".json").write_bytes(vl.dump(preset, "json", slot))
	return stem.with_suffix(".syx")


def confirm(args, prompt: str) -> None:
	if args.yes:
		return
	if not sys.stdin.isatty():
		raise UsageError(
			"refusing to write to the keytar without confirmation; pass --yes"
		)
	if input(f"{prompt} [y/N] ").strip().lower() not in ("y", "yes"):
		raise UsageError("aborted")


def write_file(path: str, data: bytes, force: bool) -> None:
	p = pathlib.Path(path)
	if p.exists() and not force:
		raise UsageError(f"{path} already exists; pass --force to overwrite")
	p.write_bytes(data)


# -- convert ----------------------------------------------------------------------------------


def cmd_convert(args) -> int:
	src, dst = args.source, args.dest
	if src == DEVICE and dst == DEVICE:
		raise UsageError(
			"both source and destination are the device; convert via a file instead"
		)
	slot = args.slot
	if slot is not None:
		vl.check_slot(slot)

	# 1. read the source
	if src == DEVICE:
		if slot is None:
			raise UsageError("reading from the keytar needs --slot N")
		with open_device(args) as kt:
			loaded = vl.Loaded("device", slot=slot, preset=kt.read(slot))
	else:
		loaded = read_input(src, args.from_format)
		slot = slot if slot is not None else loaded.slot  # --slot overrides the file

	# 2. write to the keytar
	if dst == DEVICE:
		if slot is None:
			raise UsageError(
				"no slot: the input does not name one and --slot was not given"
			)
		vl.check_slot(slot)
		with open_device(args) as kt:
			current = kt.read(slot)
			new = vl.resolve(
				loaded, current
			)  # omitted fields keep what the keytar holds
			if new.problems():
				raise vl.DeviceError(
					"refusing to write an invalid preset: " + "; ".join(new.problems())
				)
			rows = vl.diff_presets(current, new)
			if not rows:
				print(f"slot {slot} already matches; nothing to write")
				return 0
			print(
				f"slot {slot} ({current.name!r} -> {new.name!r}): {len(rows)} change(s)"
			)
			show_diff(rows)
			if args.dry_run:
				print("dry run: nothing written")
				return 0
			confirm(args, f"Write slot {slot} on the keytar?")
			if not args.no_backup:
				stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
				print(
					f"previous contents saved to {write_backup(pathlib.Path(args.backup_dir) / stamp, slot, current)}"
				)
			kt.write(slot, new)
			print(f"slot {slot} written and verified")
		return 0

	# 3. write to a file / stdout
	fmt = "json" if dst == STDIO else format_of(dst, args.to_format)
	if fmt is None:
		raise UsageError(
			f"cannot tell the output format of {dst!r}; use .json, .vw2 or .syx, or --to"
		)
	if fmt == "syx" and slot is None:
		raise UsageError(
			"a .syx file needs a slot: the input does not name one and --slot was not given"
		)
	base = vl.factory(slot)  # omitted fields come from Alesis's defaults
	new = vl.resolve(loaded, base)
	if new.problems() and not args.allow_invalid:
		raise vl.DeviceError(
			"the preset is invalid: "
			+ "; ".join(new.problems())
			+ " (--allow-invalid to write anyway)"
		)
	data = vl.dump(
		new, fmt, slot, reference=base if args.minimal and fmt == "json" else None
	)
	if args.dry_run:
		print(
			f"dry run: would write {len(data)} bytes of {fmt} to {dst}", file=sys.stderr
		)
	elif dst == STDIO:
		sys.stdout.write(data.decode("utf-8"))
	else:
		write_file(dst, data, args.force)
		eprint(f"wrote {dst} ({fmt}{'' if slot is None else f', slot {slot}'})")
	return 0


# -- backup -----------------------------------------------------------------------------------


def cmd_backup(args) -> int:
	out = pathlib.Path(args.directory)
	with open_device(args) as kt:
		for slot in range(1, vl.SLOT_COUNT + 1):
			preset = kt.read(slot)
			write_backup(out, slot, preset)
			print(f"slot {slot:2d}: {preset.name!r}")
	print(
		f"saved to {out}; restore one with: vortex convert {out / 'slot-NN.syx'} device --yes"
	)
	return 0


# -- validate ---------------------------------------------------------------------------------


def cmd_validate(args) -> int:
	bad = 0
	for path in args.files:
		try:
			loaded = read_input(path, None)
			probs = loaded.preset.problems() if loaded.preset else []
		except (vl.DocError, vl.FormatError) as e:
			msgs = e.errors if isinstance(e, vl.DocError) else [str(e)]
			bad += 1
			for m in msgs:
				print(m)
			continue
		if probs:
			bad += 1
			for m in probs:
				print(f"{path}: {m}")
		else:
			print(
				f"{path}: ok ({loaded.fmt}{'' if loaded.slot is None else f', slot {loaded.slot}'})"
			)
	return 1 if bad else 0


# -- devices / fields / schema -----------------------------------------------------------------


def cmd_devices(args) -> int:
	ins, outs = list_ports()
	for title, names in (("MIDI inputs", ins), ("MIDI outputs", outs)):
		print(f"{title}:")
		for n in names or ["(none)"]:
			mark = "   <- keytar" if DEFAULT_PORT_NAME.lower() in n.lower() else ""
			print(f"  {n}{mark}")
	try:
		find_port(ins, DEFAULT_PORT_NAME, "input")
		find_port(outs, DEFAULT_PORT_NAME, "output")
	except PortError as e:
		print(f"\n{e}")
		return 1
	return 0


def cmd_fields(args) -> int:
	rows = vl.field_rows()
	if args.markdown:
		print(
			"| key | values | factory default | raw byte | meaning |\n|---|---|---|---|---|"
		)
		for k, t, d, b, desc in rows:
			print(f"| `{k}` | {t} | {d} | {b} | {desc} |")
	else:
		for k, t, d, b, desc in rows:
			print(f"{k:28} {t.replace(chr(92), ''):40} {d:12} {desc}  [byte: {b}]")
	return 0


def cmd_schema(args) -> int:
	sys.stdout.write(json.dumps(vl.json_schema(), indent=2) + "\n")
	return 0


# -- argument parsing ----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
	p = argparse.ArgumentParser(
		prog="vortex",
		description="Manage Alesis Vortex Wireless 2 presets: .vw2, .syx, JSON, and the keytar itself.",
		epilog="Slots are numbered 1-25 like the editor's 'Preset 1'..'Preset 25'. Docs: docs/cli.md",
	)
	p.add_argument("--version", action="version", version=f"vortex-cli {__version__}")
	sub = p.add_subparsers(dest="command", required=True, metavar="command")

	dev = argparse.ArgumentParser(add_help=False)
	g = dev.add_argument_group("keytar connection")
	g.add_argument(
		"--port",
		help=f"MIDI port name or substring (default {DEFAULT_PORT_NAME!r}); "
		"'sim' or 'sim:FILE' selects a software keytar for testing",
	)
	g.add_argument("--in-port", help="override the MIDI input port name")
	g.add_argument("--out-port", help="override the MIDI output port name")
	g.add_argument(
		"--settle",
		type=float,
		default=1.5,
		help="seconds to wait after each write (default 1.5)",
	)
	g.add_argument(
		"--timeout",
		type=float,
		default=1.5,
		help="seconds to wait for a reply (default 1.5)",
	)

	c = sub.add_parser(
		"convert",
		parents=[dev],
		help="convert between .json, .vw2, .syx and the keytar",
		description="Convert SOURCE to DEST. Either may be a file, '-' (stdin / stdout JSON) or the word "
		"'device' (the keytar). Fields a JSON file omits are filled from Alesis's factory "
		"defaults when DEST is a file, or from what the keytar currently holds when DEST is 'device'.",
	)
	c.add_argument("source", help="input file, '-', or 'device'")
	c.add_argument("dest", help="output file, '-', or 'device'")
	c.add_argument(
		"-s",
		"--slot",
		type=int,
		help="slot 1-25; overrides any slot in the input file (required for "
		"'device', and for .syx output if the input names none)",
	)
	c.add_argument(
		"--from",
		dest="from_format",
		choices=vl.FORMATS,
		help="input format (default: from extension/content)",
	)
	c.add_argument(
		"--to",
		dest="to_format",
		choices=vl.FORMATS,
		help="output format (default: from extension)",
	)
	c.add_argument(
		"--minimal",
		action="store_true",
		help="JSON output: list only fields that differ from the factory defaults",
	)
	c.add_argument(
		"-n",
		"--dry-run",
		action="store_true",
		help="show what would change; write nothing",
	)
	c.add_argument(
		"-y",
		"--yes",
		action="store_true",
		help="do not ask before writing to the keytar",
	)
	c.add_argument(
		"--no-backup",
		action="store_true",
		help="do not save the keytar's previous slot contents before writing",
	)
	c.add_argument(
		"--backup-dir",
		default="vortex-backups",
		help="where backups go (default ./vortex-backups)",
	)
	c.add_argument(
		"--force", action="store_true", help="overwrite an existing output file"
	)
	c.add_argument(
		"--allow-invalid",
		action="store_true",
		help="write out-of-range values to files (never to the keytar)",
	)
	c.set_defaults(func=cmd_convert)

	b = sub.add_parser(
		"backup",
		parents=[dev],
		help="save all 25 slots from the keytar into a directory",
	)
	b.add_argument("directory")
	b.set_defaults(func=cmd_backup)

	v = sub.add_parser(
		"validate", help="check preset files (.json, .vw2, .syx) without converting"
	)
	v.add_argument("files", nargs="+")
	v.set_defaults(func=cmd_validate)

	d = sub.add_parser(
		"devices", help="list MIDI ports and whether the keytar is visible"
	)
	d.set_defaults(func=cmd_devices)

	f = sub.add_parser(
		"fields",
		help="list every JSON key with its accepted values and factory default",
	)
	f.add_argument("--markdown", action="store_true")
	f.set_defaults(func=cmd_fields)

	s = sub.add_parser("schema", help="print the JSON Schema for preset files")
	s.set_defaults(func=cmd_schema)
	p.subparser_map = sub.choices
	return p


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
	"""Parse ``argv`` so that argument order never matters.

	Options may come before or after the command word and may be interleaved with the positional
	arguments.  (argparse's own sub-command handling requires options for a command to follow it, so the
	command word is located first and the remaining arguments are parsed by that command's parser.)
	"""
	parser = build_parser()
	subs = parser.subparser_map
	takes_value = {
		o
		for sp in subs.values()
		for a in sp._actions
		for o in a.option_strings
		if a.nargs != 0
	}
	idx, skip = None, False
	for i, a in enumerate(argv):
		if skip:
			skip = False
		elif a in subs:
			idx = i
			break
		elif a in takes_value:
			skip = True
	if idx is None:
		return parser.parse_args(
			list(argv)
		)  # --help / --version / missing-command error
	rest = list(argv[:idx]) + list(argv[idx + 1 :])
	return subs[argv[idx]].parse_intermixed_args(rest)


def main(argv: Sequence[str] | None = None) -> int:
	args = parse_args(sys.argv[1:] if argv is None else list(argv))
	try:
		return args.func(args)
	except UsageError as e:
		eprint(f"vortex: {e}")
		return 2
	except vl.DocError as e:
		for m in e.errors:
			eprint(f"vortex: {m}")
		return 1
	except (
		vl.FormatError,
		vl.DeviceError,
		vl.SlotRequired,
		PortError,
		OSError,
		ValueError,
	) as e:
		eprint(f"vortex: {e}")
		return 1
	except KeyboardInterrupt:
		eprint("interrupted")
		return 130
