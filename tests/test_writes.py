"""The write log collapses repeats and stays bounded."""

from tap import writes
from tap.model import Outcome, Table, Transaction
from tap.writes import WriteLog


def write(values, start=2054, outcome=Outcome.CONFIRMED, unit=1):
    return Transaction(unit=unit, function=16, table=Table.HOLDING, start=start, values=tuple(values), outcome=outcome)


def test_repeats_collapse_into_runs():
    log = WriteLog()
    for t in range(5):
        log.add(write([1, 2]), 100.0 + t)
    log.add(write([1, 3]), 200.0)
    log.add(write([1, 3], outcome=Outcome.REJECTED), 201.0)
    log.add(Transaction(unit=1, function=3, table=Table.HOLDING, start=0, values=(5,), outcome=Outcome.ANSWERED), 202.0)

    (block,) = log.newest_first()
    assert (block.addresses, block.total, block.distinct_values) == ("2054-2055", 7, 2)
    assert [(r.values, r.outcome, r.count) for r in block.runs] == [((1, 2), "confirmed", 5), ((1, 3), "confirmed", 1), ((1, 3), "rejected", 1)]
    assert (block.runs[0].first, block.runs[0].last) == (100.0, 104.0)


def test_history_is_bounded():
    log = WriteLog()
    for i in range(writes.MAX_RUNS + 20):
        log.add(write([i]), float(i))
    assert len(log.newest_first()[0].runs) == writes.MAX_RUNS
    assert log.newest_first()[0].runs[0].values == (20,)

    for start in range(writes.MAX_BLOCKS + 5):
        log.add(write([0], start=start), 1000.0 + start)
    assert len(log.blocks) == writes.MAX_BLOCKS
    assert (1, "holding", 2054, 1) not in log.blocks  # the least recently written went first


def test_survives_a_round_trip():
    log = WriteLog()
    log.add(write([1, 2]), 100.0)
    log.add(write([1, 2]), 160.0)
    again = WriteLog.from_dict(log.as_dict())
    assert again.as_dict() == log.as_dict()
    assert WriteLog.from_dict(None).blocks == {}
