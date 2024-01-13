from datetime import datetime
from datetime import timedelta
from md_helpers import md_get_all_todos
import logging
import re

log = logging.getLogger(__name__)

def _extract_reminder(text, trigger_token):
    # Find the position of the trigger_token
    trigger_position = text.find(trigger_token)

    if trigger_position == -1:
        return None

    # Extract the substring starting from the position after the trigger_token
    start_position = trigger_position + len(trigger_token)
    remaining_text = text[start_position:].strip()

    if not remaining_text:
        raise ValueError(f"Can't finder @reminder time in ToDo: '{text}'")

    # Use split(None, 1) to split by all whitespaces
    tokens = remaining_text.split(None, 1)
    if len(tokens) == 0:
        raise ValueError(f"Can't finder @reminder time in {text}, reminder seems empty")

    if not tokens[0].isdigit():
        return (tokens[0].strip().lower(), None)

    # Check if the next token is a number, if so we need a unit too (eg 2 days)
    if len(tokens) == 1:
        raise ValueError(f"Found reminder for {tokens[0]}, but can't find its unit of time")

    return (tokens[0].strip().lower(), tokens[1].strip().lower())


def _extract_unit_value_from_single_value(input_str):
    """ Try to break a line like '25th' into unit/value (25, th) """
    match = re.match(r'(\d+)(.*)', input_str)
    if match:
        digits = match.group(1).strip()
        rest = match.group(2).strip()
        return digits, rest
    else:
        return input_str, None

def _guess_reminder_date_from_value_and_unit(value, unit):
    MINUTES_TOK = ['minutes', 'mins']
    HOURS_TOK = ['hrs', 'hr', 'hour', 'hours', 'horas', 'hora']
    DAYS_TOK = ['day', 'days', 'dia', 'dias']
    WEEKS_TOK = ['week', 'weeks', 'wk', 'wks', 'semanas']
    MONTHS_TOK = ['month', 'months', 'mes', 'meses']

    if not value.isdigit():
        raise ValueError(f"Expected {value} to be a number")

    target_time = datetime.now()
    if unit.lower() in MINUTES_TOK:
        target_time += timedelta(minutes=int(value))
    elif unit.lower() in HOURS_TOK:
        target_time += timedelta(hours=int(value))
    elif unit.lower() in DAYS_TOK:
        target_time += timedelta(days=int(value))
    elif unit.lower() in WEEKS_TOK:
        target_time += timedelta(weeks=int(value))
    elif unit.lower() in MONTHS_TOK:
        target_time += timedelta(months=int(value))
    else:
        return None
    return target_time

def _guess_reminder_date_from_value_only(input_str):
    MORNING_TOKS = ['maniana', 'morning', 'early', 'temprano']
    AFTERNOON_TOKS = ['noon', 'afternoon']
    NIGHT_TOKS = ['noche', 'night', 'tonight', 'tarde']
    TOMORROW_TOKS = ['tomorrow', 'tmrw']
    WEEKEND_TOKS = ['weekend', 'finde']

    current_time = datetime.now()
    target_time = None
    if input_str.lower() in MORNING_TOKS:
        target_time = datetime(current_time.year, current_time.month, current_time.day, 8, 0, 0)
    elif input_str.lower() in AFTERNOON_TOKS:
        target_time = datetime(current_time.year, current_time.month, current_time.day, 13, 0, 0)
    elif input_str.lower() in NIGHT_TOKS:
        target_time = datetime(current_time.year, current_time.month, current_time.day, 20, 0, 0)
    elif input_str.lower() in TOMORROW_TOKS:
        print("X")
        target_time = datetime(current_time.year, current_time.month, current_time.day + 1, 8, 0, 0)
    elif input_str.lower() in WEEKEND_TOKS:
        if current_time.weekday() == 5:  # If today is Saturday
            target_time = datetime(current_time.year, current_time.month, current_time.day, 9, 0, 0) + timedelta(days=7)
        else:
            target_time = datetime(current_time.year, current_time.month, current_time.day, 9, 0, 0)
            days_until_saturday = (5 - current_time.weekday() + 7) % 7  # Calculate days until Saturday
            target_time += timedelta(days=days_until_saturday)

    if target_time is None:
        return None

    if current_time > target_time:
        target_time += timedelta(days=1)

    return target_time


DEFAULT_REMINDER_TOK='@remindme'
DEFAULT_REMINDER_SET_TOK = '@remind_at'

def guess_reminder_date(todo_ln, reminder_tok=None):
    if reminder_tok is None:
        reminder_tok = DEFAULT_REMINDER_TOK

    reminder = _extract_reminder(todo_ln, reminder_tok)
    if not reminder:
        return None

    value, unit = reminder

    if unit is None:
        value, unit = _extract_unit_value_from_single_value(value)

    if unit is None:
        return _guess_reminder_date_from_value_only(value)

    return _guess_reminder_date_from_value_and_unit(value, unit)


def mark_for_reminder_date(ln, date):
    return f'{ln.strip()} [{DEFAULT_REMINDER_SET_TOK} {date}]'


def _try_parse_reminder_date(date_string):
    formats_to_try = ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']

    for date_format in formats_to_try:
        try:
            datetime_object = datetime.strptime(date_string, date_format)
            return datetime_object
        except ValueError:
            pass

    return None

def get_reminder_date_if_set(todo):
    reminder_set_tok = f'[{DEFAULT_REMINDER_SET_TOK} '
    if not reminder_set_tok in todo:
        return None

    start = todo.find(reminder_set_tok) + len(reminder_set_tok)
    end = todo.find(']', start)
    reminder_date = _try_parse_reminder_date(todo[start:end])

    if reminder_date is None:
        log.error("Found line with reminder set, but invalid date: %s", todo)
        return None

    return reminder_date

def foreach_md_line_with_set_reminder(fpath, cb):
    for todo in md_get_all_todos(fpath):
        reminder_date = get_reminder_date_if_set(todo)
        if reminder_date is not None:
            cb(reminder_date, todo)

