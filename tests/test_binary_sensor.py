"""The tests for the daily schedule sensor component."""
from __future__ import annotations

import datetime
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
import pytest
import pytz

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.daily_schedule.const import (
    ATTR_NEXT_TOGGLE,
    CONF_FROM,
    CONF_SCHEDULE,
    CONF_TO,
    CONF_UTC,
    DOMAIN,
    SERVICE_SET,
)


async def setup_entity(
    hass: HomeAssistant, name: str, schedule: list[dict[str, str]], utc: bool = False
) -> None:
    """Create a new entity by adding a config entry."""
    config_entry = MockConfigEntry(
        options={CONF_SCHEDULE: schedule, CONF_UTC: utc},
        domain=DOMAIN,
        title=name,
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def async_clenaup(hass: HomeAssistant) -> None:
    """Delete all config entries."""
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ["schedule"],
    [
        ([],),
        (
            [
                {
                    CONF_FROM: "01:02:03",
                    CONF_TO: "04:05:06",
                },
            ],
        ),
        (
            [
                {
                    CONF_FROM: "04:05:06",
                    CONF_TO: "01:02:03",
                },
            ],
        ),
        (
            [
                {
                    CONF_FROM: "00:00:00",
                    CONF_TO: "00:00:00",
                },
            ],
        ),
        (
            [
                {
                    CONF_FROM: "07:08:09",
                    CONF_TO: "10:11:12",
                },
                {
                    CONF_FROM: "01:02:03",
                    CONF_TO: "04:05:06",
                },
            ],
        ),
        (
            [
                {
                    CONF_FROM: "10:11:12",
                    CONF_TO: "01:02:03",
                },
                {
                    CONF_FROM: "01:02:03",
                    CONF_TO: "04:05:06",
                },
            ],
        ),
    ],
    ids=[
        "empty",
        "single",
        "overnight",
        "entire_day",
        "multiple",
        "adjusted",
    ],
)
async def test_new_sensor(hass, schedule):
    """Test new sensor."""
    entity_id = f"{Platform.BINARY_SENSOR}.my_test"
    await setup_entity(hass, "My Test", schedule)
    schedule.sort(key=lambda time_range: time_range[CONF_FROM])
    assert hass.states.get(entity_id).attributes[CONF_SCHEDULE] == schedule
    await async_clenaup(hass)


@patch("homeassistant.util.dt.now")
async def test_state(mock_now, hass):
    """Test state attribute."""
    mock_now.return_value = datetime.datetime.fromisoformat("2000-01-01 23:50:00")

    entity_id = f"{Platform.BINARY_SENSOR}.my_test"
    await setup_entity(
        hass,
        "My Test",
        [
            {CONF_FROM: "23:50:00", CONF_TO: "23:55:00"},
            {CONF_FROM: "00:00:00", CONF_TO: "00:05:00"},
        ],
    )

    assert hass.states.get(entity_id).state == STATE_ON

    state = STATE_OFF
    for _ in range(3):
        mock_now.return_value += datetime.timedelta(minutes=5)
        async_fire_time_changed(hass, mock_now.return_value)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == state
        state = STATE_ON if state == STATE_OFF else STATE_OFF

    await async_clenaup(hass)


@pytest.mark.parametrize(
    ["schedule"],
    [
        (
            [
                {
                    CONF_FROM: "00:00:00",
                    CONF_TO: "00:00:00",
                },
            ],
        ),
        (
            [
                {
                    CONF_FROM: "07:00:00",
                    CONF_TO: "07:00:00",
                },
            ],
        ),
        (
            [
                {
                    CONF_FROM: "17:00:00",
                    CONF_TO: "07:00:00",
                },
                {
                    CONF_FROM: "07:00:00",
                    CONF_TO: "17:00:00",
                },
            ],
        ),
    ],
    ids=["midnight", "one", "two"],
)
async def test_entire_day(hass, schedule):
    """Test entire day schedule."""
    entity_id = f"{Platform.BINARY_SENSOR}.my_test"
    await setup_entity(hass, "My Test", schedule)
    assert hass.states.get(entity_id).state == STATE_ON
    assert not hass.states.get(entity_id).attributes[ATTR_NEXT_TOGGLE]


