"""SCRATCH — dump select options."""
import json
from cli_anything.homeassistant.utils.homeassistant_backend import HomeAssistantClient
from cli_anything.homeassistant.core import config_entries as ce

def sel(r):
    out = {}
    for s in (r.get("data_schema") or []):
        selr = s.get("selector") or {}
        if "select" in selr:
            opts = selr["select"].get("options")
            out[s["name"]] = [o["value"] if isinstance(o, dict) else o for o in opts][:25]
    return out

def test_opts(hass_instance):
    c = HomeAssistantClient(url=hass_instance["url"], token=hass_instance["token"], timeout=30)
    c.post("states/sensor.probe_power", {"state": "5", "attributes": {"unit_of_measurement": "W", "device_class": "power"}})
    for dom in ("derivative","integration","utility_meter","min_max","switch_as_x","generic_hygrostat","tod","threshold"):
        r = ce.flow_init(c, dom)
        print(f"SEL {dom}: {json.dumps(sel(r))[:700]}")
    # menu variants second step
    for dom, ch in (("group","sensor"),("random","sensor"),("template","sensor")):
        r = ce.flow_init(c, dom)
        r2 = ce.flow_configure(c, r["flow_id"], {"next_step_id": ch})
        print(f"SEL {dom}/{ch}: fields={[(s['name'], s.get('required')) for s in r2.get('data_schema') or []]}")
        print(f"    opts={json.dumps(sel(r2))[:400]}")
    # statistics characteristic options for a numeric sensor and a binary sensor
    c.post("states/binary_sensor.probe_bin", {"state": "on"})
    for src in ("sensor.probe_power", "binary_sensor.probe_bin"):
        r = ce.flow_init(c, "statistics")
        r2 = ce.flow_configure(c, r["flow_id"], {"name": "sc probe", "entity_id": src})
        print(f"SEL statistics[{src}]: {json.dumps(sel(r2))[:600]}")
