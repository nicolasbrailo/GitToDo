""" ToDo list Telegram bot: integrates a file-backed ToDo list with a Telegram set of commands """

from md_helpers import (md_create_if_not_exists,
                        md_get_all,
                        md_get_sections,
                        md_get_section_contents,
                        md_add_to_section,
                        md_mark_done)
from pytelegrambot import TelegramLongpollBot
from reminders import guess_reminder_date, mark_for_reminder_date, get_reminder_date_if_set

import json
import logging
import os

log = logging.getLogger(__name__)


class TelBot(TelegramLongpollBot):
    """ Listen to a set of commands on Telegram, and apply them to a list of ToDos backed
    by a Markdown file """

    def __init__(self, tok, poll_interval_secs,
                 accepted_chat_ids,
                 todo_filepath,
                 on_todo_file_updated,
                 on_reminder_todo_added,
                 on_reminder_todo_marked_done):
        self._on_todo_file_updated = on_todo_file_updated
        self._on_reminder_todo_marked_done = on_reminder_todo_marked_done
        self._on_reminder_todo_added = on_reminder_todo_added
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
        ]
        super().__init__(tok, self._accepted_chat_ids, poll_interval_secs=poll_interval_secs, cmds=cmds, terminate_on_unauthorized_access=True)

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
        for cid in self._accepted_chat_ids:
            self.send_message(cid, f'Git op fail, manual fix will be needed {msg}')

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
            log.info("User sent reminder we can't parse for %s: %s", todo.strip(), str(ex))

        if maybe_reminder is not None:
            log.info("ToDo will have reminder @ %s", maybe_reminder)
            confirm_msg = f"OK. Set reminder for {maybe_reminder}"
            todo = mark_for_reminder_date(todo, maybe_reminder)

        md_add_to_section(self._todo_filepath, section, todo)
        self.send_message(msg['from']['id'], confirm_msg)
        self._notify_todo_file_updated()
        self._on_reminder_todo_added(maybe_reminder, todo)

    def _mark_done(self, _bot, msg):
        try:
            num = int(msg['cmd_args'][0])
        except (KeyError, ValueError):
            self.send_message(msg['from']['id'], "Can't find ToDo number")
            return

        log.info("Mark ToDo #%s done", num)
        try:
            deleted_line = md_mark_done(self._todo_filepath, num)
        except IndexError:
            self.send_message(msg['from']['id'], f"ToDo {num} doesn't exist")
            return

        if deleted_line is None:
            self.send_message(
                msg['from']['id'],
                f"ToDo #{num} can't be deleted")
            return

        try:
            self._notify_todo_file_updated()
        except:
            log.error("ToDo file updated listener failed", exc_info=True)

        reminder_date = get_reminder_date_if_set(deleted_line)
        if reminder_date is None:
            self.send_message(msg['from']['id'], "OK")
        else:
            log.info("Deleted ToDo #%s had a reminder set for %s", num, reminder_date)
            self.send_message(msg['from']['id'], f"OK. Also removed reminder set for {reminder_date} - {deleted_line}")
            self._on_reminder_todo_marked_done(reminder_date, deleted_line)
