# Alesis Vortex Wireless 2: Preset Interchange Specification

**Version 0.9 (draft).** Covers: (1) the USB-MIDI SysEx protocol used to read and write the 25 control presets stored in the
keytar, (2) the `.vw2` preset file format of the vendor's "Vortex Wireless 2 Preset Editor" 1.0.3, and (3) how to convert
between the two.

## 0. Provenance and clean-room use

This specification was produced by *black-box observation*: sending messages to a keytar, observing its replies, and observing
the files and MIDI traffic of the vendor editor while driving it with known inputs. It contains no vendor code and no
disassembly. Parameter *names* are those shown in the editor's user interface, and the short functional descriptions of what a
parameter does on the instrument (for example "velocity 0 means: use the velocity curve") are restated in our own words from the
vendor's publicly distributed user guide; those descriptions are **non-normative**; everything normative (positions, encodings,
framing) comes from measurement.

An implementer should need **only this document and the files in `spec/`** (all paths below are relative to that folder):

| file | content |
|---|---|
| `SPEC.md` | this document |
| `layout.json` | every byte of the SysEx message: role, name, encoding, and the offset of the same byte in the `.vw2` file (schema: Appendix A) |
| `vw2_template.hex` | the 1071-byte `.vw2` with all 171 value bytes set to zero: the constant part of the file |
| `vectors.json` | editor-produced (SysEx message, `.vw2` file) pairs, plus `negative` inputs a reader must reject |
| `field_vectors.json` | the same messages decoded into named, human-readable values: tests for section 4.2 |
| `device_factory_defaults.json` | all 25 slots (plus an out-of-range Get) read from a keytar after the vendor's factory reset (section 5) |

Vendor software measured: "Vortex Wireless 2 Preset Editor" 1.0.3 (executable file version 1.0.3.45375, shipped with its own user
guide v1.0), on Windows 11. Nothing in this document is known to hold for other editor versions or firmware versions.

Statements are tagged **[M]** *measured* (observed repeatedly, see section 10 for the evidence), **[D]** *deduced* (consistent
with all observations, not directly tested), or **[U]** *unknown*. A conforming implementation must not rely on [U] items.

Terminology: MUST / SHOULD / MAY as in RFC 2119.

### 0.1 Scope of the measurements

All device measurements were made on **one** keytar (firmware version and hardware revision not recorded). Contents are reported as
read after resetting it with the vendor's documented factory-reset procedure (section 5.2), so they are Alesis's defaults. The protocol
results (framing, commands, edge behaviour) do not depend on stored contents. Nothing was ever written to a slot above 24.

## 1. Conventions

- Bytes are written in hexadecimal. `x..y` is an inclusive range.
- **Message offset** counts the SysEx start byte `F0` as offset 0. (`F0` and `F7` are included in all message offsets and lengths.)
- A **preset body** is the 171 bytes at message offsets 10..180: the name, then every parameter.
- All SysEx data bytes are 7-bit (`00..7F`). Every field in this document therefore also fits in 7 bits.

## 2. Transport

[M] The keytar is a USB class-compliant MIDI device (USB vendor 13B2, product 005E) exposing one MIDI input and one MIDI output
port, both named `Vortex Wireless 2` by the host. All preset traffic is SysEx on that port pair. Nothing else (notes, controllers)
is part of this specification.

[M] The device answers a *Get* message with a *Reply* message. It sends **no acknowledgement** of any kind to a *Set* message.