@patch("homeassistant.util.dt.now")
@patch("homeassistant.helpers.event.async_track_point_in_time")
async def test_next_update(async_track_point_in_time, mock_now, hass):
    """Test next update time."""
    mock_now.return_value = datetime.datetime.fromisoformat("2000-01-01")

    in_5_minutes = mock_now.return_value + datetime.timedelta(minutes=5)
    in_10_minutes = mock_now.return_value + datetime.timedelta(minutes=10)
    previous_5_minutes = mock_now.return_value + datetime.timedelta(minutes=-5)
    previous_10_minutes = mock_now.return_value + datetime.timedelta(minutes=-10)

    # No schedule => no updates.
    assert async_track_point_in_time.call_count == 0

    # Inside a time range.
    await setup_entity(
        hass,
        "Test1",
        [
            {
                CONF_FROM: previous_5_minutes.time().isoformat(),
                CONF_TO: in_5_minutes.time().isoformat(),
            }
        ],
    )
    assert hass.states.get(f"{Platform.BINARY_SENSOR}.test1").state == STATE_ON
    next_update = async_track_point_in_time.call_args[0][2]
    assert next_update == in_5_minutes
    assert (
        hass.states.get(f"{Platform.BINARY_SENSOR}.test1").attributes[ATTR_NEXT_TOGGLE]
        == in_5_minutes
    )

    # After all ranges.
    await setup_entity(
        hass,
        "Test2",
        [
            {
                CONF_FROM: previous_10_minutes.time().isoformat(),
                CONF_TO: previous_5_minutes.time().isoformat(),
            }
        ],
    )
    assert hass.states.get(f"{Platform.BINARY_SENSOR}.test2").state == STATE_OFF
    expected_next_update = previous_10_minutes + datetime.timedelta(days=1)
    next_update = async_track_point_in_time.call_args[0][2]
    assert next_update == expected_next_update
    assert (
        hass.states.get(f"{Platform.BINARY_SENSOR}.test2").attributes[ATTR_NEXT_TOGGLE]
        == expected_next_update
    )

    # Before any range.
    await setup_entity(
        hass,
        "Test3",
        [
            {
                CONF_FROM: in_5_minutes.time().isoformat(),
                CONF_TO: in_10_minutes.time().isoformat(),
            }
        ],
    )
    assert hass.states.get(f"{Platform.BINARY_SENSOR}.test3").state == STATE_OFF
    next_update = async_track_point_in_time.call_args[0][2]
    assert next_update == in_5_minutes
    assert (
        hass.states.get(f"{Platform.BINARY_SENSOR}.test3").attributes[ATTR_NEXT_TOGGLE]
        == in_5_minutes
    )
    await async_clenaup(hass)


async def test_set(hass):
    """Test set service."""
    schedule1 = [{CONF_FROM: "01:02:03", CONF_TO: "04:05:06"}]
    schedule2 = [{CONF_FROM: "07:08:09", CONF_TO: "10:11:12"}]
    entity_id = f"{Platform.BINARY_SENSOR}.my_test"

    await setup_entity(hass, "My Test", schedule1)
    assert hass.states.get(entity_id).attributes[CONF_SCHEDULE] == schedule1

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET,
        {ATTR_ENTITY_ID: entity_id, CONF_SCHEDULE: schedule2},
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes[CONF_SCHEDULE] == schedule2
    await async_clenaup(hass)


@pytest.mark.parametrize(
    ["schedule"],
    [
        (
            [
                {
                    CONF_FROM: "04:05:05",
                    CONF_TO: "07:08:09",
                },
                {
                    CONF_FROM: "01:02:03",
                    CONF_TO: "04:05:06",
                },
            ],
        ),
        (
            [
                {
                    CONF_FROM: "07:08:09",
                    CONF_TO: "01:02:04",
                },
                {
                    CONF_FROM: "01:02:03",
                    CONF_TO: "04:05:06",
                },
            ],
        ),
    ],
    ids=["overlap", "overnight_overlap"],
)
async def test_invalid_set(hass, schedule):
    """Test invalid input to set method."""
    entity_id = f"{Platform.BINARY_SENSOR}.my_test"
    await setup_entity(hass, "My Test", [])
    with pytest.raises(ValueError) as excinfo:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET,
            {ATTR_ENTITY_ID: entity_id, CONF_SCHEDULE: schedule},
            blocking=True,
        )
    assert "overlap" in str(excinfo.value)
    await async_clenaup(hass)

@pytest.mark.parametrize(
    ["utc"],
    [(True,), (False,)],
    ids=["utc", "local"],
)
async def test_utc(hass, freezer: FrozenDateTimeFactory, utc: bool):
    """Test utc schedule."""
    utc_time = datetime.datetime(2023, 5, 30, 12, tzinfo=pytz.utc)  # 12pm
    local_time = utc_time.astimezone(pytz.timezone('US/Eastern'))  # 7am
    offset = utc_time.timestamp() - local_time.replace(tzinfo=None).timestamp()  # 5h
    freezer.move_to(local_time)
    entity_id = f"{Platform.BINARY_SENSOR}.my_test"
    await setup_entity(
        hass,
        "My Test",
        [
            {
                CONF_FROM: "12:00:00",
                CONF_TO: "12:00:01",
            },
        ],
        utc,
    )
    assert hass.states.get(entity_id).state == STATE_ON if utc else STATE_OFF
    next_toogle_timestamp = hass.states.get(entity_id).attributes[ATTR_NEXT_TOGGLE].timestamp()
    assert next_toogle_timestamp == utc_time.timestamp() + 1 if utc else offset
    await async_clenaup(hass)
