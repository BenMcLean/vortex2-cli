import pytest

import vortexlib as vl
from vortexlib import codec
from vortexlib import fields as F


def test_detect_and_load_each_format():
	p = vl.factory(5)
	for fmt in vl.FORMATS:
		loaded = vl.load(vl.dump(p, fmt, slot=5))
		assert loaded.fmt == fmt
		assert vl.resolve(loaded, vl.factory()) == p
	assert vl.load(vl.dump(p, "syx", slot=5)).slot == 5
	assert vl.load(vl.dump(p, "vw2")).slot is None
	assert vl.load(vl.dump(p, "json", slot=7)).slot == 7


def test_syx_needs_slot_and_single_message():
	with pytest.raises(vl.SlotRequired):
		vl.dump(vl.factory(), "syx")
	with pytest.raises(vl.FormatError, match="exactly one"):
		vl.load(vl.dump(vl.factory(), "syx", 1) * 2)
	with pytest.raises(vl.FormatError):
		vl.detect(b"hello")


def test_resolve_uses_given_base():
	device = vl.factory()
	device.body[40] = 99
	assert vl.resolve(vl.load(b'{"name": "Hi"}'), device).body[40] == 99


class FakeClock:
	def __init__(self):
		self.t = 0.0

	def now(self):
		return self.t

	def sleep(self, s):
		self.t += s


def make(busy=0.5, settle=1.5):
	clk = FakeClock()
	sim = vl.SimKeytar(busy=busy, clock=clk.now)
	return (
		sim,
		vl.Keytar(sim, vl.Timing(settle=settle), sleep=clk.sleep, clock=clk.now),
		clk,
	)


def test_read_write_roundtrip():
	sim, kt, _ = make()
	p = vl.factory()
	p.name = "Hello"
	kt.write(10, p)
	assert kt.read(10) == p
	assert kt.read(9) == vl.factory(9)


def test_busy_get_is_dropped_and_retried():
	sim, kt, clk = make(
		busy=0.5, settle=0.1
	)  # the verify read arrives while busy: first attempt is dropped
	p = vl.factory()
	p.name = "Retry"
	kt.write(3, p)
	assert sim.slots[2] == p


def test_write_refuses_invalid_and_reports_silence():
	_, kt, _ = make()
	bad = vl.factory()
	bad.body[F.BY_PATH[("upper", "channel")].index] = 0x7F
	with pytest.raises(vl.DeviceError, match="invalid"):
		kt.write(1, bad)

	class Dead:
		def send(self, d):
			pass

		def receive(self, t):
			return None

		def drain(self):
			pass

	clk = FakeClock()
	with pytest.raises(vl.DeviceError, match="no valid reply"):
		vl.Keytar(Dead(), vl.Timing(), sleep=clk.sleep, clock=clk.now).read(1)


def test_slot_bounds():
	_, kt, _ = make()
	for s in (0, 26):
		with pytest.raises(ValueError):
			kt.read(s)


def test_sim_follows_spec_edge_behaviour():
	sim, _, _ = make()
	p = vl.factory()
	p.name = "X"
	sim.send(
		codec.build_message(codec.CMD_SET, 0, p)[:-2] + b"\xf7"
	)  # one byte short: ignored
	assert sim.slots[0].name == ""
	sim.send(codec.build_get(30))  # out of range: template, slot byte 0
	assert codec.parse_message(sim.receive(0)) == (codec.CMD_REPLY, 0, vl.factory())