[M] **Timing.** After a Set, the device is busy: a Get sent 0.1 s or 0.25 s after a Set receives *no reply*; a Get sent 0.5 s or
more after a Set receives the new data. A Get that arrives while the device is busy is silently dropped (it is not queued), so the host must re-send it. An implementation SHOULD wait at least 1.5 s after a Set before sending the
next message, and SHOULD use a reply timeout of at least 1 s. (The vendor editor's replies arrive about 0.3 s after its Get.)

[M] The device accepts only complete messages: see section 6 for what it ignores.

**Finding the device.** Match the MIDI port by name *substring* `Vortex Wireless 2`: the host decorates it. On Windows (WinMM) the
input was listed as `Vortex Wireless 2 0` and the output as `Vortex Wireless 2 1`; other hosts will differ. Use the USB IDs above if the
platform exposes them. Whether the device answers a Universal Device Inquiry (`F0 7E 7F 06 01 F7`) was not tested [U].

**Sharing the port.** On Windows an independent program and the vendor editor held the device's MIDI ports open at the same time and both
exchanged messages with it without any interference we could observe [M]. Behaviour on other platforms, and with two programs
*talking at once*, is [U].

**Receiving.** Each Reply is one complete SysEx message of 182 bytes. A host MIDI stack must be configured to deliver SysEx
(some stacks filter it by default) and must have enough input buffer for 182 bytes.

## 3. Message framing

Every preset message is:

```
F0  00 00 0E  52 5E  <command>  <length: 2 bytes>  <body: length bytes>  F7
```

| offset | bytes | meaning |
|---|---|---|
| 0 | `F0` | SysEx start |
| 1..3 | `00 00 0E` | manufacturer ID (Alesis) [M] |
| 4..5 | `52 5E` | device/model identifier; constant in every message observed. Meaning of the individual bytes [U] |
| 6 | command | `02` Get, `01` Set, `03` Reply [M] |
| 7..8 | length | 14-bit big-endian: `length = (b7 << 7) \| b8` = number of bytes strictly between offset 8 and the final `F7` [M] |
| 9.. | body | command-specific |
| last | `F7` | SysEx end |

### 3.1 Get (host to device)

`F0 00 00 0E 52 5E 02 00 01 <slot> F7`: 11 bytes; length = 1; the body is one byte, the **slot index** (0..24, zero-based:
"Preset 1" in the editor is slot 0). [M]

### 3.2 Reply (device to host)

`F0 00 00 0E 52 5E 03 01 2C <slot> <171 body bytes> F7`: 182 bytes; length = 172 (`01 2C`); body = slot byte + 171 preset-body
bytes. The slot byte echoes the requested slot for slots 0..24. [M]

### 3.3 Set (host to device)

Identical to a Reply except that the command is `01` [M]: the device writes the 171 preset-body bytes into the slot named by
the slot byte. There is no response. The vendor editor sends exactly this single message for "Send Preset" and nothing else [M].
The editor sends the bytes *unchanged* from what it holds, including bytes it does not display [M] (see reserved bytes).

### 3.4 Worked examples

**A Get for slot 5** (11 bytes):

```
F0 00 00 0E 52 5E 02 00 01 05 F7
F0 | 00 00 0E | 52 5E | 02 | 00 01 | 05 | F7
start | manufacturer | device,model | Get | length = 1 | slot 5 | end
```

**The Reply for slot 6 of a factory-reset keytar** (182 bytes; the number on the left is the message offset of the first byte of the row):

```
  0  F0 00 00 0E 52 5E 03 01 2C 06 00 00 00 00 00 00
 16  00 00 00 00 00 00 00 00 00 00 00 00 00 06 04 01
 32  12 0C 00 01 0C 00 00 00 00 00 00 07 00 7F 00 00
 48  01 00 01 00 7F 00 01 00 00 7F 00 00 16 00 7F 00
 64  00 01 00 7F 00 00 0E 00 7F 00 00 0F 00 7F 00 00
 80  10 00 7F 00 00 11 00 7F 00 00 12 00 7F 00 00 13
 96  00 7F 00 00 14 00 7F 00 00 15 00 7F 00 00 24 00
112  00 09 06 02 0C 0A 00 25 00 00 09 06 02 0C 0A 00
128  26 00 00 09 06 02 0C 0A 00 27 00 00 09 06 02 0C
144  0A 00 28 00 00 09 06 02 0C 0A 00 29 00 00 09 06
160  02 0C 0A 00 2A 00 00 09 06 02 0C 0A 00 2B 00 00
176  09 06 02 0C 0A F7
```

Reading it: offsets 0..9 are `F0 | 00 00 0E | 52 5E | 03 | 01 2C | 06` (start, manufacturer, device/model, Reply, length 172, slot 6); offsets 10..25 are sixteen `00` (an empty name); offset 29 (`pc.program`) is `06`; the final byte is `F7`. Pad 1 occupies offsets 109..117 as `00 24 00 00 09 06 02 0C 0A`, which decodes (section 4.2) as: type `00` Note, note `24` = 36, velocity 0, curve byte 0 = Curve 1, channel byte 9 = Channel 10, colours Blue, Green, Yellow, Red.

**Writing the same preset into slot 24:** take that message and change offset 6 to `01` (Set), offset 9 to `18` (slot 24) and, to keep the factory convention that the Program Change number equals the slot, offset 29 to `18`. Everything else, including the length bytes `01 2C`, is unchanged.

## 4. Complete message layout

Every byte of a Reply or Set message (182 bytes). "file offset" is the position of the same byte in a `.vw2` file (section 7); bytes
with no file offset are not stored in the file.

| msg offset | file offset | field | encoding / value |
|---|---|---|---|
| 0 |  | `sysex_start` | `F0` |
| 1 |  | `manufacturer_id_1` | `00` |
| 2 |  | `manufacturer_id_2` | `00` |
| 3 |  | `manufacturer_id_3` | `0E` |
| 4 |  | `device_family` | `52` |
| 5 |  | `device_model` | `5E` |
| 6 |  | `command` | `02` Get, `01` Set, `03` Reply |
| 7 |  | `length_hi` | 14-bit big-endian length (see section 3) |
| 8 |  | `length_lo` | 14-bit big-endian length (see section 3) |
| 9 |  | `slot` | slot index 0..24 |
| 10 | 36 | `name[0]` | ASCII, `00` padded |
| 11 | 37 | `name[1]` | ASCII, `00` padded |
| 12 | 38 | `name[2]` | ASCII, `00` padded |
| 13 | 39 | `name[3]` | ASCII, `00` padded |
| 14 | 40 | `name[4]` | ASCII, `00` padded |
| 15 | 41 | `name[5]` | ASCII, `00` padded |
| 16 | 42 | `name[6]` | ASCII, `00` padded |
| 17 | 43 | `name[7]` | ASCII, `00` padded |
| 18 | 44 | `name[8]` | ASCII, `00` padded |
| 19 | 45 | `name[9]` | ASCII, `00` padded |
| 20 | 46 | `name[10]` | ASCII, `00` padded |
| 21 | 47 | `name[11]` | ASCII, `00` padded |
| 22 | 48 | `name[12]` | ASCII, `00` padded |
| 23 | 49 | `name[13]` | ASCII, `00` padded |
| 24 | 50 | `name[14]` | ASCII, `00` padded |
| 25 | 51 | `name[15]` | ASCII, `00` padded |
| 26 | 76 | `pc.send_on_load` | enum: 0=Yes, 1=No |
| 27 | 77 | `pc.msb` | 0..127 |
| 28 | 78 | `pc.lsb` | 0..127 |
| 29 | 79 | `pc.program` | 0..127 |
| 30 | 104 | `split.curve` | enum: 8 values (0=Curve 1 .. 7=Curve 8) |
| 31 | 105 | `split.mode` | enum: 0=Split On, 1=Split Off |
| 32 | 106 | `split.key` | 0..35 (shown as byte + 1) |
| 33 | 131 | `upper.transpose` | 0..24 (shown as byte - 12) |
| 34 | 132 | `upper.midi_to_din` | enum: 0=On, 1=Off |
| 35 | 133 | `upper.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 36 | 158 | `lower.transpose` | 0..24 (shown as byte - 12) |
| 37 | 159 | `lower.midi_to_din` | enum: 0=On, 1=Off |
| 38 | 160 | `lower.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 39 | 185 | `sustain.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 40 | 210 | `wheel.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 41 | 211 | `wheel.direction` | enum: 0=Normal, 1=Reverse |
| 42 | 236 | `reserved_after_wheel` | reserved (write 00) |
| 43 | 237 | `volume.cc` | 0..127 |
| 44 | 238 | `volume.min` | 0..127 |
| 45 | 239 | `volume.max` | 0..127 |
| 46 | 240 | `volume.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 47 | 265 | `ribbon.default_bank` | enum: 0=Bank 1, 1=Bank 2, 2=Bank 3 |
| 48 | 266 | `ribbon.release_mode` | enum: 0=Return, 1=Latch |
| 49 | 291 | `ribbon.bank1.type` | enum: 0=CC, 1=Pitch Bend |
| 50 | 292 | `ribbon.bank1.cc` | 0..127 |
| 51 | 293 | `ribbon.bank1.min` | 0..127 |
| 52 | 294 | `ribbon.bank1.max` | 0..127 |
| 53 | 295 | `ribbon.bank1.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 54 | 320 | `ribbon.bank2.type` | enum: 0=CC, 1=Pitch Bend |
| 55 | 321 | `ribbon.bank2.cc` | 0..127 |
| 56 | 322 | `ribbon.bank2.min` | 0..127 |
| 57 | 323 | `ribbon.bank2.max` | 0..127 |
| 58 | 324 | `ribbon.bank2.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 59 | 349 | `ribbon.bank3.type` | enum: 0=CC, 1=Pitch Bend |
| 60 | 350 | `ribbon.bank3.cc` | 0..127 |
| 61 | 351 | `ribbon.bank3.min` | 0..127 |
| 62 | 352 | `ribbon.bank3.max` | 0..127 |
| 63 | 353 | `ribbon.bank3.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 64 | 378 | `tilt.type` | enum: 0=CC, 1=Pitch Bend |
| 65 | 379 | `tilt.cc` | 0..127 |
| 66 | 380 | `tilt.min` | 0..127 |
| 67 | 381 | `tilt.max` | 0..127 |
| 68 | 382 | `tilt.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 69 | 407 | `reserved_after_tilt` | reserved (write 00) |
| 70 | 408 | `fader1.cc` | 0..127 |
| 71 | 409 | `fader1.min` | 0..127 |
| 72 | 410 | `fader1.max` | 0..127 |
| 73 | 411 | `fader1.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 74 | 436 | `reserved_after_fader1` | reserved (write 00) |
| 75 | 437 | `fader2.cc` | 0..127 |
| 76 | 438 | `fader2.min` | 0..127 |
| 77 | 439 | `fader2.max` | 0..127 |
| 78 | 440 | `fader2.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 79 | 465 | `reserved_after_fader2` | reserved (write 00) |
| 80 | 466 | `fader3.cc` | 0..127 |
| 81 | 467 | `fader3.min` | 0..127 |
| 82 | 468 | `fader3.max` | 0..127 |
| 83 | 469 | `fader3.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 84 | 494 | `reserved_after_fader3` | reserved (write 00) |
| 85 | 495 | `fader4.cc` | 0..127 |
| 86 | 496 | `fader4.min` | 0..127 |
| 87 | 497 | `fader4.max` | 0..127 |
| 88 | 498 | `fader4.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 89 | 523 | `reserved_after_fader4` | reserved (write 00) |
| 90 | 524 | `fader5.cc` | 0..127 |
| 91 | 525 | `fader5.min` | 0..127 |
| 92 | 526 | `fader5.max` | 0..127 |
| 93 | 527 | `fader5.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 94 | 552 | `reserved_after_fader5` | reserved (write 00) |
| 95 | 553 | `fader6.cc` | 0..127 |
| 96 | 554 | `fader6.min` | 0..127 |
| 97 | 555 | `fader6.max` | 0..127 |
| 98 | 556 | `fader6.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 99 | 581 | `reserved_after_fader6` | reserved (write 00) |
| 100 | 582 | `fader7.cc` | 0..127 |
| 101 | 583 | `fader7.min` | 0..127 |
| 102 | 584 | `fader7.max` | 0..127 |
| 103 | 585 | `fader7.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 104 | 610 | `reserved_after_fader7` | reserved (write 00) |
| 105 | 611 | `fader8.cc` | 0..127 |
| 106 | 612 | `fader8.min` | 0..127 |
| 107 | 613 | `fader8.max` | 0..127 |
| 108 | 614 | `fader8.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 109 | 639 | `pad1.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 110 | 640 | `pad1.value1` | 0..127 |
| 111 | 641 | `pad1.value2` | 0..127 |
| 112 | 642 | `pad1.value3` | 0..127 |
| 113 | 643 | `pad1.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 114 | 668 | `pad1.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 115 | 669 | `pad1.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 116 | 670 | `pad1.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 117 | 671 | `pad1.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 118 | 696 | `pad2.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 119 | 697 | `pad2.value1` | 0..127 |
| 120 | 698 | `pad2.value2` | 0..127 |
| 121 | 699 | `pad2.value3` | 0..127 |
| 122 | 700 | `pad2.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 123 | 725 | `pad2.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 124 | 726 | `pad2.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 125 | 727 | `pad2.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 126 | 728 | `pad2.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 127 | 753 | `pad3.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 128 | 754 | `pad3.value1` | 0..127 |
| 129 | 755 | `pad3.value2` | 0..127 |
| 130 | 756 | `pad3.value3` | 0..127 |
| 131 | 757 | `pad3.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 132 | 782 | `pad3.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 133 | 783 | `pad3.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 134 | 784 | `pad3.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 135 | 785 | `pad3.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 136 | 810 | `pad4.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 137 | 811 | `pad4.value1` | 0..127 |
| 138 | 812 | `pad4.value2` | 0..127 |
| 139 | 813 | `pad4.value3` | 0..127 |
| 140 | 814 | `pad4.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 141 | 839 | `pad4.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 142 | 840 | `pad4.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 143 | 841 | `pad4.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 144 | 842 | `pad4.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 145 | 867 | `pad5.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 146 | 868 | `pad5.value1` | 0..127 |
| 147 | 869 | `pad5.value2` | 0..127 |
| 148 | 870 | `pad5.value3` | 0..127 |
| 149 | 871 | `pad5.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 150 | 896 | `pad5.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 151 | 897 | `pad5.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 152 | 898 | `pad5.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 153 | 899 | `pad5.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 154 | 924 | `pad6.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 155 | 925 | `pad6.value1` | 0..127 |
| 156 | 926 | `pad6.value2` | 0..127 |
| 157 | 927 | `pad6.value3` | 0..127 |
| 158 | 928 | `pad6.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 159 | 953 | `pad6.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 160 | 954 | `pad6.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 161 | 955 | `pad6.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 162 | 956 | `pad6.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 163 | 981 | `pad7.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 164 | 982 | `pad7.value1` | 0..127 |
| 165 | 983 | `pad7.value2` | 0..127 |
| 166 | 984 | `pad7.value3` | 0..127 |
| 167 | 985 | `pad7.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 168 | 1010 | `pad7.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 169 | 1011 | `pad7.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 170 | 1012 | `pad7.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 171 | 1013 | `pad7.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 172 | 1038 | `pad8.type` | enum: 0=Note, 1=CC Toggle, 2=CC Momentary, 3=Program Change, 4=Panic |
| 173 | 1039 | `pad8.value1` | 0..127 |
| 174 | 1040 | `pad8.value2` | 0..127 |
| 175 | 1041 | `pad8.value3` | 0..127 |
| 176 | 1042 | `pad8.channel` | enum: 16 values (0=Channel 1 .. 15=Channel 16) |
| 177 | 1067 | `pad8.color1` | enum: 14 values (0=LED Off .. 13=White) |
| 178 | 1068 | `pad8.color2` | enum: 14 values (0=LED Off .. 13=White) |
| 179 | 1069 | `pad8.color3` | enum: 14 values (0=LED Off .. 13=White) |
| 180 | 1070 | `pad8.color4` | enum: 14 values (0=LED Off .. 13=White) |
| 181 |  | `sysex_end` | `F7` |

### 4.1 Reserved bytes

Message offsets 42, 69, 74, 79, 84, 89, 94, 99, 104 are never shown by the editor. In all 26 presets read (25 slots plus the out-of-range reply) they are `00`. That is one device only, so a conforming reader must accept any value.
[M] The editor preserves them when it receives a preset from the device and sends it back, and the device stores and returns
them unchanged. A writer MUST preserve the values it read, and SHOULD write `00` when it has no value to preserve. Their purpose is [U].

### 4.2 Encodings

Unless stated otherwise a "byte" value shown below is the raw message byte. Values outside the listed domain are **not valid**:
the device stores and returns them unchanged [M] (see section 6), and the editor shows an unspecified fallback for them, so a
writer MUST NOT produce them.

**MIDI channel (every `*.channel` field)**

| byte | meaning |
|---|---|
| 0 | Channel 1 |
| 1 | Channel 2 |
| 2 | Channel 3 |
| 3 | Channel 4 |
| 4 | Channel 5 |
| 5 | Channel 6 |
| 6 | Channel 7 |
| 7 | Channel 8 |
| 8 | Channel 9 |
| 9 | Channel 10 |
| 10 | Channel 11 |
| 11 | Channel 12 |
| 12 | Channel 13 |
| 13 | Channel 14 |
| 14 | Channel 15 |
| 15 | Channel 16 |

**Pad type (`padN.type`)**

| byte | meaning |
|---|---|
| 0 | Note |
| 1 | CC Toggle |
| 2 | CC Momentary |
| 3 | Program Change |
| 4 | Panic |

**Pad colour (`padN.colorM`)**

| byte | meaning |
|---|---|
| 0 | LED Off |
| 1 | Chartreuse |
| 2 | Green |
| 3 | Aquamarine |
| 4 | Cyan |
| 5 | Azure |
| 6 | Blue |
| 7 | Violet |
| 8 | Magenta |
| 9 | Rose |
| 10 | Red |
| 11 | Orange |
| 12 | Yellow |
| 13 | White |

(Bytes 14 and 15 display as Green and Aquamarine and bytes above 15 repeat 0..13 in the editor: invalid, do not write.)

**Velocity curve (pad `value3` for Note pads; `split.curve`)**

| byte | meaning |
|---|---|
| 0 | Curve 1 |
| 1 | Curve 2 |
| 2 | Curve 3 |
| 3 | Curve 4 |
| 4 | Curve 5 |
| 5 | Curve 6 |
| 6 | Curve 7 |
| 7 | Curve 8 |

**Ribbon bank type, tilt type**

| byte | meaning |
|---|---|
| 0 | CC |
| 1 | Pitch Bend |

**`ribbon.default_bank`**

| byte | meaning |
|---|---|
| 0 | Bank 1 |
| 1 | Bank 2 |
| 2 | Bank 3 |

**`ribbon.release_mode`**

| byte | meaning |
|---|---|
| 0 | Return |
| 1 | Latch |

**`wheel.direction`**

| byte | meaning |
|---|---|
| 0 | Normal |
| 1 | Reverse |

**`pc.send_on_load`**

| byte | meaning |
|---|---|
| 0 | Yes |
| 1 | No |

**`split.mode`**

| byte | meaning |
|---|---|
| 0 | Split On |
| 1 | Split Off |

**`upper.midi_to_din`, `lower.midi_to_din`**

| byte | meaning |
|---|---|
| 0 | On |
| 1 | Off |

**Numbers.** `*.cc`, `*.min`, `*.max`, `pc.program/lsb/msb`, pad `value1..3` (except Note curve): byte = value, 0..127.
`*.transpose`: byte = semitones + 12, 0..24 (shown -12..+12). `split.key`: byte = key - 1, 0..35 (shown 1..36).

*Note for tool authors (non-normative).* Everything in this document is about **bytes**. Where the editor *displays*
a different number from the byte (channels, velocity curves, ribbon banks and `split.key` are shown as byte + 1;
transpose as byte - 12), a human-facing format should say clearly which of the two it uses, and enumerations list their
"yes" side first (`Yes`, `On`, `Split On` are byte `00`). The `vortex-cli` JSON format shows the editor's numbers; its
translation table is in `docs/preset-format.md`, "Numbers and the raw bytes".


Type-dependent pad values (pad *n*, bytes `value1..value3`):

| pad type | value1 | value2 | value3 |
|---|---|---|---|
| Note | note number 0..127 | velocity 0..127 (0 = use the velocity curve) | velocity curve, byte 0..7 = Curve 1..8 |
| CC Toggle | CC number | value sent when switched on | value sent when switched off |
| CC Momentary | CC number | value sent on press | value sent on release |
| Program Change | program number | bank LSB | bank MSB |
| Panic | not used | not used | not used |

[M] for the labels the editor shows for each type and for the byte positions; the behaviour of the *keytar's pads* for each type was
not measured on the hardware [U] (this specification describes the stored configuration only).

### 4.3 Name

[M] 16 bytes at message offsets 10..25, ASCII, shorter names padded with `00`. A 16-character name has no terminator. [D] Names should
be printable ASCII `20..7E`. The device itself stores any 7-bit bytes verbatim (section 6).

### 4.4 Field meanings (non-normative)

Restated in our own words from the vendor's user guide; useful for naming and help text, not needed to read or write the format.

| group | fields | meaning |
|---|---|---|
| Name | `name` | the preset's name, up to 16 characters |
| Program Change | `pc.send_on_load` | Yes: when this preset is loaded on the keytar it sends one combined Program Change plus Bank Select (MSB and LSB); No: it sends nothing |
| | `pc.program`, `pc.lsb`, `pc.msb` | the program number and bank bytes sent when *Send on load* is Yes |
| Split point | `split.mode` | Split On: the keybed is divided into a lower and an upper zone at the split key; Split Off: the keybed behaves as a single zone |
| | `split.key` | how many keys, counting from the lowest key, belong to the lower zone (1..36); keys above belong to the upper zone |
| | `split.curve` | the velocity curve applied to the keybed (Curve 1..8) |
| Zones | `lower.*`, `upper.*` | per zone: `channel` = MIDI channel; `transpose` = shift in semitones (-12..+12; 12 = one octave); `midi_to_din` = On: the zone's messages also go out of the DIN MIDI output, Off: USB only. Which zone's values apply when the split is Off is not stated by the vendor and was not measured [U] |
| Sustain | `sustain.channel` | MIDI channel of sustain pedal messages |
| Pitch wheel | `wheel.channel` | MIDI channel of the pitch wheel |
| | `wheel.direction` | Normal: turning the wheel to the right raises the pitch; Reverse: it lowers it |
| Volume slider (S1) | `volume.cc`, `.channel`, `.min`, `.max` | the slider sends controller `cc` on `channel`, scaled to the range `min`..`max` |
| Touch ribbon | `ribbon.default_bank` | which of the three banks is active when the preset is loaded |
| | `ribbon.release_mode` | Latch: nothing is sent when the finger lifts (suits modulation); Return: the controller's default message is sent on release (suits pitch bend) |
| | `ribbon.bankN.type` | CC or Pitch Bend |
| | `ribbon.bankN.cc`, `.channel`, `.min`, `.max` | controller number (used by type CC), channel, and the output range |
| Tilt (accelerometer) | `tilt.type`, `.cc`, `.channel`, `.min`, `.max` | as for a ribbon bank |
| Faders 1..8 | `faderN.cc`, `.channel`, `.min`, `.max` | controller number, channel, and the output range of each fader |
| Pads 1..8 | `padN.type` | Note: Note On when pressed, Note Off when released. CC Toggle: each press alternates between sending the *on* value and the *off* value. CC Momentary: sends the *press* value on press and the *release* value on release. Program Change: sends a Program Change (with bank LSB/MSB). Panic: sends all-notes-off |
| | `padN.value1..3`, `.channel` | per type, see the table in section 4.2; `channel` is the MIDI channel the pad sends on |
| | `padN.color1..4` | LED colours. Note pads: color1 = idle, color2 = struck with velocity 1..63, color3 = 64..95, color4 = 96..127. All other types use only color1 (off/released/idle) and color2 (on/pressed/active) |

## 5. Slots and default contents

### 5.1 Slots

[M] The device holds 25 presets, indexes 0..24 (the vendor editor offers "Preset 1".."Preset 25" = indexes 0..24). Get **and Set work for every one of
them**: a distinct marker written by SysEx to each of the 25 slots was read back exactly from every slot, with no slot aliasing another and
the out-of-range reply unaffected; and the vendor editor's Send to "Preset 25" (index 24) produced the expected message and changed only slot 24. A Get for an index of 25 or more returns a well-formed reply whose slot byte is `00`
(not the requested index), whose Program Change number is 0, and whose body is the default preset of section 5.2. [M] This also holds when slot 0 has been given other content, so the reply comes from a template in the firmware and not from slot 0.
A writer MUST NOT Set an index above 24 [U: effect untested].

### 5.2 Factory state

[M] After the vendor's factory reset (power the keytar off, hold the lowest C and the Gb key, switch it on; vendor support FAQ for the
Vortex Wireless 2) a read of every slot gave **one and the same preset in all 25 slots**. Slots differ only in the slot byte (message offset 9)
and the Program Change number (message offset 29), which equals the slot index (0..24); the out-of-range reply has both bytes 0. The name
is empty (16 bytes of `00`) and all reserved bytes are `00`. `spec/device_factory_defaults.json` holds the raw reads. The default preset, decoded
with section 4.2, next to the editor's own "new preset" state (section 5.3):

| field | device factory default | editor new-preset state |
|---|---|---|
| `name` | '' | 'PRESET' |
| `pc.send_on_load` | Yes | No |
| `pc.msb` | 0 | 0 |
| `pc.lsb` | 0 | 0 |
| `pc.program` | 6 (= slot index) | 0 |
| `split.curve` | Curve 5 | Curve 1 |
| `split.mode` | Split Off | Split Off |
| `split.key` | 19 | 1 |
| `upper.transpose` | 0 | 0 |
| `upper.midi_to_din` | On | On |
| `upper.channel` | Channel 2 | Channel 1 |
| `lower.transpose` | 0 | 0 |
| `lower.midi_to_din` | On | On |
| `lower.channel` | Channel 1 | Channel 2 |
| `sustain.channel` | Channel 1 | Channel 1 |
| `wheel.channel` | Channel 1 | Channel 1 |
| `wheel.direction` | Normal | Normal |
| `volume.cc` | 7 | 1 |
| `volume.min` | 0 | 0 |
| `volume.max` | 127 | 127 |
| `volume.channel` | Channel 1 | Channel 1 |
| `ribbon.default_bank` | Bank 1 | Bank 1 |
| `ribbon.release_mode` | Latch | Return |
| `ribbon.bank1.type` | CC | CC |
| `ribbon.bank1.cc` | 1 | 100 |
| `ribbon.bank1.min` | 0 | 0 |
| `ribbon.bank1.max` | 127 | 127 |
| `ribbon.bank1.channel` | Channel 1 | Channel 1 |
| `ribbon.bank2.type` | Pitch Bend | CC |
| `ribbon.bank2.cc` | 0 | 101 |
| `ribbon.bank2.min` | 0 | 0 |
| `ribbon.bank2.max` | 127 | 127 |
| `ribbon.bank2.channel` | Channel 1 | Channel 1 |
| `ribbon.bank3.type` | CC | CC |
| `ribbon.bank3.cc` | 22 | 102 |
| `ribbon.bank3.min` | 0 | 0 |
| `ribbon.bank3.max` | 127 | 127 |
| `ribbon.bank3.channel` | Channel 1 | Channel 1 |
| `tilt.type` | CC | CC |
| `tilt.cc` | 1 | 91 |
| `tilt.min` | 0 | 0 |
| `tilt.max` | 127 | 127 |
| `tilt.channel` | Channel 1 | Channel 1 |
| `fader1.cc` | 14 | 36 |
| `fader1.min` | 0 | 0 |
| `fader1.max` | 127 | 127 |
| `fader1.channel` | Channel 1 | Channel 1 |
| `fader2.cc` | 15 | 37 |
| `fader2.min` | 0 | 0 |
| `fader2.max` | 127 | 127 |
| `fader2.channel` | Channel 1 | Channel 1 |
| `fader3.cc` | 16 | 38 |
| `fader3.min` | 0 | 0 |
| `fader3.max` | 127 | 127 |
| `fader3.channel` | Channel 1 | Channel 1 |
| `fader4.cc` | 17 | 39 |
| `fader4.min` | 0 | 0 |
| `fader4.max` | 127 | 127 |
| `fader4.channel` | Channel 1 | Channel 1 |
| `fader5.cc` | 18 | 40 |
| `fader5.min` | 0 | 0 |
| `fader5.max` | 127 | 127 |
| `fader5.channel` | Channel 1 | Channel 1 |
| `fader6.cc` | 19 | 41 |
| `fader6.min` | 0 | 0 |
| `fader6.max` | 127 | 127 |
| `fader6.channel` | Channel 1 | Channel 1 |
| `fader7.cc` | 20 | 42 |
| `fader7.min` | 0 | 0 |
| `fader7.max` | 127 | 127 |
| `fader7.channel` | Channel 1 | Channel 1 |
| `fader8.cc` | 21 | 43 |
| `fader8.min` | 0 | 0 |
| `fader8.max` | 127 | 127 |
| `fader8.channel` | Channel 1 | Channel 1 |
| `pad1.type` | Note | Note |
| `pad1.value1` | 36 | 48 |
| `pad1.value2` | 0 | 0 |
| `pad1.value3` | 0 | 0 |
| `pad1.channel` | Channel 10 | Channel 1 |
| `pad1.color1` | Blue | LED Off |
| `pad1.color2` | Green | Chartreuse |
| `pad1.color3` | Yellow | Green |
| `pad1.color4` | Red | Aquamarine |
| `pad2.type` | Note | Note |
| `pad2.value1` | 37 | 49 |
| `pad2.value2` | 0 | 0 |
| `pad2.value3` | 0 | 0 |
| `pad2.channel` | Channel 10 | Channel 1 |
| `pad2.color1` | Blue | LED Off |
| `pad2.color2` | Green | Chartreuse |
| `pad2.color3` | Yellow | Green |
| `pad2.color4` | Red | Aquamarine |
| `pad3.type` | Note | Note |
| `pad3.value1` | 38 | 50 |
| `pad3.value2` | 0 | 0 |
| `pad3.value3` | 0 | 0 |
| `pad3.channel` | Channel 10 | Channel 1 |
| `pad3.color1` | Blue | LED Off |
| `pad3.color2` | Green | Chartreuse |
| `pad3.color3` | Yellow | Green |
| `pad3.color4` | Red | Aquamarine |
| `pad4.type` | Note | Note |
| `pad4.value1` | 39 | 51 |
| `pad4.value2` | 0 | 0 |
| `pad4.value3` | 0 | 0 |
| `pad4.channel` | Channel 10 | Channel 1 |
| `pad4.color1` | Blue | LED Off |
| `pad4.color2` | Green | Chartreuse |
| `pad4.color3` | Yellow | Green |
| `pad4.color4` | Red | Aquamarine |
| `pad5.type` | Note | Note |
| `pad5.value1` | 40 | 52 |
| `pad5.value2` | 0 | 0 |
| `pad5.value3` | 0 | 0 |
| `pad5.channel` | Channel 10 | Channel 1 |
| `pad5.color1` | Blue | LED Off |
| `pad5.color2` | Green | Chartreuse |
| `pad5.color3` | Yellow | Green |
| `pad5.color4` | Red | Aquamarine |
| `pad6.type` | Note | Note |
| `pad6.value1` | 41 | 53 |
| `pad6.value2` | 0 | 0 |
| `pad6.value3` | 0 | 0 |
| `pad6.channel` | Channel 10 | Channel 1 |
| `pad6.color1` | Blue | LED Off |
| `pad6.color2` | Green | Chartreuse |
| `pad6.color3` | Yellow | Green |
| `pad6.color4` | Red | Aquamarine |
| `pad7.type` | Note | Note |
| `pad7.value1` | 42 | 54 |
| `pad7.value2` | 0 | 0 |
| `pad7.value3` | 0 | 0 |
| `pad7.channel` | Channel 10 | Channel 1 |
| `pad7.color1` | Blue | LED Off |
| `pad7.color2` | Green | Chartreuse |
| `pad7.color3` | Yellow | Green |
| `pad7.color4` | Red | Aquamarine |
| `pad8.type` | Note | Note |
| `pad8.value1` | 43 | 55 |
| `pad8.value2` | 0 | 0 |
| `pad8.value3` | 0 | 0 |
| `pad8.channel` | Channel 10 | Channel 1 |
| `pad8.color1` | Blue | LED Off |
| `pad8.color2` | Green | Chartreuse |
| `pad8.color3` | Yellow | Green |
| `pad8.color4` | Red | Aquamarine |

Default preset body as read from slot 6 (message offsets 9..180, spaces between bytes):

```
06 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 06 04 01 12 0c 00 01 0c 00 00 00 00 00 00 07 00 7f 00 00 01 00 01 00 7f 00 01 00 00 7f 00 00 16 00 7f 00 00 01 00 7f 00 00 0e 00 7f 00 00 0f 00 7f 00 00 10 00 7f 00 00 11 00 7f 00 00 12 00 7f 00 00 13 00 7f 00 00 14 00 7f 00 00 15 00 7f 00 00 24 00 00 09 06 02 0c 0a 00 25 00 00 09 06 02 0c 0a 00 26 00 00 09 06 02 0c 0a 00 27 00 00 09 06 02 0c 0a 00 28 00 00 09 06 02 0c 0a 00 29 00 00 09 06 02 0c 0a 00 2a 00 00 09 06 02 0c 0a 00 2b 00 00 09 06 02 0c 0a
```

### 5.3 The editor's "new preset" state

[M] A freshly started vendor editor (nothing loaded) holds the preset shown in the right-hand column of the table above, which differs
from the device's factory state (for instance the name `PRESET`, pad notes 48..55, fader controllers 36..43). This is the editor's own
template, not device state; it is listed because tools are easily confused between the two.

## 6. Device behaviour on unusual input

Measured by sending the following to the device (each from a known state, waiting 3 s, then reading back slot 0 with a well-formed Get):

- Set: control: well-formed: applied
- Set: length field=0, body intact: applied
- Set: length field=1, body intact: applied
- Set: length field=127, body intact: applied
- Set: length field=171, body intact: applied
- Set: length field=173, body intact: applied
- Set: length field=16383, body intact: applied
- Set: body 1 byte short, length field intact: NOT applied
- Set: body 1 byte short, length field=171: NOT applied
- Set: 1 extra trailing byte, length intact: NOT applied
- Set with slot byte = 3 (messages otherwise well-formed): slot 3 changed, slot 0 did not
- Get with device byte 52->53: no reply
- Get with model byte 5e->5f: no reply
- Get with manufacturer 0e->0f: no reply

Conclusions **[M]** (each from the trials above or from the first, equivalent run of the same probe):

1. **Message size matters; the length field does not.** A Set whose total size is exactly 182 bytes is applied whatever the two length
	bytes contain (tested: 0, 1, 127, 171, 173, 16383). A Set that is one byte short, or has one extra byte, is ignored, even when its
	length field is adjusted to the true length (171). A writer MUST still write the correct length (172), and a reader SHOULD check it.
2. **The three identification fields must match exactly.** A Get whose device byte is `53` instead of `52`, whose model byte is `5F`
	instead of `5E`, or whose manufacturer byte is `0F` instead of `0E`, receives no reply.
3. **Which slot a Set writes** is determined by the slot byte in the body (message offset 9); a Set with slot byte 3 changed slot 3.
4. **A Get must be exactly 11 bytes.** A Get with length field 0, with length field 2, or with one extra trailing byte receives no reply.
5. **No validation of values.** Writing the byte `7F` into a channel, pad type, pad colour, pad curve, split curve, transpose, split key,
	ribbon type or send-on-load field was stored and returned unchanged. The device will therefore never protect you from an invalid
	preset; the writer must validate against section 4.2.
6. **Names are stored verbatim.** A 16-character name with no terminator was stored and returned in full; a name containing the bytes
	`7F 01 1F 20 41 00 42` was returned unchanged (the device does not truncate at `00` or sanitise control characters).
7. **Slot indexes 25..127**: a Get returns a well-formed reply with slot byte `00`, Program Change number `00` and the default
	the default preset of section 5.2 (a firmware template, not slot 0's content).
8. Messages that the device ignores produce **no error response**: silence is the only signal.


## 7. The `.vw2` file

[M] A `.vw2` file written by the vendor editor 1.0.3 is exactly **1071 bytes** and has no checksum: 21 presets (including random
ones) saved by the editor differ *only* at the 171 value positions below; the other 900 bytes are identical in every file. [M]
Every value byte equals the corresponding SysEx message byte (no transformation, no re-encoding): all 171 relations were identity
over 21 presets. The file contains no slot number and no command.

Layout:

- File offsets `0..35`: constant prefix. Then the 171 value bytes are interleaved with constant 24-byte record headers:

| file offsets | hold message offsets | bytes |
|---|---|---|
| 36..51 | 10..25 | 16 |
| 76..79 | 26..29 | 4 |
| 104..106 | 30..32 | 3 |
| 131..133 | 33..35 | 3 |
| 158..160 | 36..38 | 3 |
| 185..185 | 39..39 | 1 |
| 210..211 | 40..41 | 2 |
| 236..240 | 42..46 | 5 |
| 265..266 | 47..48 | 2 |
| 291..295 | 49..53 | 5 |
| 320..324 | 54..58 | 5 |
| 349..353 | 59..63 | 5 |
| 378..382 | 64..68 | 5 |
| 407..411 | 69..73 | 5 |
| 436..440 | 74..78 | 5 |
| 465..469 | 79..83 | 5 |
| 494..498 | 84..88 | 5 |
| 523..527 | 89..93 | 5 |
| 552..556 | 94..98 | 5 |
| 581..585 | 99..103 | 5 |
| 610..614 | 104..108 | 5 |
| 639..643 | 109..113 | 5 |
| 668..671 | 114..117 | 4 |
| 696..700 | 118..122 | 5 |
| 725..728 | 123..126 | 4 |
| 753..757 | 127..131 | 5 |
| 782..785 | 132..135 | 4 |
| 810..814 | 136..140 | 5 |
| 839..842 | 141..144 | 4 |
| 867..871 | 145..149 | 5 |
| 896..899 | 150..153 | 4 |
| 924..928 | 154..158 | 5 |
| 953..956 | 159..162 | 4 |
| 981..985 | 163..167 | 5 |
| 1010..1013 | 168..171 | 4 |
| 1038..1042 | 172..176 | 5 |
| 1067..1070 | 177..180 | 4 |

The constant bytes are given in `spec/vw2_template.hex` (value positions are zero in that file). For information, the constant part
is a serialisation of 36 parameter records, each introduced by a 24-byte header of six little-endian 32-bit integers
`[S, 0, i, S-12, 1, 14]` where *i* counts 1..36 and *S* varies per record:

| header at file offset | S | i |
|---|---|---|
| 52 | 28 | 1 |
| 80 | 27 | 2 |
| 107 | 27 | 3 |
| 134 | 27 | 4 |
| 161 | 25 | 5 |
| 186 | 26 | 6 |
| 212 | 29 | 7 |
| 241 | 26 | 8 |
| 267 | 29 | 9 |
| 296 | 29 | 10 |
| 325 | 29 | 11 |
| 354 | 29 | 12 |
| 383 | 29 | 13 |
| 412 | 29 | 14 |
| 441 | 29 | 15 |
| 470 | 29 | 16 |
| 499 | 29 | 17 |
| 528 | 29 | 18 |
| 557 | 29 | 19 |
| 586 | 29 | 20 |
| 615 | 29 | 21 |
| 644 | 28 | 22 |
| 672 | 29 | 23 |
| 701 | 28 | 24 |
| 729 | 29 | 25 |
| 758 | 28 | 26 |
| 786 | 29 | 27 |
| 815 | 28 | 28 |
| 843 | 29 | 29 |
| 872 | 28 | 30 |
| 900 | 29 | 31 |
| 929 | 28 | 32 |
| 957 | 29 | 33 |
| 986 | 28 | 34 |
| 1014 | 29 | 35 |
| 1043 | 28 | 36 |

The meaning of *S* and of the prefix integers is [U]; a writer SHOULD copy the template verbatim.

### 7.1 Reading and writing

- A writer MUST emit the template with the 171 value bytes inserted at the file offsets in `spec/layout.json`. [M]
- Strictness of the vendor editor when loading files (measured by deliberately damaging files): 

| damaged file loaded into the editor | value bytes taken from the file | left as before | set to 0 | error dialog |
|---|---|---|---|---|
| valid file | 145 | 0 | 0 | no |
| size 1070 (last value byte dropped) | 144 | 0 | 1 | no |
| size 1072 (extra 00 appended) | 145 | 0 | 0 | yes |
| size 1100 (29 extra bytes) | 145 | 0 | 0 | yes |
| size 500 (truncated) | 57 | 88 | 0 | no |
| prefix byte 0: 01 -> 02 | 0 | 145 | 0 | yes |
| first record header size byte [52]: 1c -> 1d | 7 | 138 | 0 | yes |
| first record header index byte [60]: 01 -> 09 | 141 | 4 | 0 | no |
| first record header tail byte [74]: 0e -> 0f | 3 | 142 | 0 | yes |
| pad1.type value = 127 (out of range) | all (the out-of-range 127 is stored as is) | 0 | 0 | no |
| all constant bytes zeroed | 0 | 145 | 0 | yes |

(Of the 171 value bytes, 26 were identical in both files and could not be attributed, so each row accounts for 145.)

How the table was made: each damaged file was loaded into the editor right after a *control* file whose values differ from the
damaged file's almost everywhere; the editor's state was then saved and every value byte was attributed to the damaged file, the
control, or zero. "Error dialog" means a message box titled `Preset File Load` reading "Preset file is not compatible with this version
of the preset editor".

Conclusions **[M]**:

1. **The editor applies the file as it reads it and stops at the first problem.** It is not transactional: a bad file can leave the
	editor *partially* loaded (earlier records applied, later ones untouched) while showing an error.
2. **Prefix check.** Changing the first byte of the file (`01` to `02`), or zeroing all constant bytes, applies nothing at all and shows
	the error.
3. **Record-header checks.** Changing the size byte of the first record header applies only what precedes that header (the name) and
	shows the error. Changing the last integer of a header (`0E` to `0F`) applies everything before that record, none of that record or
	later ones, and shows the error. Changing a record's *index* byte (`01` to `09`) shows no error: that one record's values are
	skipped and every other record is applied, so records are identified by their index, not by position.
4. **File size.** Trailing extra bytes (1 or 29) are tolerated but trigger the error after all values were applied. A file *shorter*
	than 1071 bytes raises **no error**: records fully inside the file are applied and the rest are left untouched; a file one byte short
	applies everything except the final value byte, which becomes 0.
5. **No range checking.** An out-of-range value (`pad1.type = 127`) loads and saves back unchanged.

Consequences for implementers: a **writer** MUST produce exactly 1071 bytes with the exact template constants (anything else may load
partially in the vendor editor). A **reader** SHOULD be strict (reject any file that is not exactly 1071 bytes with constants equal to
the template) rather than imitate the vendor editor's partial loading, and SHOULD range-check values itself (section 4.2).


## 8. Conversion

**SysEx message to `.vw2`** (a Reply or a Set; the command and slot are discarded):

```
file = copy of the 1071-byte template
for each row of layout.json with a vw2_offset:
    file[vw2_offset] = message[msg_offset]
```

**`.vw2` to SysEx Set** for a chosen destination slot (0..24):

```
msg = F0 00 00 0E 52 5E 01 01 2C <slot>  (182 bytes total)
for each row of layout.json with a vw2_offset:
    msg[msg_offset] = file[vw2_offset]
msg[181] = F7
```

[M] Both directions reproduce the vendor editor's output byte for byte for all vectors in `spec/vectors.json`; additionally,
files generated from this specification were loaded into the vendor editor, which sent the expected SysEx to the device for 6 of 6 fresh random presets (not used to derive this specification): the editor sent exactly one message, byte-identical to the original preset, and the device's read-back of the destination slot was identical too.

### 8.1 Recommended host procedures (non-normative)

The device never acknowledges anything, so reliability comes from verifying by reading back.

- **Read slot *n*** (0..24): open the port pair and discard pending input; send Get(*n*); wait up to 1.5 s for one SysEx; accept it only if
	the strict reader of section 9 passes, the command is `03`, and the slot byte equals *n*. On silence, wait 0.5 s and retry (3 attempts),
	then report failure: silence is the only error signal.
- **Write slot *n***: validate every field against section 4.2; build the 182-byte Set with the correct length bytes; send it **once**; wait at
	least 1.5 s (messages sent while the device is busy are dropped); read the slot back and compare all 171 preset bytes; there is no other
	confirmation. On mismatch, retry the write once after a further delay, then fail.
- **Several slots**: strictly one at a time, at least 1.5 s between Sets; do not pipeline.
- **Back up first**: read all 25 slots and keep the raw replies before overwriting anything; restoring is a Set of each reply.
- **Preserve what you do not understand**: to change a preset, start from the bytes just read and modify only the fields you mean to, so
	reserved bytes are carried through unchanged.
- **Never write to a slot above 24** (effect untested).
- **Names**: the device keeps whatever 7-bit bytes you send, but the vendor editor's treatment of non-printable or non-ASCII names was not
	measured, so write printable ASCII `20..7E` only.

### 8.2 Wireless-receiver pairing (non-normative)

The editor's pairing dialog takes a six-digit dongle ID and sends one SysEx message on the same port pair. Captured at the OS MIDI API
([M], two captures with different IDs; the device sent no reply in either):

```
F0 00 20 2B 68 3C 00 | d1 d2 d3 d4 d5 d6 | 30 30 30 30 30 30 30 30 30 30 30 30 30 | F7
```

- The manufacturer bytes `00 20 2B` differ from the `00 00 0E` used by the preset messages (section 3).
- `d1..d6` are the ID digits as ASCII (`0x30`..`0x39`). Only these six bytes differed between the captures.
- The thirteen trailing `30` bytes were identical in both captures [U: padding or an unused field].
- [D] Sending it replaces the current pairing. The device sends no reply to it.
- [M] A message built from this layout and sent by a host other than the editor was confirmed with a MIDI monitor.

## 9. Conformance

An implementation conforms if it passes all of the following, using only this document and the files in `spec/`. A reference check built
from nothing but those files (no vendor software, no other code) passes every item.

1. **Conversion** (`vectors.json`, `vectors`): for every vector, SysEx-to-`.vw2` yields exactly `vw2_hex`, and `.vw2`-to-SysEx with the
	vector's slot byte and command yields exactly `sysex_hex`. (22 vectors: 21 random presets and the factory default.)
2. **Rejection** (`vectors.json`, `negative`): the strict `.vw2` reader rejects every `vw2` item (wrong size, altered prefix or record
	header, zeroed constants) and the strict SysEx reader rejects every `sysex` item (wrong size, wrong manufacturer/device/model byte,
	missing `F7`, wrong command, slot above 24, a data byte with the high bit set). The strict SysEx reader checks: size 182; `F0`, `00 00 0E 52 5E`,
	`F7` present; command `01` or `03`; length field 172; slot 0..24; all data bytes below `80`. (15 items.)
3. **Decoding** (`field_vectors.json`): decoding each message with the encodings of `layout.json` / section 4.2 yields the listed named
	values for all 148 fields (the name as text, enumerations as their names, numbers with their display offset). (22 messages.)
4. **Defaults** (`device_factory_defaults.json`): every slot body converts to a `.vw2` and back unchanged, and decodes to the table of section 5.2.

## 10. Evidence and open questions

| claim | how established |
|---|---|
| framing, commands, length field | 26 device replies; the editor's Get and Send messages captured at the OS MIDI API; length field matched in all 26 |
| every byte position in section 4 | 8-round group test flipping bit 0 of subsets of bytes with a verification round (130 of 134 predicted, 0 unexpected; remaining 4 resolved by single-byte tests) |
| value encodings in section 4.2 | writing known values to the device, retrieving them in the editor and reading what it displayed (several instances per round) |
| `.vw2` layout and identity relation | same group test but diffing saved files: each round changed exactly as many file bytes as were flipped; verification round 0 missing / 0 unexpected |
| reserved bytes preserved | set non-zero, retrieved, sent, read back |
| every slot 0..24 writable, no aliasing | marker written to each slot, all read back; editor Send to index 24 |
| device edge behaviour (section 6) | experiments described there |

Open questions [U] (an implementation must not rely on any of these):

- the meaning of `52` and `5E` in the header, and whether other products share the framing;
- the purpose of the reserved bytes (message offsets 42, 69, 74, 79, 84, 89, 94, 99, 104);
- the meaning of the 24-byte record headers inside the `.vw2` and of its prefix;
- the behaviour of the physical controls for each pad type, and which zone applies when the split is Off;
- the effect of a Set to an index above 24;
- whether a Set to the slot that is currently active on the keytar takes effect immediately or only when that preset is next selected, and
	whether the device accepts a Set while it is being played;
- whether the device answers a Universal Device Inquiry;
- port naming and sharing behaviour on hosts other than Windows;
- how the vendor editor limits name entry (length and characters);
- behaviour on firmware or editor versions other than those measured (the firmware version was not recorded);
- whether the pairing message (section 8.2) takes effect on every firmware version, and what the thirteen trailing `0` bytes mean (they were
	identical in both captures).

## Appendix A. Data file formats

- **`layout.json`**: `{ "message_length": 182, "body_length": 172, "vw2_size": 1071, "fields": [ ... ] }`. Each field is one **message byte**,
	in message-offset order, with: `msg_offset` (0..181); `name`; `role` (`constant` with `value`; `command` with `values`; `length`; `slot`
	with `range`; `name` (one character of the name); `reserved`; `parameter`); `vw2_offset` (file offset of the same byte, or `null`/absent
	if it is not stored in the file); and for parameters `encoding`: `{"type":"enum","values":[names in byte order]}` or
	`{"type":"int","byte_min":..,"byte_max":..,"display_offset":..}` (displayed value = byte + display_offset).
- **`vw2_template.hex`**: 1071 bytes as hexadecimal pairs separated by spaces; all value positions are `00`.
- **`vectors.json`**: `{ "note", "vectors": [ {"name","sysex_hex","vw2_hex"} ], "negative": { "vw2": [ {"why","hex"} ], "sysex": [ {"why","hex"} ] } }`;
	hex strings are space-separated bytes; `sysex_hex` includes `F0` and `F7`.
- **`field_vectors.json`**: `{ "note", "vectors": [ {"name","sysex_hex","fields": {field name: displayed value}} ] }`, including `slot` and `name`.
- **`device_factory_defaults.json`**: `{ "note", "taken", "slots": { "0".."25": hex } }`; each value is the message **without** `F0` and `F7`
	(it starts `00 00 0E 52 5E 03 01 2C`); key `25` is the reply to an out-of-range Get.
