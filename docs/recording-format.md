# Recording format

A recording is one file named `recording-YYYYMMDD-HHMMSS.jsonl.gz`: gzip-compressed [JSON Lines](https://jsonlines.org), one JSON object per line. It may consist of several gzip members appended together, and standard tools (`zcat`, Python's `gzip`) read that as one stream.

Every line has a `type`. Times (`t`) are Unix timestamps in seconds, as floats.

## `header` (first line)

```json
{"type":"header","format":"modbus-tap-recording","version":1,"started":"2026-11-09T08:00:00+00:00",
 "bridge":{"host":"192.168.1.120","port":8899},
 "reference_entities":["sensor.pv_power"],
 "units":{"1":{"community_map":"sosen_sse_hh6k"}}}
```

## `transaction`

One request from the poller and how the unit answered.

```json
{"type":"transaction","t":1731139200.123,"unit":1,"function":4,"table":"input","start":37,
 "values":[2344,0,65332],"outcome":"answered"}
```

| Field | Meaning |
|---|---|
| `unit` | Unit address (0 is broadcast) |
| `function` | Modbus function code: 1–4 read, 5/6/15/16 write |
| `table` | `holding`, `input`, `coil` or `discrete_input` |
| `start` | First register address |
| `values` | Registers read, or values the poller tried to write. Coils are 0/1 |
| `outcome` | `answered` (a read), `confirmed` (a write the unit echoed), `rejected` (exception; see `exception_code`), `unanswered` (no reply) |

Only `answered` and `confirmed` values are what the unit actually holds.

## `entity`

The state of a reference entity, at the start and whenever it changes.

```json
{"type":"entity","t":1731139201.5,"entity_id":"sensor.pv_power","state":"2100","unit_of_measurement":"W"}
```

`device_class` and `friendly_name` are included when the entity has them.

## `note`

```json
{"type":"note","t":1731139300.0,"text":"kettle on"}
```

## `end` (last line)

```json
{"type":"end","t":1731150000.0,"ended":"2026-11-09T11:00:00+00:00","reason":"stopped"}
```

`reason` is `stopped`, `time limit reached` or `unloaded`. A file without an `end` line was cut short, for example by a restart.
