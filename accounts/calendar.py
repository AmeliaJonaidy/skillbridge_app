import calendar
from collections import defaultdict
from datetime import datetime, timedelta

from django.utils import timezone


def _parse_date(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def _parse_month(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError):
        return fallback.replace(day=1)


def build_month_calendar(interviews, month_value=None, selected_value=None):
    today = timezone.localdate()
    month_date = _parse_month(month_value, today)
    selected_date = _parse_date(selected_value, today)
    month = calendar.Calendar(firstweekday=6)
    events_by_date = defaultdict(list)

    for interview in interviews:
        event_date = timezone.localtime(interview.scheduled_start).date()
        events_by_date[event_date].append(interview)

    weeks = []
    for week in month.monthdatescalendar(month_date.year, month_date.month):
        weeks.append([
            {
                "date": day,
                "day": day.day,
                "in_month": day.month == month_date.month,
                "is_today": day == today,
                "is_selected": day == selected_date,
                "events": events_by_date.get(day, []),
            }
            for day in week
        ])

    previous_month = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_date.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)
    return {
        "month_label": month_date.strftime("%B %Y"),
        "month": month_date,
        "row_count": len(weeks),
        "previous_month": previous_month,
        "next_month": next_month,
        "selected_date": selected_date,
        "selected_events": events_by_date.get(selected_date, []),
        "weekdays": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "weeks": weeks,
    }
