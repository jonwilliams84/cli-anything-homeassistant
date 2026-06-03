# Bug — powercalc group membership: delete-cascade, non-persistent add, energy gap

**Status:** RESOLVED in v1.42.0 (2026-06-03) — wrappers rebuilt (read-config /
resend-all-fields / reload+verify / power+energy), all rollups restored & verified
across an HA restart. See CHANGELOG [1.42.0]. Root cause of the energy "gap": the
group energy sensor is a powercalc GroupedEnergySensor that accumulates member
energy from creation — the 4 broken groups had *unavailable* energy because their
power list held energy sensors (wrong device_class), not because energy_entities
was unset. Original — found 2026-06-03 during the 30× GLEDOPTO spot template migration
**Area:** `core/powercalc.py` (`add_group_members` / `set_group_members`), and the
delete + create_virtual_power lifecycle.

## What happened
Migrated 30 `light.spotlight_*` powercalc entries from `linear` → `fixed`+template
by **delete + recreate** (a linear entry's options flow has no `fixed` step, so
`set-template` can't reach it). The template work succeeded (30/30 on the
5 W-white / colour template, persists across restart). The **rollup group
memberships did not survive it.**

## Three distinct defects

1. **Deleting a virtual_power entry cascades a removal from every group it
   belongs to.** So delete+recreate silently strips the (same-id) sensor from
   its rollups. Recreate does NOT re-add it. Observed: Kitchen −13, Living −3,
   Porch & Lanterns −9, Utility −1 (Dining's 4 survived by batch-timing luck).
   → **delete+recreate is unsafe for grouped entries.** Need an in-place
   linear→fixed mode change (or `set-source`) so deletion isn't required.

2. **`add_group_members` writes don't persist across an HA restart.** Re-adding
   the spot *power* sensors via the safe wrapper restored the area rollups
   in-session (counts went 0→correct), but after `homeassistant.restart` they
   were **0 again**. The options-flow write isn't committing to the group's
   stored config (the `create_entry` response is misleading, same shape as the
   set-template no-op found in v1.41). Dining — never touched by the wrapper —
   held, which isolates the wrapper as the culprit.

3. **`add_group_members` ignores `group_energy_entities`.** It only touches the
   power-member list, so the energy rollups (`*_energy`) stayed at 0 spots even
   when the power side showed correct. All energy rollups (area AND global —
   Lighting energy, Home Total energy) lost the spot `_energy` members and the
   wrapper can't put them back.

## Current live state (for tomorrow's resume)
- 30 spots: ✅ on template, fixed mode, persists.
- POWER: Home Total / Lighting = 30 ✅ (spots still in the home total). Dining
  area = 4 ✅. **Kitchen / Living / Utility / Porch & Lanterns area power = 0** ❌.
- ENERGY: **all rollups = 0 spots** ❌ (global + area).
- No double-count anywhere; no group-level powercalc entries exist.

## Fix direction
- `add_group_members` / `set_group_members`: write BOTH `group_power_entities`
  and `group_energy_entities`; read-back-verify the stored options actually
  changed (don't trust `create_entry`); reload after.
- Add an in-place `linear→fixed` (or generic mode-change / set-source) path so
  grouped entries never need delete+recreate.
- Add `powercalc group members <entry>` (read) + a `reconcile` to restore a
  known membership set from a snapshot.

## Repair plan (tomorrow, once wrapper fixed)
Re-add to area power+energy rollups: Kitchen (13), Living (3), Utility (1),
Porch & Lanterns (9 = 8 lantern + airing_cupboard); restore spot `_energy`
members to Lighting-energy and Home-Total-energy. Snapshot of the pre-migration
membership is reconstructable from the entity naming (spotlight_<area>_*).
