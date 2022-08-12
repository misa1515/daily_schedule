"""Schedule and time range logic."""
from __future__ import annotations

import datetime

import voluptuous as vol

from .const import CONF_TO, CONF_FROM


class TimeRange:
    """Time range with start and end (since "from" is a reserved word)."""

    def __init__(self, start: str, end: str) -> None:
        """Initialize the object."""
        self.start: datetime.time = datetime.time.fromisoformat(start)
        self.end: datetime.time = datetime.time.fromisoformat(end)

    def containing(self, time: datetime.time) -> bool:
        """Check if the time is inside the range."""
        # If the range crosses the day boundary.
        if self.end <= self.start:
            return self.start <= time or time < self.end

        return self.start <= time < self.end

    def to_dict(self) -> dict[str, str]:
        """Serialize the object as a dict."""
        return {
            CONF_FROM: self.start.isoformat(),
            CONF_TO: self.end.isoformat(),
        }


class Schedule:
    """List of TimeRange."""

    def __init__(self, schedule: list[dict[str, str]]) -> None:
        """Create a list of TimeRanges representing the schedule."""
        self._schedule = [
            TimeRange(time_range[CONF_FROM], time_range[CONF_TO])
            for time_range in schedule
        ]
        self._schedule.sort(key=lambda time_range: time_range.start)
        self._validate()

    def _validate(self) -> None:
        """Validate the schedule."""
        # Any schedule with zero or a single entry is valid.
        if len(self._schedule) <= 1:
            return

        # Check all except the last range of the schedule.
        for i in range(len(self._schedule) - 1):
            # The end should be between starts of current and next ranges.
            # Note that adjusted ranges are allowed.
            if (
                not self._schedule[i].start
                < self._schedule[i].end
                <= self._schedule[i + 1].start
            ):
                raise vol.Invalid("Invalid input schedule")

        # Check the last time range.
        if self._schedule[-1].end <= self._schedule[-1].start:
            # If it crosses the day boundary, check overlap with 1st range.
            if self._schedule[-1].end > self._schedule[0].start:
                raise vol.Invalid("Invalid input schedule")

    def containing(self, time: datetime.time) -> bool:
        """Check if the time is inside the range."""
        for time_range in self._schedule:
            if time_range.containing(time):
                return True
        return False

    def to_list(self) -> list[dict[str, str]]:
        """Serialize the object as a list."""
        return [time_range.to_dict() for time_range in self._schedule]

    def next_update(self, date: datetime.datetime) -> datetime.datetime | None:
        """Schedule a timer for the point when the state should be changed."""
        if not self._schedule:
            return None

        time = date.time()
        today = date.date()
        prev = datetime.time()  # Midnight.

        # Get all timestamps (de-duped and sorted).
        timestamps = [time_range.start for time_range in self._schedule] + [
            time_range.end for time_range in self._schedule
        ]
        timestamps = list(set(timestamps))
        timestamps.sort()

        # Find the smallest timestamp which is bigger than time.
        for current in timestamps:
            if prev <= time < current:
                return datetime.datetime.combine(
                    today,
                    current,
                )
            prev = current

        # Time is bigger than all timestamps. Use tomorrow's 1st timestamp.
        return datetime.datetime.combine(
            today + datetime.timedelta(days=1),
            timestamps[0],
        )
