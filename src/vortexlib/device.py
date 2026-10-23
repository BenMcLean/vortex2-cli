"""Talking to a keytar over any byte transport, following spec section 8.1.

The library does not open MIDI ports.  Callers provide a ``Transport`` that
sends and receives complete SysEx messages (F0 ... F7) as ``bytes``.
Slots are 1-based, as everywhere in this library.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol

from . import codec
from . import fields as F
from .formats import check_slot
from .preset import Preset, factory


class DeviceError(RuntimeError):
	"""The keytar did not answer, or a write could not be verified."""


class Transport(Protocol):
	def send(self, data: bytes) -> None:
		"""Send one complete SysEx message."""

	def receive(self, timeout: float) -> bytes | None:
		"""Wait up to ``timeout`` seconds for one complete SysEx message; None if none arrives."""

	def drain(self) -> None:
		"""Discard anything already received."""


@dataclass
class Timing:
	"""Spec 2 and 8.1: the device drops Gets for ~0.5 s after a Set and never acknowledges anything."""

	settle: float = 1.5  # wait after every Set before the next message
	reply_timeout: float = 1.5  # how long to wait for a Reply
	read_attempts: int = 3
	retry_wait: float = 0.5


class Keytar:
	def __init__(
		self,
		transport: Transport,
		timing: Timing | None = None,
		sleep: Callable[[float], None] = time.sleep,
		clock: Callable[[], float] = time.monotonic,
	):
		self.transport = transport
		self.timing = timing or Timing()
		self._sleep = sleep
		self._clock = clock

	def read(self, slot: int) -> Preset:
		"""Read ``slot`` (1..25).  Silence is the only error signal, so it is retried."""
		idx = check_slot(slot) - 1
		t = self.timing
		for attempt in range(t.read_attempts):
			if attempt:
				self._sleep(t.retry_wait)
			self.transport.drain()
			self.transport.send(codec.build_get(idx))
			deadline = self._clock() + t.reply_timeout
			while True:
				remaining = deadline - self._clock()
				if remaining <= 0:
					break
				msg = self.transport.receive(remaining)
				if msg is None:
					break
				try:
					cmd, got, preset = codec.parse_message(msg)
				except codec.FormatError:
					continue
				if cmd == codec.CMD_REPLY and got == idx:
					return preset
		raise DeviceError(
			f"no valid reply for slot {slot} after {t.read_attempts} attempts "
			"(is the keytar connected and not busy?)"
		)

	def write(self, slot: int, preset: Preset, verify: bool = True) -> None:
		"""Write ``preset`` to ``slot`` and, unless ``verify`` is False, read it back and compare."""
		idx = check_slot(slot) - 1
		problems = preset.problems()
		if problems:
			raise DeviceError(
				"refusing to write an invalid preset: " + "; ".join(problems)
			)
		msg = codec.build_message(codec.CMD_SET, idx, preset)
		for attempt in range(2):
			self.transport.send(msg)
			self._sleep(self.timing.settle)
			if not verify:
				return
			if self.read(slot) == preset:
				return
		raise DeviceError(f"slot {slot} did not read back as written after 2 attempts")


class SimKeytar:
	"""A software keytar implementing the behaviour measured in spec sections 2, 5 and 6.

	State is in memory only; ``snapshot``/``restore`` let a caller persist it.  ``busy`` is the time after a Set
	during which Gets are silently dropped (0.5 s measured).
	"""

	def __init__(self, busy: float = 0.5, clock: Callable[[], float] = time.monotonic):
		self.slots = [factory(i + 1) for i in range(F.SLOT_COUNT)]
		self.busy = busy
		self._clock = clock
		self._busy_until = 0.0
		self._inbox: list[bytes] = []

	def snapshot(self) -> list[bytes]:
		return [bytes(p.body) for p in self.slots]

	def restore(self, bodies: list[bytes]) -> None:
		if len(bodies) != F.SLOT_COUNT:
			raise ValueError(f"expected {F.SLOT_COUNT} slot bodies")
		self.slots = [Preset(b) for b in bodies]

	# Transport
	def send(self, data: bytes) -> None:
		if data[:6] != codec.HEADER or data[-1:] != b"\xf7" or len(data) < 7:
			return
		if data[6] == codec.CMD_GET and len(data) == 11 and data[7:9] == b"\x00\x01":
			if self._clock() < self._busy_until:
				return
			slot = data[9]
			if slot <= codec.MAX_SLOT:
				self._inbox.append(
					codec.build_message(codec.CMD_REPLY, slot, self.slots[slot])
				)
			else:  # out of range: firmware template, slot byte 0 (spec 5.1)
				default = factory()
				self._inbox.append(codec.build_message(codec.CMD_REPLY, 0, default))
		elif (
			data[6] == codec.CMD_SET
			and len(data) == codec.MSG_LEN
			and data[9] <= codec.MAX_SLOT
		):
			self.slots[data[9]] = Preset(data[10:181])
			self._busy_until = self._clock() + self.busy

	def receive(self, timeout: float) -> bytes | None:
		return self._inbox.pop(0) if self._inbox else None

	def drain(self) -> None:
		self._inbox.clear()
