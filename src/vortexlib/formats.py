"""Bytes-in / bytes-out conversion between the three preset file formats.

    json  human-editable document (partial or complete; see document.py)
    vw2   the vendor editor's 1071-byte file
    syx   one SysEx Set message (182 bytes), ready to send to the keytar

Nothing here touches files, ports or the clock; callers supply bytes.
Slots are 1-based everywhere in this API (the editor's "Preset 1".."Preset 25").
"""

from __future__ import annotations

from dataclasses import dataclass

from . import codec
from . import fields as F
from .codec import FormatError
from .document import DocError, apply_doc, dump_json, parse_json, preset_to_doc
from .preset import Preset, factory

FORMATS = ("json", "vw2", "syx")


class SlotRequired(ValueError):
	"""An output needs a slot and neither the input nor the caller provided one."""


@dataclass
class Loaded:
	"""A parsed input.  Exactly one of ``preset`` (a complete preset) or ``doc`` (a possibly partial
	JSON document) is set."""

	fmt: str
	slot: int | None = None
	preset: Preset | None = None
	doc: dict | None = None

	@property
	def complete(self) -> bool:
		return self.preset is not None


def detect(data: bytes) -> str:
	"""Guess the format of ``data`` by content."""
	if data[:1] == b"\xf0":
		return "syx"
	if len(data) == codec.VW2_SIZE:
		return "vw2"
	stripped = data.lstrip(b"\xef\xbb\xbf \t\r\n")
	if stripped[:1] == b"{":
		return "json"
	raise FormatError("cannot recognise the data as a JSON, .vw2 or .syx preset")


def load(data: bytes, fmt: str | None = None) -> Loaded:
	"""Parse ``data`` (format guessed from content if ``fmt`` is None).  Binary formats are read strictly."""
	fmt = fmt or detect(data)
	if fmt == "vw2":
		return Loaded("vw2", preset=codec.from_vw2(data))
	if fmt == "syx":
		msgs = codec.split_sysex(data)
		if len(msgs) != 1:
			raise FormatError(f"expected exactly one SysEx message, found {len(msgs)}")
		_, slot, preset = codec.parse_message(msgs[0])
		return Loaded("syx", slot=slot + 1, preset=preset)
	if fmt == "json":
		doc = parse_json(data)
		_, slot = apply_doc(factory(), doc)  # validates the document completely
		return Loaded("json", slot=slot, doc=doc)
	raise ValueError(f"unknown format {fmt!r}; expected one of {FORMATS}")


def resolve(loaded: Loaded, base: Preset) -> Preset:
	"""The complete preset described by ``loaded``.

	A complete input (``vw2``/``syx``) is returned as is.  A JSON document is applied onto ``base``:
	fields it omits keep the value they have in ``base``.  Choose ``base`` as the factory defaults
	when the result goes to a file, or the keytar's current contents when it goes to the keytar.
	"""
	if loaded.preset is not None:
		return loaded.preset.copy()
	return apply_doc(base, loaded.doc)[0]


def dump(
	preset: Preset, fmt: str, slot: int | None = None, reference: Preset | None = None
) -> bytes:
	"""Serialise ``preset``.  ``slot`` (1-based) is required for ``syx`` and recorded in ``json`` if given.
	``reference`` (json only) makes the document contain only fields that differ from it."""
	if fmt == "vw2":
		return codec.to_vw2(preset)
	if fmt == "syx":
		if slot is None:
			raise SlotRequired("a .syx message needs a slot")
		return codec.build_message(codec.CMD_SET, check_slot(slot) - 1, preset)
	if fmt == "json":
		return dump_json(preset_to_doc(preset, slot, reference)).encode("utf-8")
	raise ValueError(f"unknown format {fmt!r}; expected one of {FORMATS}")


def check_slot(slot: int) -> int:
	if (
		isinstance(slot, bool)
		or not isinstance(slot, int)
		or not 1 <= slot <= F.SLOT_COUNT
	):
		raise ValueError(f"slot must be an integer 1..{F.SLOT_COUNT}, got {slot!r}")
	return slot


__all__ = [
	"FORMATS",
	"Loaded",
	"SlotRequired",
	"FormatError",
	"DocError",
	"detect",
	"load",
	"resolve",
	"dump",
	"check_slot",
]
