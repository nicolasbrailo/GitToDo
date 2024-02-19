""" ToDo list Telegram bot: integrates a file-backed ToDo list with a Telegram set of commands """

import logging
from reminders import guess_reminder_date, mark_for_reminder_date, get_reminder_date_if_set
from pytelegrambot import TelegramLongpollBot
from md_helpers import (md_create_if_not_exists,
                        md_get_all,
                        md_get_sections,
                        md_get_section_contents,
                        md_add_to_section,
                        md_mark_done)

log = logging.getLogger(__name__)


class TelBot(TelegramLongpollBot):
    """ Listen to a set of commands on Telegram, and apply them to a list of ToDos backed
    by a Markdown file """

    def __init__(self, tok, poll_interval_secs,
                 accepted_chat_ids,
                 todo_filepath,
                 on_todo_file_updated,
                 force_pull_cb,
                 force_push_cb):
        self._on_todo_file_updated = on_todo_file_updated
        self._force_pull_cb = force_pull_cb
        self._force_push_cb = force_push_cb
        self._accepted_chat_ids = accepted_chat_ids
        self._todo_filepath = todo_filepath
        md_create_if_not_exists(self._todo_filepath)

        cmds = [
            ('ls',
             "Use: /ls [section] - List all ToDos [in section]",
             self._ls),
            ('sections',
             'List sections',
             self._sects),
            ('add',
             'Add ToDo. Use: /add <section> <ToDo>',
             self._add),
            ('done',
             'Mark complete. Use: /done <number>',
             self._mark_done),
            ('pull',
             'Force git pull',
             self._force_pull),
            ('push',
             'Force commit and push, in case external changes to files where not pushed',
             self._force_push),
        ]
        super().__init__(
            tok,
            self._accepted_chat_ids,
            poll_interval_secs=poll_interval_secs,
            cmds=cmds,
            terminate_on_unauthorized_access=True)

    def _notify_todo_file_updated(self):
        try:
            self._on_todo_file_updated()
        except BaseException:  # pylint: disable=broad-exception-caught
            # Never leak an exception up, an error here is not this class'
            # responsibility
            log.error(
                'Error processing callback for ToDo file updated',
                exc_info=True)

    def on_bot_connected(self, bot):
        """ Called by super() """
        log.info('Connected to Telegram bot %s', bot.bot_info['first_name'])

    def on_bot_received_message(self, msg):
        """ Called by super() """
        log.info('Telegram bot received a message: %s', msg)

    def on_failed_git_op(self, msg):
        """ Notify bot of a failed git op, to notify a user """
        for cid in self._accepted_chat_ids:
            self.send_message(
                cid, f'Git op fail, manual fix will be needed {msg}')

    def _ls(self, _bot, msg):
        if len(msg['cmd_args']) > 0:
            todo_list = md_get_section_contents(
                self._todo_filepath, msg['cmd_args'][0])
        else:
            todo_list = md_get_all(self._todo_filepath)
        self.send_message(msg['from']['id'], todo_list)

    def _sects(self, _bot, msg):
        self.send_message(
            msg['from']['id'],
            md_get_sections(
                self._todo_filepath))

    def _add(self, _bot, msg):
        section = msg['cmd_args'][0]
        todo = ' '.join(msg['cmd_args'][1:])
        log.info("Add ToDo to section %s", section)

        confirm_msg = 'OK'
        try:
            maybe_reminder = guess_reminder_date(todo)
        except ValueError as ex:
            maybe_reminder = None
            confirm_msg = f"ToDo added. Detected a reminder, but can't parse it: {ex}"
            log.info(
                "User sent reminder we can't parse for %s: %s",
                todo.strip(),
                str(ex))

        if maybe_reminder is not None:
            log.info("ToDo will have reminder @ %s", maybe_reminder)
            confirm_msg = f"OK. Set reminder for {maybe_reminder}"
            todo = mark_for_reminder_date(todo, maybe_reminder)

        md_add_to_section(self._todo_filepath, section, todo)
        self.send_message(msg['from']['id'], confirm_msg)
        self._notify_todo_file_updated()

    def _mark_done(self, _bot, msg):
        try:
            todo_nums = [int(n) for n in msg['cmd_args']]
            todo_nums.sort(reverse=True)
        except (KeyError, ValueError):
            self.send_message(
                msg['from']['id'],
                "Can't find ToDo[s] {msg['cmd_args']}")
            return

        # Reverse-sorting maintains todo line number while deleting
        action_report = []
        for num in todo_nums:
            log.info("Mark ToDo #%s done", num)
            try:
                deleted_line = md_mark_done(self._todo_filepath, num)
            except IndexError:
                action_report.append(f"ToDo {num} doesn't exist")
                continue

            if deleted_line is None:
                action_report.append(f"ToDo #{num} can't be deleted")
                continue

            try:
                self._notify_todo_file_updated()
            except BaseException:  # pylint: disable=broad-exception-caught
                log.error("ToDo file updated listener failed", exc_info=True)

            reminder_date = get_reminder_date_if_set(deleted_line)
            if reminder_date is None:
                action_report.append(f"ToDo #{num} deleted")
            else:
                log.info(
                    "Deleted ToDo #%s had a reminder set for %s",
                    num,
                    reminder_date)
                action_report.append(
                    f"ToDo #{num} deleted. Also removed reminder set for {reminder_date}")

        if len(action_report) == 0:
            self.send_message(msg['from']['id'], "Nothing changed?")
        elif len(action_report) == 1:
            self.send_message(msg['from']['id'], action_report[0])
        else:
            self.send_message(msg['from']['id'], "\n".join(action_report))

    def _force_pull(self, _bot, msg):
        log.info("User requested force push in command %s", msg)
        self._force_pull_cb()
        self.send_message(msg['from']['id'], "Pull complete")

    def _force_push(self, _bot, msg):
        log.info("User requested force push in command %s", msg)
        self._force_push_cb()
        self.send_message(msg['from']['id'], "Push complete")

    def send_reminder_msg(self, txt):
        """ Notify all registered users of a reminder triggering """
        for cid in self._accepted_chat_ids:
            self.send_message(cid, f'Reminder! {txt}')
