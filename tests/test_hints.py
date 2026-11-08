from msn.hints import find_strings, register_hints
from msn.rtu import RegisterStats


def stats(*values, written=False):
    s = RegisterStats(values[0], values[0], values[0], written=written)
    for v in values[1:]:
        s.update(v, written)
    return s


def test_hints():
    assert "mains voltage x0.1 V?" in register_hints(stats(2344, 2350, 2340))
    assert "mains frequency x0.01 Hz?" in register_hints(stats(4999))
    assert "probably signed (int16)" in register_hints(stats(65332))
    assert "only increases (counter?)" in register_hints(stats(10, 11, 12))
    assert "constant" in register_hints(stats(7, 7, 7))
    assert "written by the master" in register_hints(stats(26, written=True))


def test_find_strings():
    regs = {(1, "input", 144 + i): stats(v) for i, v in enumerate([0x5353, 0x452D, 0x4848, 0x364B])}
    regs[(1, "input", 148)] = stats(5)
    assert find_strings(regs) == [{"slave": 1, "table": "input", "address": 144, "count": 4, "text": "SSE-HH6K"}]
