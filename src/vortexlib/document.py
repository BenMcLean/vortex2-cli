"""The human-editable JSON document <-> Preset.

A document is a flat description of one preset: an optional ``slot`` (1..25)
and any subset of the controls.  Applying a document to a *base* preset
changes only the fields it mentions (see ``apply_doc``).  The format is
specified in ``docs/preset-format.md``.
"""

from __future__ import annotations

import difflib
import json
from typing import Any

from . import fields as F
from .preset import Preset, factory


class DocError(ValueError):
	"""The document is invalid.  ``errors`` lists every problem found, each prefixed by its JSON path."""

	def __init__(self, errors: list[str]):
		super().__init__("; ".join(errors))
		self.errors = errors


# -- tree of non-pad parameters ---------------------------------------------------


def _is_pad(top: str) -> bool:
	return top.startswith("pad") and top[3:].isdigit()


def _build_tree() -> dict:
	tree: dict = {}
	for p in F.PARAMS:
		if _is_pad(p.path[0]):
			continue
		node = tree
		for k in p.path[:-1]:
			node = node.setdefault(k, {})
		node[p.path[-1]] = p
	return tree


_TREE = _build_tree()
PAD_FIXED = ("type", "channel", "color1", "color2", "color3", "color4")
TOP_KEYS = ("$schema", "description", "slot", "name", *F.TOP_ORDER)


def _suggest(key: str, allowed) -> str:
	m = difflib.get_close_matches(key, list(allowed), n=1)
	return f" (did you mean '{m[0]}'?)" if m else ""


# -- Preset -> document -------------------------------------------------------------


def preset_to_doc(
	preset: Preset, slot: int | None = None, reference: Preset | None = None
) -> dict:
	"""Describe ``preset`` as a document.

	With ``reference`` given, only fields that differ from it are included
	(a minimal patch).  ``slot`` is the 1-based slot to record, if known.
	"""
	doc: dict[str, Any] = {}
	if slot is not None:
		doc["slot"] = slot
	if reference is None or preset.name != reference.name:
		doc["name"] = preset.name

	def differs(p: F.Param) -> bool:
		return reference is None or preset.body[p.index] != reference.body[p.index]

	for top in F.TOP_ORDER:
		if _is_pad(top):
			pad = _pad_doc(preset, int(top[3:]), reference)
			if pad:
				doc[top] = pad
			continue
		for p in F.PARAMS:
			if p.path[0] != top or not differs(p):
				continue
			if p.kind == "raw" and reference is None and preset.body[p.index] == 0:
				continue
			node = doc
			for k in p.path[:-1]:
				node = node.setdefault(k, {})
			node[p.path[-1]] = p.to_json(preset.body[p.index])
	return doc


def _pad_doc(preset: Preset, n: int, ref: Preset | None) -> dict:
	top = f"pad{n}"
	tparam = F.BY_PATH[(top, "type")]
	type_changed = ref is None or preset.body[tparam.index] != ref.body[tparam.index]
	out: dict[str, Any] = {}
	if type_changed:
		out["type"] = tparam.to_json(preset.body[tparam.index])
	ptype = preset.pad_type(n)
	if ptype is not None:
		for key in F.pad_param_keys(ptype):
			sp = F.pad_param(n, ptype, key)
			if (
				type_changed
				or ref is None
				or preset.body[sp.index] != ref.body[sp.index]
			):
				out[key] = sp.to_json(preset.body[sp.index])
	for key in PAD_FIXED[1:]:
		p = F.BY_PATH[(top, key)]
		if ref is None or preset.body[p.index] != ref.body[p.index]:
			out[key] = p.to_json(preset.body[p.index])
	return out


# -- document -> Preset ---------------------------------------------------------------


def apply_doc(base: Preset, doc: Any) -> tuple[Preset, int | None]:
	"""Apply ``doc`` on top of ``base``; return (new preset, slot named by the document or None).

	Only fields present in the document change.  If a pad's ``type`` is given
	and differs from the base's, that pad's three type-dependent value bytes
	are reset to 0 first (so a Note number never silently becomes a CC number);
	values the document gives are applied afterwards.  Raises DocError listing
	every problem; ``base`` is never modified.
	"""
	if not isinstance(doc, dict):
		raise DocError(["(top level): expected a JSON object"])
	errors: list[str] = []
	assigns: list[tuple[int, int]] = []
	slot: int | None = None
	name: str | None = None

	for key in doc:
		if key not in TOP_KEYS:
			errors.append(f"{key}: unknown key{_suggest(key, TOP_KEYS)}")

	if "description" in doc and not isinstance(doc["description"], str):
		errors.append("description: expected a string")
	if "$schema" in doc and not isinstance(doc["$schema"], str):
		errors.append("$schema: expected a string")

	if "slot" in doc:
		v = doc["slot"]
		if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= F.SLOT_COUNT:
			slot = v
		else:
			errors.append(f"slot: expected an integer 1..{F.SLOT_COUNT}")

	if "name" in doc:
		v = doc["name"]
		if not isinstance(v, str):
			errors.append("name: expected a string")
		elif len(v) > F.NAME_LEN or not all(0x20 <= ord(c) <= 0x7E for c in v):
			errors.append(
				f"name: expected at most {F.NAME_LEN} printable ASCII characters"
			)
		else:
			name = v

	for top in F.TOP_ORDER:
		if top not in doc:
			continue
		if _is_pad(top):
			_apply_pad(base, int(top[3:]), top, doc[top], errors, assigns)
		else:
			_walk(_TREE[top], doc[top], top, errors, assigns)

	if errors:
		raise DocError(errors)
	out = base.copy()
	if name is not None:
		out.name = name
	for idx, raw in assigns:
		out.body[idx] = raw
	return out, slot


