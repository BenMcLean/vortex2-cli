# Preset JSON format

A preset file describes **one preset**: an optional `slot` and any subset of the keytar's controls. There are no
includes, templates or variables. That is deliberate: this tool needs every ambiguity resolved *before* it runs, so
anything cleverer (generating many presets from shared parts, for example) belongs in a separate tool that writes
these files.

The structure (keys, types, ranges, accepted names) is defined by the machine-readable
[`schema/preset.schema.json`](../schema/preset.schema.json) (JSON Schema 2020-12; point your editor at it with a
`"$schema"` key for completion and error squiggles). It is generated from the same table as
[fields.md](fields.md), which lists every key, its accepted values, factory default and raw byte. This page covers
what a schema can't say: what a document *means*. Examples: [`examples/`](../examples).

## Partial documents

Every key is optional. A key you leave out is *unspecified*: the document says nothing about that setting, and what
fills the gap is up to whatever reads it. (`vortex` uses Alesis's factory defaults when the result goes to a file and
what the keytar currently holds when it goes to the keytar; see [cli.md](cli.md#convert-source-dest).) So
`{"name": "Lead"}` changes the name and nothing else.

A document that states every setting (every key in [fields.md](fields.md)) is *complete*: it doesn't depend on
anything outside itself. `.vw2` and `.syx` files are always complete. Bytes JSON never shows (reserved bytes, a Panic
pad's unused values) are zero in a complete document, as in the factory preset.

## Slots

`slot` is optional and counts **1 to 25**, like the vendor editor's "Preset 1".."Preset 25". (The spec's wire index is
0-based; this format converts at the boundary and never shows you the 0-based number.) `.vw2` files have no slot.
How `vortex` combines this with `--slot` is in [cli.md](cli.md#slot-rules).

## Structure

```json
{
  "slot": 3,
  "name": "Lead Synth",
  "program_change": { "send_on_load": true, "msb": 0, "lsb": 0, "program": 12 },
  "split":  { "enabled": false, "key": 19, "curve": 5 },
  "upper":  { "transpose": 0, "midi_to_din": true, "channel": 2 },
  "lower":  { "transpose": 0, "midi_to_din": true, "channel": 1 },
  "sustain": { "channel": 1 },
  "wheel":  { "channel": 1, "direction": "Normal" },
  "volume": { "cc": 7, "min": 0, "max": 127, "channel": 1 },
  "ribbon": { "default_bank": 1, "release_mode": "Latch",
              "bank1": { "type": "CC", "cc": 1, "min": 0, "max": 127, "channel": 1 },
              "bank2": { }, "bank3": { } },
  "tilt":   { "type": "CC", "cc": 1, "min": 0, "max": 127, "channel": 1 },
  "fader1": { "cc": 14, "min": 0, "max": 127, "channel": 1 },
  "pad1":   { "type": "Note", "note": 36, "channel": 10, "color1": "Blue" }
}
```

Top-level keys: `$schema`, `description` (free text, ignored), `slot`, `name`, `program_change`, `split`, `upper`,
`lower`, `sustain`, `wheel`, `volume`, `ribbon`, `tilt`, `fader1`..`fader8`, `pad1`..`pad8`, and `reserved`.
Unknown keys are errors (with a "did you mean" hint), because a typo that is silently ignored would leave your
keytar unchanged without telling you.

### Values

| kind | accepted | written as |
|---|---|---|
| yes/no and on/off settings (`send_on_load`, `midi_to_din`, `split.enabled`) | `true` / `false`, or `"Yes"`/`"No"`/`"On"`/`"Off"` | `true` / `false` |
| MIDI channels, velocity curves, ribbon banks | plain integers: channels `1`..`16`, curves `1`..`8`, banks `1`..`3` (names like `"Channel 10"` are not accepted) | integer |
| named choices (pad `type`, `color1`..`4`, `direction`, `release_mode`, ribbon/tilt `type`) | the name shown in the vendor editor | the name |
| numbers (`cc`, `min`, `max`, `note`, ...) | integer in the range given in [fields.md](fields.md) | integer |
| `transpose` | semitones, `-12`..`12` | integer |
| `split.key` | `1`..`36` as the editor shows it | integer |

Names ignore case, spaces, `_` and `-`: `"cc toggle"`, `"CC_Toggle"` and `"CC Toggle"` are the same. Booleans and
numbers are strict: `"7"` is not `7`, and `true` is not `1`.

### Numbers and the raw bytes

**The numbers in a JSON file are the numbers you see on the vendor editor, not the bytes the keytar stores.** The
spec (section 4.2) describes the bytes; this format translates them so that files read the way a musician thinks.
The tool converts both ways, so you only need this table to read a `.syx` or `.vw2` in a hex editor, or when
comparing against the spec:

| JSON key(s) | you write | raw byte | example |
|---|---|---|---|
| any `channel` | `1`..`16` | value - 1 (`0`..`15`) | `"channel": 10` is byte `09` |
| `split.curve`, Note pad `curve` | `1`..`8` | value - 1 | `"curve": 5` is byte `04` |
| `ribbon.default_bank` | `1`..`3` | value - 1 | `"default_bank": 2` is byte `01` |
| `split.key` | `1`..`36` | value - 1 | `"key": 19` is byte `12` (hex) |
| `upper.transpose`, `lower.transpose` | `-12`..`12` semitones | value + 12 | `"transpose": -12` is byte `00`, `0` is `0C`, `12` is `18` |
| `send_on_load`, `midi_to_din`, `split.enabled` | `true` / `false` | **`true` = `00`, `false` = `01`** | see below |
| named choices (pad `type`, colours, `direction`, `release_mode`, ribbon/tilt `type`) | the name | its position in the list, from 0 | `"type": "CC Toggle"` is byte `01`; `"Blue"` is `06` |
| `cc`, `min`, `max`, `note`, `velocity`, `program`, `bank_lsb`, `bank_msb`, `on_value`, ... | `0`..`127` | same | `"cc": 74` is byte `4A` |
| `slot` | `1`..`25` | wire slot index = value - 1 (`0`..`24`) | `"slot": 3` is slot byte `02` |

Watch the booleans: the keytar stores *Yes* / *On* / *Split On* as `00` and *No* / *Off* / *Split Off* as `01`
(the spec's enumerations list the "yes" side first). JSON `true` means Yes / On / Split On, so it is the byte `00`.
The raw byte for every key is also in the *raw byte* column of [fields.md](fields.md), generated from the same table
the converter uses.

Values outside these ranges are never written; a byte the keytar holds that has no valid value shows up as
`{"raw": n}` (see below).

### Name

`name` is up to 16 printable ASCII characters (`0x20`..`0x7E`).

### Pads

Pads have a `type` that decides what their three stored value bytes mean, so those bytes get type-specific names.
The spec's anonymous `value1`..`value3` are **not** accepted.

| `type` | keys |
|---|---|
| `Note` | `note` (0-127), `velocity` (0-127; 0 = use the curve), `curve` (1-8) |
| `CC Toggle` | `cc`, `on_value`, `off_value` |
| `CC Momentary` | `cc`, `press_value`, `release_value` |
| `Program Change` | `program`, `bank_lsb`, `bank_msb` |
| `Panic` | (none) |

All pads also take `channel` and `color1`..`color4`. For Note pads the colours are idle / struck at velocity 1-63 /
64-95 / 96-127; other types use only `color1` (idle) and `color2` (active). Colours: `LED Off`, `Chartreuse`, `Green`,
`Aquamarine`, `Cyan`, `Azure`, `Blue`, `Violet`, `Magenta`, `Rose`, `Red`, `Orange`, `Yellow`, `White`.

Rules that remove ambiguity:

* A type-specific key must match the pad's **effective** type: the `type` in the file if given, otherwise the pad's
	type in the base preset. `{"pad1": {"cc": 5}}` on a pad that is currently a Note pad is an error that says so.
* **Changing a pad's type resets its three value bytes to 0** unless the same file also sets them. Otherwise a Note
	pad's note 36 would silently become CC 36. Restating the type the pad already has resets nothing.
* A `Panic` pad's three value bytes are unused. They are never shown, but they are preserved from the base preset.

### Reserved bytes

Nine bytes the vendor editor never displays are exposed as `reserved.wheel`, `reserved.tilt` and `reserved.fader1`..`reserved.fader7`
(named for the control they follow in the message). They are preserved when reading from the keytar and written as 0
in factory defaults. Leave them out unless you know why you need them; exports only include them when non-zero.

### Invalid bytes: `{"raw": n}`

The keytar validates nothing, so it can hold values the format cannot name (for example channel byte 127). Reading
such a preset emits `{"raw": 127}` for that key instead of failing. Such a value is only for files: `vortex` will
not write it to the keytar (see `--allow-invalid` in [cli.md](cli.md#convert-source-dest)).

## Validation

The JSON Schema checks canonical spellings; `vortex` is a little more lenient (names ignore case, as above) and
reports every problem at once, each with its JSON path. See `vortex validate` in [cli.md](cli.md#validate-file).
