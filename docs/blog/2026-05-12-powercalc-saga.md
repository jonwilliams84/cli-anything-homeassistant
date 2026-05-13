# Two silent footguns in Home Assistant's Powercalc API (and how I tripped both in one evening)

*2026-05-12 / 2026-05-13 — published from `cli-anything-homeassistant` v1.26.0*

I spent a session building out hierarchical [Powercalc](https://github.com/bramstroker/homeassistant-powercalc)
rollups for my house — every device estimated, every room rolled up, every
floor rolled up to a `Home Total` that you can compare against the smart
meter. The goal: a single Energy view with an `Actual vs Estimated`
overlay so the gap between the two is obviously the "stuff we haven't
modelled yet".

It worked, eventually. But along the way I hit two API gotchas that
were both **silent**: no exception, no warning, no log line. Just data
quietly wrong. This post is about both, and the safety helpers I added
to the harness so I (and anyone using it) can't hit them again.

---

## Footgun #1 — Group membership is `REPLACE`, not `APPEND`

Powercalc exposes a group's membership through its **options flow**.
The schema looks like the most reasonable thing in the world:

```python
{
    "group_member_sensors": [...],   # config_entry ids
    "group_power_entities": [...],   # sensor.*_power entity ids
    "group_energy_entities": [...],
    "sub_groups": [...],
    "area": ...,
    "floor": ...,
}
```

I had a freshly-built fridge sensor and wanted to add it to four groups:
`Kitchen`, `Appliances`, `Ground Floor`, `Home Total`. The naive code:

```python
for group_entry_id in [kitchen, appliances, ground_floor, home_total]:
    options_flow_set(client, group_entry_id, {
        "group_power_entities": [new_fridge_sensor],
    })
```

This looks like "add the fridge sensor". It is not. The options flow
**replaces** the entire `group_power_entities` list with whatever you
submit. My one-element list wiped:

| Group | Before | After |
|---|---:|---:|
| Kitchen | 19 entities | 1 |
| Appliances | 6 entities | 1 |
| Ground Floor | 57 leaves | 1 |
| Home Total | 92 leaves | 1 |

Recovery took a JSON snapshot from earlier in the session, a hand-rebuilt
list of Kitchen's 19 lights (recovered from logs of an earlier inspection),
and careful reconstruction of the floor/total rollups using `sub_groups`
instead of flat entity lists.

The fix in the harness — `cli_anything.homeassistant.core.powercalc` —
gives you two unmistakably-named operations:

```python
from cli_anything.homeassistant.core import powercalc

# SAFE — reads current members, merges in the new ones, submits the union
powercalc.add_group_members(
    client, entry_id=kitchen_entry,
    sensor_entity_id="sensor.power_kitchen_power",
    entities=["sensor.family_hub_fridge_derived_power"],
)

# SAFE — reads current, drops the named ones, submits what's left
powercalc.remove_group_members(...)

# EXPLICIT — replaces, named so you know it's destructive
powercalc.set_group_members(client, entry_id, power_entities=[...])
```

You can still shoot yourself in the foot with `set_group_members`, but
now you have to *type the word "set"* to do it. That feels about right.

---

## Footgun #2 — Fixed-mode powercalc on a `binary_sensor` source silently no-ops

Hours later, I added the immersion heater. Setup:

* **Source**: `binary_sensor.t_smart_relay` — turns on when the
  Telford T-Smart immersion controller closes its relay to heat the tank.
* **Mode**: fixed
* **Power**: 3000 W when on, 0 when off.

The powercalc flow accepted all of this without complaint. The sensor
was created. Its source attribute was correctly set to the relay
binary_sensor. Everything *looked* fine.

Then the tank cooled below the deadband and the immersion fired:

* Smart meter: **0 W → 3 922 W → 0 W** (40 seconds)
* Tank temperature: **42.4 °C → 45.2 °C** (the heat actually went in)
* `binary_sensor.t_smart_relay`: **off → on → off** (state changes logged)
* `sensor.immersion_heater_power`: **0 W** (no change recorded at all)

The dashboard's `Home Total` estimate didn't budge during the spike.

Why? Powercalc's fixed-mode `power: <number>` form gates on the source
entity going to a recognised "on" state — but only for source domains it
treats as on/off-able: `light`, `switch`, the usual suspects. For
`binary_sensor`, the form accepts the config and then... does nothing
useful with it.

The fix is to use `power_template` and gate explicitly:

```jinja
{{ 3000 if is_state('binary_sensor.t_smart_relay', 'on') else 0 }}
```

This works perfectly. But you have to *know* to do it.

The harness now refuses the bug:

```python
powercalc.create_virtual_power(
    client,
    source_entity="binary_sensor.t_smart_relay",
    name="Immersion Heater",
    power=3000,    # raises ValueError
)
```

```
ValueError: Source `binary_sensor.t_smart_relay` is a 'binary_sensor' —
powercalc's fixed-mode `power: <number>` form does not gate on
binary_sensor state and the resulting sensor will be stuck at 0 W. Use
`power_template=` with an explicit `is_state(...)` check instead, e.g.:
  power_template="{{ 3000 if is_state('binary_sensor.t_smart_relay', 'on') else 0 }}"
```

The error message includes a copy-pasteable template that matches your
actual source entity. Switch / light sources still accept the plain
`power=` form — only the known-broken combination errors.

---

## Other things this session

While we're here, a few smaller wins from the same evening:

### Replace SmartThings' nonsense fridge wattage with a derived value

Samsung's SmartThings integration exposes `sensor.family_hub_power` for
the Family Hub fridge. It reports values like 642 W → 747 W → 1107 W,
constantly fluctuating. None of these are real — they appear to come
from instantaneous current draw of whatever subsystem polled last
(touchscreen, ice maker compressor, defrost). For a fridge the
**only** meaningful number is the time-averaged draw, and the DOE
EnergyGuide nameplate says **85 W average** for this model.

Better: build a derivative pipeline from the *cumulative kWh* sensor:

```
sensor.family_hub_energy (kWh, monotonic)
        ↓ Home Assistant derivative helper, 1 h window
sensor.family_hub_fridge_energy_rate_1h (kW)
        ↓ Template sensor: × 1000, clamp [15, 800]
sensor.family_hub_fridge_derived_power (W)
```

The 1-hour window smooths out compressor cycles. The 15 W floor stops
the value bottoming out at 0 during long compressor-off periods (the
LCD touchscreen alone draws something). The 800 W ceiling rejects
defrost-cycle spikes that aren't sustained.

After an hour the value sat at 31 W — barely above the floor, consistent
with a quiet overnight period. Through the day it'll fluctuate, but
the 24-hour average should land near 85 W as advertised.

### The UPS daisy-chain riddle

The "by domain" mini-graph showed `Infrastructure` at ~366 W, which
included `sensor.rack_total_power` (a YAML template sensor, not a
powercalc group — that took an entity-registry round trip to figure out).
There are *four* UPSes on the network, but they're **daisy-chained off
the big SMT3000**:

```
Wall → SMT3000 ─┬── SMT1500i
                ├── elt-k8s-1 (only exposes load %, no W sensor)
                ├── APC 1000
                └── direct loads
```

Which means `rack_total_power` (tracking just the SMT3000) **is** the
whole rack draw. Adding the smaller UPSes would double-count. This is
exactly the kind of fact that needs to be written down — it's the third
time this session I'd done the math on "why doesn't UPS_a + UPS_b match
rack_total" before realising the topology made it impossible.

### Removing the Bambu X1C from rollups

The X1C is on the SMT3000, so its draw is already in `rack_total_power`.
Having it *also* as a separate powercalc entry (gated on print_status
existing → fixed 500 W) was the worst kind of double-count, because the
"fixed 500 W" was wrong twice: wrong because the printer was idle, and
wrong because the UPS already had it. Deleted the entry, deleted the
now-empty `Power · Workshop` group, and coverage % dropped from
**107 %** (clearly bogus) to **44 %** (honestly modest).

The Bambu WLED *strip* stayed — that's a separate USB-powered light not
on the UPS chain.

### Dining Lamp 2 / Sophie's Lamp duplicates

Phase 1 of the powercalc rollout had created some duplicate entries —
older `loungelamp2_power` (active, with energy history) sitting alongside
a newer `dining_lamp_2_power` (Phase 1, no history) both pointing at the
same `light.loungelamp2`. Sophie's Lamp had **three** entries from
successive setup attempts.

Fix: keep the entries (preserve energy history) but make sure only one
copy of each physical fixture is in any rollup. Group memberships updated;
no `delete_entry` calls needed.

### Kids swapped bedrooms

While auditing, I noticed `sensor.noah_bedroom_big_light_device_power`
was in the `Power · Sophie Bedroom` group. Flagged it as wrong, the
user said "that's correct, they moved rooms" — entity_id is stale but
the device physically lives where the group says it does. Several other
entities are similarly cross-named (the friendly_names were updated;
the entity_ids were not, because renaming entity_ids breaks every
automation, dashboard, and history reference they appear in).

Saved that to project memory so future me doesn't keep "fixing" the
non-bug.

---

## What's in v1.26.0

```
cli_anything/homeassistant/core/powercalc.py
tests/test_powercalc.py          (23 tests, all passing)
```

Functions exported:

* `get_group_members(client, sensor_entity_id)` — read resolved entity list
* `set_group_members(client, entry_id, *, power_entities, sub_groups, energy_entities)` —
  REPLACE (destructive, named so)
* `add_group_members(client, entry_id, *, sensor_entity_id, entities)` —
  SAFE add (reads current, merges, submits union)
* `remove_group_members(client, entry_id, *, sensor_entity_id, entities)` —
  SAFE remove
* `create_virtual_power(client, *, source_entity, name, power=..., power_template=..., groups=...)` —
  refuses `binary_sensor + power=<number>` with a helpful error

Two silent footguns turned into loud `ValueError`s. That's the win.

---

## Why this matters beyond Powercalc

Both bugs are the same shape: **an API that accepts an action and produces
the wrong outcome with no signal to the caller**. The options flow accepts
a single-element list and writes it; it could have validated against the
current member count or warned that 92 entries would be lost. The fixed
mode accepts a binary_sensor source and silently doesn't gate; it could
have rejected the combination or emitted a config warning.

In both cases the harness can hold the line where Powercalc doesn't. The
pattern — *wrap the raw API with a safer surface that turns silent
failures into loud ones* — is the whole point of having a CLI harness in
the first place.

Tomorrow: verify the immersion `power_template` actually catches the next
3 000 W cycle. The deadband should fire within the hour.