def _walk(node, val, path: str, errors: list[str], assigns: list) -> None:
	if isinstance(node, F.Param):
		try:
			assigns.append((node.index, node.from_json(val)))
		except ValueError as e:
			errors.append(f"{path}: {e}")
		return
	if not isinstance(val, dict):
		errors.append(f"{path}: expected an object with keys: {', '.join(node)}")
		return
	for k, v in val.items():
		if k not in node:
			errors.append(f"{path}.{k}: unknown key{_suggest(k, node)}")
		else:
			_walk(node[k], v, f"{path}.{k}", errors, assigns)


def _apply_pad(
	base: Preset, n: int, path: str, val, errors: list[str], assigns: list
) -> None:
	if not isinstance(val, dict):
		errors.append(f"{path}: expected an object")
		return
	tparam = F.BY_PATH[(path, "type")]
	eff_raw = base.body[tparam.index]
	if "type" in val:
		try:
			new_raw = tparam.from_json(val["type"])
		except ValueError as e:
			errors.append(f"{path}.type: {e}")
			return
		if new_raw != eff_raw:
			assigns.extend((i, 0) for i in F.PAD_VALUE_INDEX[n])
		eff_raw = new_raw
		assigns.append((tparam.index, new_raw))
	ptype = tparam.values[eff_raw] if tparam.valid(eff_raw) else None

	for k, v in val.items():
		if k == "type":
			continue
		if k in PAD_FIXED:
			_walk(F.BY_PATH[(path, k)], v, f"{path}.{k}", errors, assigns)
			continue
		if ptype is None:
			errors.append(
				f"{path}.{k}: the pad's type byte is invalid; set 'type' explicitly"
			)
			continue
		sp = F.pad_param(n, ptype, k)
		if sp is not None:
			_walk(sp, v, f"{path}.{k}", errors, assigns)
			continue
		valid = F.pad_param_keys(ptype) + list(PAD_FIXED)
		other = [t for t in F.PAD_TYPES if k in F.pad_param_keys(t)]
		if other:
			errors.append(
				f"{path}.{k}: only valid for {' / '.join(other)} pads, not {ptype} "
				f"(valid keys here: {', '.join(valid)})"
			)
		else:
			errors.append(f"{path}.{k}: unknown key{_suggest(k, valid)}")


# -- text, flattening, diff ------------------------------------------------------------


def parse_json(text: str | bytes) -> Any:
	"""Parse JSON text (UTF-8, BOM tolerated); syntax errors become DocError."""
	if isinstance(text, bytes):
		try:
			text = text.decode("utf-8-sig")
		except UnicodeDecodeError as e:
			raise DocError([f"not valid UTF-8: {e}"]) from None
	try:
		return json.loads(text)
	except json.JSONDecodeError as e:
		raise DocError(
			[f"invalid JSON at line {e.lineno} column {e.colno}: {e.msg}"]
		) from None


def dump_json(doc: dict) -> str:
	return json.dumps(doc, indent="	", ensure_ascii=False) + "\n"


def flatten(doc: dict, prefix: str = "") -> dict[str, Any]:
	out: dict[str, Any] = {}
	for k, v in doc.items():
		if isinstance(v, dict) and set(v) != {"raw"}:
			out.update(flatten(v, f"{prefix}{k}."))
		else:
			out[f"{prefix}{k}"] = v
	return out


def is_complete_doc(doc: dict) -> bool:
	"""True if ``doc`` states every setting the JSON can express, so the preset it describes does not depend
	on the base it is applied to (apart from bytes JSON never shows, which come from the factory base)."""
	resolved, _ = apply_doc(factory(), doc)
	needed = set(flatten(preset_to_doc(resolved)))
	return needed <= set(flatten(doc))


def diff_presets(old: Preset, new: Preset) -> list[tuple[str, Any, Any]]:
	"""Differences as (json key, old value, new value); a missing side is None.

	Differences in bytes the JSON cannot express (a Panic pad's unused values)
	are reported under the key ``(hidden bytes)``.
	"""
	a, b = flatten(preset_to_doc(old)), flatten(preset_to_doc(new))
	out = [
		(k, a.get(k), b.get(k)) for k in dict.fromkeys([*a, *b]) if a.get(k) != b.get(k)
	]
	if not out and old != new:
		out.append(("(hidden bytes)", None, None))
	return out
