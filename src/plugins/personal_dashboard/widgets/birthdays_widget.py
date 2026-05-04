from datetime import datetime, timedelta

import icalendar
import recurring_ical_events
import requests

_BIRTHDAY_TITLE_KEYWORDS = ("birthday", "geburtstag")
_DEFAULT_MAX_BIRTHDAYS = 8


class BirthdaysWidget:
    """Fetches and filters upcoming birthdays from an ICS feed."""

    @staticmethod
    def get_data(settings, tz, max_birthdays=_DEFAULT_MAX_BIRTHDAYS):
        """Fetch and filter upcoming birthday events from an ICS URL.

        Works with any VCALENDAR-based feed that uses RRULE:FREQ=YEARLY for
        recurring birthdays, including the Google Calendar "Birthdays" feed.
        """
        ics_url = settings.get("birthdaysIcsUrl", "").strip()
        if not ics_url:
            return []

        lookahead_days = int(settings.get("birthdayLookaheadDays", 60))

        resp = requests.get(ics_url, timeout=15)
        resp.raise_for_status()
        cal = icalendar.Calendar.from_ical(resp.content)

        today = datetime.now(tz).date()
        end_date = today + timedelta(days=lookahead_days)

        # Use naive datetimes for recurring_ical_events (same pattern as
        # the calendar plugin).
        start_range = datetime(today.year, today.month, today.day)
        end_range = datetime(end_date.year, end_date.month, end_date.day)

        events = recurring_ical_events.of(cal).between(start_range, end_range)

        birthdays = []
        for event in events:
            name = str(event.get("summary", "Unknown"))
            name_lc = name.lower()
            if not any(keyword in name_lc for keyword in _BIRTHDAY_TITLE_KEYWORDS):
                continue

            dtstart = event.get("dtstart")
            if dtstart is None:
                continue

            event_date = dtstart.dt
            # All-day events give a date; timed events give a datetime.
            if hasattr(event_date, "date"):
                event_date = event_date.date()

            days_until = (event_date - today).days
            if days_until == 0:
                when = "Today!"
            elif days_until == 1:
                when = "Tomorrow"
            else:
                when = f"in {days_until} days"

            birthdays.append(
                {
                    "name": name,
                    "date": f"{event_date.day} {event_date.strftime('%b')}",
                    "days_until": days_until,
                    "when": when,
                }
            )

        birthdays.sort(key=lambda x: x["days_until"])
        return birthdays[:max_birthdays]
