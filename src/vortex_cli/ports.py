"""Real and simulated MIDI ports (everything that touches the operating system's MIDI stack or files)."""

from __future__ import annotations

import contextlib
import json
import pathlib
import time
from typing import Iterator

import vortexlib as vl

DEFAULT_PORT_NAME = (
	"Vortex Wireless 2"  # substring; hosts decorate the name (spec section 2)
)


class PortError(RuntimeError):
	"""No usable MIDI port."""


def _mido():
	try:
		import mido

		return mido
	except ImportError:
		raise PortError(
			'MIDI support is not installed; run: pip install "vortex-cli[midi]"'
		) from None


def list_ports() -> tuple[list[str], list[str]]:
	mido = _mido()
	try:
		return mido.get_input_names(), mido.get_output_names()
	except Exception as e:  # backend problems surface as many exception types
		raise PortError(f"cannot list MIDI ports: {e}") from e


def find_port(names: list[str], wanted: str, what: str) -> str:
	exact = [n for n in names if n == wanted]
	hits = exact or [n for n in names if wanted.lower() in n.lower()]
	if not hits:
		shown = ", ".join(repr(n) for n in names) or "none"
		raise PortError(
			f"no MIDI {what} port matching {wanted!r} (available: {shown}). Is the keytar connected?"
		)
	return hits[0]


class MidoTransport:
	"""``vortexlib.Transport`` over a mido input/output pair (SysEx only)."""

	def __init__(self, in_name: str, out_name: str):
		mido = _mido()
		self._mido = mido
		try:
			self._in = mido.open_input(in_name)
			self._out = mido.open_output(out_name)
		except Exception as e:
			raise PortError(f"cannot open MIDI ports: {e}") from e

	def send(self, data: bytes) -> None:
		self._out.send(self._mido.Message("sysex", data=list(data[1:-1])))

	def receive(self, timeout: float) -> bytes | None:
		deadline = time.monotonic() + timeout
		while True:
			msg = self._in.poll()
			if msg is not None:
				if msg.type == "sysex":
					return bytes([0xF0, *msg.data, 0xF7])
				continue
			if time.monotonic() >= deadline:
				return None
			time.sleep(0.005)

	def drain(self) -> None:
		while self._in.poll() is not None:
			pass

	def close(self) -> None:
		self._in.close()
		self._out.close()


@contextlib.contextmanager
def open_keytar(
	port: str | None, in_port: str | None, out_port: str | None, timing: vl.Timing
) -> Iterator[vl.Keytar]:
	"""Open the keytar.  ``port`` of ``sim`` or ``sim:FILE`` selects a software keytar (state kept in FILE)."""
	port = port or DEFAULT_PORT_NAME
	if port == "sim" or port.startswith("sim:"):
		sim = vl.SimKeytar()
		path = pathlib.Path(port[4:]) if port.startswith("sim:") else None
		if path is not None and path.exists():
			sim.restore(
				[bytes.fromhex(h) for h in json.loads(path.read_text())["slots"]]
			)
		try:
			yield vl.Keytar(sim, timing)
		finally:
			if path is not None:
				path.write_text(
					json.dumps({"slots": [b.hex() for b in sim.snapshot()]}, indent=1)
				)
		return
	ins, outs = list_ports()
	transport = MidoTransport(
		find_port(ins, in_port or port, "input"),
		find_port(outs, out_port or port, "output"),
	)
	try:
		yield vl.Keytar(transport, timing)
	finally:
		transport.close()
