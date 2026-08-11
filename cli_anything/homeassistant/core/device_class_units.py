"""Device-class unit conversion — what a sensor/number can be displayed as.

Home Assistant lets you override the *display* unit of a `sensor` or `number`
entity through its registry options (``entity update --options`` with
``{"sensor": {"unit_of_measurement": "°F"}}``). HA rejects any unit that is not
convertible from the native one, and the set of legal units is decided by the
entity's **device class** — not by the integration and not by anything visible
in the state attributes.

These two WS commands are how the UI populates that dropdown, and they are the
only way to know a conversion will be accepted before attempting the write.

WS commands wrapped
-------------------
* ``sensor/device_class_convertible_units`` — legal display units for a sensor
  device class (e.g. ``temperature`` → ``°C``/``°F``/``K``).
* ``number/device_class_convertible_units`` — the same for ``number`` entities.
* ``sensor/numeric_device_classes`` — which sensor device classes are numeric
  at all (the ones that support precision + unit overrides).

These three commands are registered by the ``sensor`` / ``number`` integrations
themselves, not by ``websocket_api``: on a server where the domain has never
been loaded (no sensor entity, no ``default_config``) HA answers
``unknown_command``. That error is passed through rather than swallowed — it
means "this HA has no sensors", which is a different answer from "this device
class has no convertible units" (an empty list).

Public API
----------
* :func:`sensor_convertible_units`
* :func:`number_convertible_units`
* :func:`convertible_units`
* :func:`numeric_device_classes`
* :func:`is_numeric_device_class`
* :func:`can_convert_to`
* :func:`entity_device_class`
* :func:`entity_convertible_units`
* :func:`display_options`
* :func:`set_display_options`
"""

from __future__ import annotations

from cli_anything.homeassistant.core import entity_registry_extras as _registry_extras
from cli_anything.homeassistant.core import registry as _registry
from cli_anything.homeassistant.core import states as _states

WS_SENSOR_UNITS = "sensor/device_class_convertible_units"
WS_NUMBER_UNITS = "number/device_class_convertible_units"
WS_NUMERIC_DEVICE_CLASSES = "sensor/numeric_device_classes"

#: Entity domains that support a device-class-driven unit override.
SUPPORTED_DOMAINS = ("sensor", "number")


def _require_device_class(device_class: str) -> str:
    if not device_class or not str(device_class).strip():
        raise ValueError("device_class is required")
    return str(device_class)


def _units_from(result) -> list[str]:
    if not isinstance(result, dict):
        return []
    return sorted(str(u) for u in (result.get("units") or []))


def sensor_convertible_units(client, device_class: str) -> list[str]:
    """Return the display units a ``sensor`` of *device_class* can use.

    An empty list means the device class is not convertible (or is unknown to
    this HA build) — attempting a unit override will fail.
    """
    payload = {"device_class": _require_device_class(device_class)}
    return _units_from(client.ws_call(WS_SENSOR_UNITS, payload))


def number_convertible_units(client, device_class: str) -> list[str]:
    """Return the display units a ``number`` of *device_class* can use."""
    payload = {"device_class": _require_device_class(device_class)}
    return _units_from(client.ws_call(WS_NUMBER_UNITS, payload))


def convertible_units(client, device_class: str, *, domain: str = "sensor") -> list[str]:
    """Dispatch to the sensor or number variant based on *domain*.

    Raises
    ------
    ValueError
        If *domain* is not one of :data:`SUPPORTED_DOMAINS`.
    """
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(f"domain must be one of {SUPPORTED_DOMAINS}, got: {domain!r}")
    if domain == "number":
        return number_convertible_units(client, device_class)
    return sensor_convertible_units(client, device_class)


def numeric_device_classes(client) -> list[str]:
    """Return the sorted sensor device classes HA treats as numeric."""
    result = client.ws_call(WS_NUMERIC_DEVICE_CLASSES, {})
    if not isinstance(result, dict):
        return []
    return sorted(str(dc) for dc in (result.get("numeric_device_classes") or []))


def is_numeric_device_class(client, device_class: str) -> bool:
    """Return ``True`` if *device_class* is one of the numeric sensor classes."""
    return _require_device_class(device_class) in numeric_device_classes(client)


def can_convert_to(client, device_class: str, unit: str, *, domain: str = "sensor") -> bool:
    """Return ``True`` if *unit* is a legal display unit for *device_class*.

    The pre-flight for
    ``entity update <id> --options '{"sensor": {"unit_of_measurement": ...}}'``.
    """
    if not unit or not str(unit).strip():
        raise ValueError("unit is required")
    return str(unit) in convertible_units(client, device_class, domain=domain)


