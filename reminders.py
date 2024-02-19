""" Helpers and schedulers to parse strings into dates, and set reminders based on them """

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
from datetime import timedelta
from md_helpers import md_get_all_todos
import logging
import re

log = logging.getLogger(__name__)

def _text_to_number(text):
    """ Got it from ChatGPT and fixed a few bugs, it's not very robust but it's good
    enough for reminders """
    if text is None:
        return 0

    if text.isdigit():
        return int(text)

    number_mapping = {
        'en': {
            'zero': 0,
            'one': 1,
            'two': 2,
            'three': 3,
            'four': 4,
            'five': 5,
            'six': 6,
            'seven': 7,
            'eight': 8,
            'nine': 9,
            'ten': 10,
            'eleven': 11,
            'twelve': 12,
            'thirteen': 13,
            'fourteen': 14,
            'fifteen': 15,
            'sixteen': 16,
            'seventeen': 17,
            'eighteen': 18,
            'nineteen': 19,
            'twenty': 20,
            'thirty': 30,
            'forty': 40,
            'fifty': 50,
            'sixty': 60,
            'seventy': 70,
            'eighty': 80,
            'ninety': 90},
        'es': {
            'cero': 0,
            'uno': 1,
            'dos': 2,
            'tres': 3,
            'cuatro': 4,
            'cinco': 5,
            'seis': 6,
            'siete': 7,
            'ocho': 8,
            'nueve': 9,
            'diez': 10,
            'once': 11,
            'doce': 12,
            'trece': 13,
            'catorce': 14,
            'quince': 15,
            'dieciséis': 16,
            'diecisiete': 17,
            'dieciocho': 18,
            'diecinueve': 19,
            'veinte': 20,
            'veintiuno': 21,
            'veintidós': 22,
            'veintitrés': 23,
            'veinticuatro': 24,
            'veinticinco': 25,
            'veintiseis': 26,
            'veintiséis': 26,
            'veintisiete': 27,
            'veintiocho': 28,
            'veintinueve': 29,
            'treinta': 30,
            'cuarenta': 40,
            'cincuenta': 50,
            'sesenta': 60,
            'setenta': 70,
            'ochenta': 80,
            'noventa': 90,
            'cien': 100,
            'doscientos': 200,
            'trescientos': 300,
            'cuatrocientos': 400,
            'quinientos': 500,
            'seiscientos': 600,
            'setecientos': 700,
            'ochocientos': 800,
            'novecientos': 900}}

    result = 0
    current_number = 0

    for lang in ['en', 'es']:
        for word in text.lower().split():
            if word in number_mapping[lang]:
                current_number += number_mapping[lang][word]
            elif word == 'hundred' and lang == 'en':
                current_number = 100 * current_number
            elif word in ('y', 'and'):
                continue
            else:
                result += current_number
                current_number = 0

        result += current_number
        if result != 0:
            return result

    return 0


def _extract_reminder(text, trigger_token):
    # Tokens to skip (eg if format is 'in two weeks', we don't care about 'in')
    TOKS_TO_IGNORE = ['in', 'at']

    # Find the position of the trigger_token
    trigger_position = text.find(trigger_token)

    if trigger_position == -1:
        return None

    # Extract the substring starting from the position after the trigger_token
    start_position = trigger_position + len(trigger_token)
    remaining_text = text[start_position:].strip()

    if not remaining_text:
        raise ValueError(f"Can't finder @reminder time in ToDo: '{text}'")

    # split by all whitespaces
    tokens = remaining_text.split()
    if len(tokens) == 0:
        raise ValueError(
            f"Can't finder @reminder time in {text}, reminder seems empty")

    # TODO: Need to consume as many tokens as possible, in case it's a number with spaces
    tok_0_is_num = _text_to_number(tokens[0]) != 0
    if not tok_0_is_num and not tokens[0].strip().lower() in TOKS_TO_IGNORE:
        return (tokens[0].strip().lower(), None)

    # Check if the next token is a number, if so we need a unit too (eg 2 days)
    if len(tokens) == 1:
        raise ValueError(
            f"Found reminder for {tokens[0]}, but can't find its unit of time")

    if tokens[0].strip().lower() in TOKS_TO_IGNORE and len(tokens) > 2:
        # If the first token is ignorable, return toks 2 and 3 (eg if format is
        # '@reminder in 2 weeks', then skip 'in' and return (2, weeks)
        return (tokens[1].strip().lower(), tokens[2].strip().lower())

    return (tokens[0].strip().lower(), tokens[1].strip().lower())


def _extract_unit_value_from_single_value(input_str):
    """ Try to break a line like '25th' into unit/value (25, th) """
    match = re.match(r'(\d+)(.*)', input_str)
    if match:
        digits = match.group(1).strip()
        rest = match.group(2).strip()
        return digits, rest
    return input_str, None



