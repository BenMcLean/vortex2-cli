"""vortexlib: Alesis Vortex Wireless 2 preset library.

Pure library: bytes and dicts in, bytes and dicts out.  It never opens files or MIDI ports
and never prints; see ``vortex_cli`` for the file / MIDI / command-line wrapper.

Typical use::

    import vortexlib as vl
    loaded = vl.load(json_bytes)                       # parse + validate any supported format
    preset = vl.resolve(loaded, vl.factory(slot=3))    # fill unspecified fields from a base
    syx = vl.dump(preset, "syx", slot=3)               # bytes ready to send to the keytar

Slots are 1-based (the editor's "Preset 1".."Preset 25").
"""

from .codec import FormatError
from .device import DeviceError, Keytar, SimKeytar, Timing, Transport
from .document import (
	DocError,
	apply_doc,
	diff_presets,
	dump_json,
	flatten,
	parse_json,
	preset_to_doc,
)
from .formats import (
	FORMATS,
	Loaded,
	SlotRequired,
	check_slot,
	detect,
	dump,
	load,
	resolve,
)
from .preset import Preset, factory
from .reference import field_rows, json_schema

SLOT_COUNT = 25

__all__ = [
	"DeviceError",
	"DocError",
	"FORMATS",
	"FormatError",
	"Keytar",
	"Loaded",
	"Preset",
	"SLOT_COUNT",
	"SimKeytar",
	"SlotRequired",
	"Timing",
	"Transport",
	"apply_doc",
	"check_slot",
	"detect",
	"diff_presets",
	"dump",
	"dump_json",
	"factory",
	"field_rows",
	"flatten",
	"json_schema",
	"load",
	"parse_json",
	"preset_to_doc",
	"resolve",
]