# ────────────────────────────────────────────────────────────────────────────
# Entity-level helpers (read the device class, then write the override)
# ────────────────────────────────────────────────────────────────────────────


def _split_domain(entity_id: str) -> str:
    if not entity_id or "." not in entity_id:
        raise ValueError(f"entity_id must look like 'domain.object_id', got: {entity_id!r}")
    domain = entity_id.split(".", 1)[0]
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"display options only apply to {SUPPORTED_DOMAINS} entities, got: {entity_id!r}"
        )
    return domain


def entity_device_class(client, entity_id: str) -> str | None:
    """Return the device class HA reports for *entity_id* (``None`` if unset).

    Read from the live state attributes, which is where the *effective* device
    class ends up — a registry override included.
    """
    _split_domain(entity_id)
    state = _states.get_state(client, entity_id) or {}
    attrs = state.get("attributes") or {}
    return attrs.get("device_class")


def entity_convertible_units(client, entity_id: str) -> dict:
    """Return the display units *entity_id* itself can be switched to.

    Resolves the entity's device class first, so callers do not have to know
    it. ``{"entity_id", "domain", "device_class", "units"}`` — an empty
    ``units`` list means no conversion is possible for this entity.
    """
    domain = _split_domain(entity_id)
    device_class = entity_device_class(client, entity_id)
    if not device_class:
        return {
            "entity_id": entity_id,
            "domain": domain,
            "device_class": None,
            "units": [],
        }
    return {
        "entity_id": entity_id,
        "domain": domain,
        "device_class": device_class,
        "units": convertible_units(client, device_class, domain=domain),
    }


def display_options(client, entity_id: str) -> dict:
    """Return the entity's *current* registry options for its own domain."""
    domain = _split_domain(entity_id)
    entry = _registry_extras.get_entity_registry_entry(client, entity_id=entity_id) or {}
    # `config/entity_registry/get` answers with {"entity_entry": {...}} on some
    # builds and the bare entry on others.
    entry = entry.get("entity_entry", entry) if isinstance(entry, dict) else {}
    options = entry.get("options") or {}
    current = options.get(domain) or {}
    return dict(current) if isinstance(current, dict) else {}


def set_display_options(
    client,
    entity_id: str,
    *,
    unit_of_measurement: str | None = None,
    display_precision: int | None = None,
    validate_unit: bool = True,
    merge: bool = True,
) -> dict:
    """Set the display unit and/or precision of a sensor/number entity.

    Two footguns are handled here:

    * HA **replaces** the whole per-domain option dict on write, so setting the
      unit alone would silently drop an existing precision override. With
      ``merge`` (the default) the current options are read first and merged.
    * HA rejects a unit that is not convertible from the native one. With
      ``validate_unit`` the device class is resolved and the unit checked
      first, so the failure is a clear local error instead of an opaque
      ``invalid_info`` from the registry.

    Returns ``{"entity_id", "domain", "options", "previous", "result"}``.

    Raises
    ------
    ValueError
        If neither field was supplied, the entity is not a sensor/number, or
        the unit is not convertible for its device class.
    """
    domain = _split_domain(entity_id)
    if unit_of_measurement is None and display_precision is None:
        raise ValueError("supply unit_of_measurement and/or display_precision")
    if display_precision is not None and display_precision < 0:
        raise ValueError("display_precision must be >= 0")

    if unit_of_measurement is not None and validate_unit:
        device_class = entity_device_class(client, entity_id)
        if not device_class:
            raise ValueError(f"{entity_id} has no device_class, so HA cannot convert its unit")
        allowed = convertible_units(client, device_class, domain=domain)
        if unit_of_measurement not in allowed:
            raise ValueError(
                f"{unit_of_measurement!r} is not a convertible unit for device_class "
                f"{device_class!r}; allowed: {allowed or '(none)'}"
            )

    previous = display_options(client, entity_id) if merge else {}
    new_options = dict(previous)
    if unit_of_measurement is not None:
        new_options["unit_of_measurement"] = unit_of_measurement
    if display_precision is not None:
        new_options["display_precision"] = display_precision

    result = _registry.update_entity(
        client,
        entity_id,
        options=new_options,
        options_domain=domain,
    )
    return {
        "entity_id": entity_id,
        "domain": domain,
        "options": new_options,
        "previous": previous,
        "result": result,
    }