def _guess_reminder_date_from_value_and_unit(value, unit):
    ABSOLUTE_TIME_TOK = ['am', 'pm']
    MINUTES_TOK = ['minute', 'minutes', 'mins', 'min']
    HOURS_TOK = ['hrs', 'hr', 'hour', 'hours', 'horas', 'hora']
    DAYS_TOK = ['day', 'days', 'dia', 'dias']
    WEEKS_TOK = ['week', 'weeks', 'wk', 'wks', 'semanas']
    MONTHS_TOK = ['month', 'months', 'mes', 'meses']

    parsed_value = _text_to_number(value)
    if parsed_value == 0:
        raise ValueError(
            f"Expected {value} to be a number, parsed it to {parsed_value}")

    value = parsed_value
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
    elif unit.lower() in ABSOLUTE_TIME_TOK:
        if unit.lower() == 'am':
            target_time = target_time.replace(hour=int(value), minute=0, second=0, microsecond=0)
        else:
            target_time = target_time.replace(hour=int(value)+12, minute=0, second=0, microsecond=0)
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
        target_time = datetime(
            current_time.year,
            current_time.month,
            current_time.day,
            8,
            0,
            0)
    elif input_str.lower() in AFTERNOON_TOKS:
        target_time = datetime(
            current_time.year,
            current_time.month,
            current_time.day,
            13,
            0,
            0)
    elif input_str.lower() in NIGHT_TOKS:
        target_time = datetime(
            current_time.year,
            current_time.month,
            current_time.day,
            20,
            0,
            0)
    elif input_str.lower() in TOMORROW_TOKS:
        target_time = datetime(
            current_time.year,
            current_time.month,
            current_time.day + 1,
            8,
            0,
            0)
    elif input_str.lower() in WEEKEND_TOKS:
        if current_time.weekday() == 5:  # If today is Saturday
            target_time = datetime(current_time.year,
                                   current_time.month,
                                   current_time.day,
                                   9,
                                   0,
                                   0) + timedelta(days=7)
        else:
            target_time = datetime(
                current_time.year,
                current_time.month,
                current_time.day,
                9,
                0,
                0)
            # Calculate days until Saturday
            days_until_saturday = (5 - current_time.weekday() + 7) % 7
            target_time += timedelta(days=days_until_saturday)

    if target_time is None:
        return None

    if current_time > target_time:
        target_time += timedelta(days=1)

    return target_time


DEFAULT_REMINDER_TOK = '@remindme'
DEFAULT_REMINDER_SET_TOK = '@remind_at'


def guess_reminder_date(todo_ln, reminder_tok=None):
    """ Try to parse an absolute date from a user proivded one """
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


def mark_for_reminder_date(line, date):
    """ Append a well known token with the absolute date at which a reminder needs to trigger.
    This is done so that we don't have to guess dates all over again: when a ToDo is first
    added, we'll search for a reminder. If one is found, an absolute date is saved. On todo file
    (re)load we just need to look for the absolute date token, and a good-known date format. """
    return f'{line.strip()} [{DEFAULT_REMINDER_SET_TOK} {date}]'


def _try_parse_reminder_date(date_string):
    formats_to_try = [
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d']

    for date_format in formats_to_try:
        try:
            datetime_object = datetime.strptime(date_string, date_format)
            return datetime_object
        except ValueError:
            pass

    return None


def get_reminder_date_if_set(todo):
    """ Parse a log line. If the line has a @reminder token, will try to parse the date """
    reminder_set_tok = f'[{DEFAULT_REMINDER_SET_TOK} '
    if reminder_set_tok not in todo:
        return None

    start = todo.find(reminder_set_tok) + len(reminder_set_tok)
    end = todo.find(']', start)
    reminder_date = _try_parse_reminder_date(todo[start:end])

    if reminder_date is None:
        log.error("Found line with reminder set, but invalid date: %s", todo)
        return None

    return reminder_date


class ReminderScheduler:
    """ Manages reminders in a todo file, sends notifications when reminders trigger """

    def __init__(self, todo_filepath):
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()
        self._todo_filepath = todo_filepath
        self.reload_reminders_from_file()
        self._msg_sender = None

    def register_sender(self, msg_sender):
        """ Telegram bot - split from init to avoid init circular dep """
        self._msg_sender = msg_sender

    def reload_reminders_from_file(self):
        """ Reset and reload all reminders (useful if a file changes) """
        self._scheduler.remove_all_jobs()
        for todo in md_get_all_todos(self._todo_filepath):
            reminder_date = get_reminder_date_if_set(todo)
            if reminder_date is not None and reminder_date > datetime.now():
                self._on_reminder_todo_added(reminder_date, todo)

    def _on_reminder_todo_added(self, reminder_date, todo_ln):
        log.info("Will schedule reminder @ %s: %s", reminder_date, todo_ln)

        def send_reminder():
            log.info("Sending reminder %s", reminder_date)
            self._msg_sender.send_reminder_msg(todo_ln)

        self._scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(reminder_date)
        )
