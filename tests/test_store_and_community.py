from tap.community import parse_map, suggest
from tap.model import Outcome, Table, Transaction
from tap.store import MIN_STALE_SECONDS, RegisterStore


def read(unit, table, start, values):
    function = 4 if table is Table.INPUT else 3
    return Transaction(unit, function, table, start, tuple(values), Outcome.ANSWERED)


def test_store_values_and_listeners():
    store, calls, units = RegisterStore(), [], []
    store.on_new_unit(units.append)
    store.subscribe([(1, Table.INPUT, 37)], lambda: calls.append(1))
    store.apply(read(1, Table.INPUT, 37, [2344, 0]), now=100.0)
    store.apply(read(1, Table.INPUT, 37, [2350, 0]), now=120.0)
    assert store.values([(1, Table.INPUT, 37), (1, Table.INPUT, 38)]) == [2350, 0]
    assert calls == [1, 1] and units == [1]
    assert store.registers[(1, Table.INPUT, 37)].changes == 1
    assert store.reads[1] == {(Table.INPUT, 37, 2)}


def test_rejected_and_unanswered_change_nothing():
    store = RegisterStore()
    store.apply(Transaction(1, 16, Table.HOLDING, 10, (5,), Outcome.REJECTED), now=1.0)
    store.apply(Transaction(1, 16, Table.HOLDING, 10, (5,), Outcome.UNANSWERED), now=1.0)
    assert store.registers == {}
    store.apply(Transaction(1, 16, Table.HOLDING, 10, (5,), Outcome.CONFIRMED), now=1.0)
    assert store.registers[(1, Table.HOLDING, 10)].written


def test_staleness_learns_poll_interval():
    store, calls = RegisterStore(), []
    key = (1, Table.INPUT, 1)
    store.subscribe([key], lambda: calls.append("x"))
    for t in (0.0, 200.0, 400.0):
        store.apply(read(1, Table.INPUT, 1, [1]), now=t)
    assert store.values([key], now=400 + 3 * 200) == [1]  # three missed polls is still fine
    assert store.values([key], now=400 + 3 * 200 + 1) is None
    calls.clear()
    store.check_stale(now=400 + 601)
    store.check_stale(now=400 + 700)  # notifies once, not again
    assert calls == ["x"]
    assert store.poll_interval(1) == 200.0


def test_fast_polling_still_waits_minimum():
    store = RegisterStore()
    for t in (0.0, 1.0, 2.0):
        store.apply(read(1, Table.INPUT, 1, [1]), now=t)
    assert store.values([(1, Table.INPUT, 1)], now=2 + MIN_STALE_SECONDS) == [1]


MAP = """
name: Example hybrid
manufacturer: Example
match:
  model_text: "^SSE-HH"
  reads: ["input 1-100"]
sensors:
  - name: Model
    address: 144
    input_type: input
    data_type: string
    count: 4
    model: true
  - name: Grid voltage
    address: 37
    input_type: input
    scale: 0.1
"""


def test_community_map_and_suggestion_by_model_text():
    community = parse_map("example", MAP)
    store = RegisterStore()
    store.apply(read(1, Table.INPUT, 144, [0x5353, 0x452D, 0x4848, 0x364B]), now=1.0)
    assert suggest([community], 1, store.values, store.reads.get(1, set())) is community
    assert community.for_unit(5)[0].device_address == 5


def test_suggestion_by_read_pattern():
    community = parse_map("example", MAP)
    store = RegisterStore()
    store.apply(read(2, Table.INPUT, 1, [0] * 100), now=1.0)
    assert suggest([community], 2, store.values, store.reads[2]) is community
    assert suggest([community], 2, store.values, set()) is None
