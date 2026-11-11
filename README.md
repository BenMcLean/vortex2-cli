# vortex-cli

Command-line tool and Python library for managing presets on the **Alesis Vortex Wireless 2** keytar.

It converts between four representations of a preset, in any direction:

| | |
|---|---|
| `.vw2` | the file format of Alesis's "Vortex Wireless 2 Preset Editor" |
| `.json` | a human-editable description, partial or complete ([format](docs/preset-format.md)) |
| `.syx` | a ready-to-send SysEx message, for any generic MIDI tool |
| the keytar | read or write a slot directly over USB MIDI or pair it with a wireless dongle |

The key feature: **a JSON file only has to mention what it wants to change.** Converting to the keytar reads the slot's
current contents and applies just those fields; converting to a file fills the gaps from Alesis's factory defaults.

```sh
pip install "vortex-cli[midi]"

echo '{ "name": "Lead", "fader3": { "cc": 74 } }' > lead.json

vortex convert lead.json device --slot 3 --dry-run   # preview: shows exactly which settings change
vortex convert lead.json device --slot 3             # apply them (verifies after)
vortex convert lead.json lead.vw2 --slot 3           # or make a file for the vendor editor
vortex convert lead.json lead.syx --slot 3           # or a SysEx file
vortex convert device now.json --slot 3              # read a slot back as JSON
vortex factory device 3                              # slot 3 back to factory defaults
vortex backup my-keytar/                             # save all 25 slots
vortex pair 123456                                   # pair with a wireless dongle (last six digits of the sticker number)
vortex pair 123456 pair.syx                          # or save that pairing message as a SysEx file
```

## Documentation

* [Preset JSON format](docs/preset-format.md): how partial documents, slots and pads work; every key in [fields.md](docs/fields.md); [JSON Schema](schema/preset.schema.json); [examples](examples)
* [Command-line reference](docs/cli.md)
* [Using the library](docs/library.md): `vortexlib` works on bytes only, with no file or MIDI access
* [Protocol and file-format specification](spec/SPEC.md): the clean-room spec this tool implements, with test vectors

## Design in brief

* **Nothing is ambiguous at run time.** Slots are 1-25; `--slot` overrides the file; no slot anywhere is an error;
	unknown keys are errors; the base preset is determined by where the output goes.
* **Option order never matters.**
* **Safe by default with hardware.** The device never acknowledges writes and validates nothing, so the tool validates
	first, shows a diff, asks, writes once, waits, and reads back to verify. It keeps no state and writes no files you did not name.
* **Two packages.** `vortexlib` is pure (bytes in, bytes out); `vortex_cli` adds files, MIDI ports and the CLI.

## Status and caveats

* The protocol knowledge comes from [spec/SPEC.md](spec/SPEC.md), measured on **one** keytar with one editor version.
	The spec's open questions apply: e.g. whether writing the currently active slot takes effect immediately.
* The conversion code is tested byte-for-byte against all the spec's vectors, and the device logic against a
	simulated keytar (`--port sim`).
* **Tested on hardware:** a keytar on firmware 1.1.5, connected by **USB cable**, on Windows 11. `devices`, `backup`
	(all 25 slots), `convert` from the keytar, `--dry-run`, a full write with verify, a partial (single-field) update,
	an unchanged re-write (correctly skipped), a `.vw2` round trip, restoring from a backup `.syx`, and the error paths
	(missing or out-of-range slot, unknown key, out-of-range value, wrong port) all behaved as documented.
	`pair` was checked on the wire with a MIDI monitor: it sends the same message as the vendor editor.
* Not yet exercised: writing the slot that is currently active on the keytar, writing while it is being played, and
	other firmware versions or operating systems. Try `--dry-run` and `vortex backup` first.
* This is unofficial and unaffiliated with Alesis/inMusic. Use at your own risk.

## Development

```sh
python -m venv .venv && .venv/Scripts/activate      # or bin/activate
pip install -e ".[midi,dev]"
pytest
python tools/gen_data.py    # after editing spec/: regenerate the embedded spec data
python tools/gen_docs.py    # after editing the field model: regenerate schema/ and docs/fields.md
```

`spec/` is the source of truth for the wire formats; the tests fail if the embedded copy or the generated docs fall
out of sync with it.

## License

MIT; see [LICENSE](LICENSE).
