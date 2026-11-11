# Command-line reference

```
vortex <command> [options]
```

**Argument order never matters.** Options may come before or after the command word and may sit between the
positional arguments: `vortex --slot 3 convert a.json device`, `vortex convert a.json --slot 3 device` and
`vortex convert a.json device --slot 3` are identical. (The only restriction: a file literally named like a command,
e.g. `convert`, must be written `./convert`.)

Slots are **1-25**, like the vendor editor's "Preset 1".."Preset 25".

## `convert SOURCE DEST`

The one conversion command. `SOURCE` and `DEST` are each:

* a file: format taken from `.json`, `.vw2` or `.syx` (override with `--from` / `--to`; input format is otherwise
  also detected from content);
* `-`: stdin as source (format detected), stdout as destination (always JSON);
* `device`: the keytar, by USB MIDI.

| from \ to | file | `device` |
|---|---|---|
| JSON file | omitted fields filled from **Alesis's factory defaults** | omitted fields keep **what the keytar holds in that slot**; only changes are written |
| `.vw2` / `.syx` file | whole preset | whole preset replaces the slot |
| `device` | the slot's full contents (needs `--slot`) | not supported; go via a file |

| option | meaning |
|---|---|
| `-s`, `--slot N` | Slot 1-25. **Overrides** a slot in the input file. Required for `device`; required for `.syx` output if the input names no slot. |
| `--from FMT`, `--to FMT` | `json`, `vw2` or `syx`, when the extension doesn't say. |
| `--minimal` | JSON output lists only fields that differ from the factory defaults. |
| `-n`, `--dry-run` | Show what would change; write nothing (still reads the keytar if it is the destination). |
| `-y`, `--yes` | Don't ask for confirmation before writing to the keytar. Required when stdin isn't a terminal. |
| `--no-backup`, `--backup-dir DIR` | Writing to the keytar first saves the slot's previous contents to `DIR/<timestamp>/slot-NN.syx` (+ `.json`); default `./vortex-backups`. |
| `--force` | Overwrite an existing output file (otherwise refused). |
| `--allow-invalid` | Allow out-of-range bytes in *file* outputs. Never applies to the keytar. |
| connection options | `--port`, `--in-port`, `--out-port`, `--settle`, `--timeout` (below). |

### Slot rules

1. `--slot` given: use it.
2. Otherwise the input file's slot (`slot` in JSON, the slot byte in `.syx`).
3. Otherwise: an error, if a slot is needed (writing to the keytar, or a `.syx`). `.vw2` and JSON outputs don't need one.

### Writing to the keytar

```
$ vortex convert lead.json device --slot 3
slot 3 ('' -> 'Lead'): 2 change(s)
  name: "" -> "Lead"
  fader3.cc: 16 -> 74
previous contents saved to vortex-backups/20261010-100535/slot-03.syx
Write slot 3 on the keytar? [y/N] y
slot 3 written and verified
```

The tool reads the slot, merges your file onto it, shows exactly which settings change, saves a restorable backup,
asks, writes the **single** Set message, waits for the device to settle, reads the slot back and compares every byte.
If nothing differs, nothing is written. Restore a backup with
`vortex convert vortex-backups/<stamp>/slot-03.syx device --yes`.

### Examples

```sh
vortex convert lead.json lead.vw2 --slot 3         # JSON -> vendor editor file (factory defaults fill the gaps)
vortex convert lead.json lead.syx --slot 3         # JSON -> SysEx, ready for any MIDI tool
vortex convert lead.vw2 lead.json                  # vendor file -> readable JSON
vortex convert lead.vw2 lead.json --minimal        # ...only what differs from factory
vortex convert device current.json -s 7            # what is on the keytar right now
vortex convert tweak.json device -s 7 --dry-run    # preview a change
vortex convert tweak.json device -s 7              # apply only the fields in tweak.json
vortex convert lead.vw2 device -s 3                # replace slot 3 with a vendor-editor preset
cat lead.json | vortex convert - device -s 3 -y
```

## `backup DIRECTORY`

Reads all 25 slots into `DIRECTORY/slot-01.syx` .. `slot-25.syx` (each a Set message that restores that slot) plus a
readable `slot-NN.json` for each. Takes the connection options.

## `pair DONGLE_ID [DEST]`

Pair the keytar with a Vortex Wireless 2 USB dongle, given the six-digit ID the editor's pairing dialog asks for (spec section 8.2).
It sends the one SysEx message the editor sends. **This replaces the keytar's current pairing.**

```sh
vortex pair 123456                  # send the pairing message for dongle 123456 to the keytar
vortex pair 123456 --dry-run        # print the message; send nothing
vortex pair 123456 pair.syx         # write it to a .syx file instead, for any MIDI tool
```

`DEST` is `device` (the default) or a `.syx` file; an existing file is only replaced with `--force`.

| option | |
|---|---|
| `-n`, `--dry-run` | Print the message; send or write nothing. |
| `--force` | Overwrite an existing `.syx` file. |

Sending to the keytar happens immediately, with no confirmation prompt. The connection options below apply.

## `validate FILE...`

Checks `.json`, `.vw2` and `.syx` files (strict readers: exact sizes, structure, ranges) and reports every problem.
Exit status 1 if any file is bad.

## `devices`

Lists MIDI input/output ports and whether a "Vortex Wireless 2" is visible.

## `fields [--markdown]`, `schema`

Print the table of every JSON key (see also [fields.md](fields.md)) and the JSON Schema.

## Connection options (`convert`, `backup`, `pair`)

| option | default | |
|---|---|---|
| `--port NAME` | `Vortex Wireless 2` | MIDI port name or substring (the OS decorates it, e.g. `Vortex Wireless 2 0` on Windows). |
| `--in-port`, `--out-port` | from `--port` | Override one direction. |
| `--settle S` | 1.5 | Seconds to wait after each write. The device is busy and drops messages for ~0.5 s after a Set (spec section 2). |
| `--timeout S` | 1.5 | Seconds to wait for each reply; reads are retried 3 times. |
| `--port sim` / `sim:FILE` | | A **software keytar** (spec-faithful; state saved in FILE) for trying commands safely. |

MIDI access needs the optional extra: `pip install "vortex-cli[midi]"`.

## Exit status

`0` success, `1` the operation failed (invalid file, no reply from the keytar, ...), `2` the command line is wrong
or you declined to confirm.
