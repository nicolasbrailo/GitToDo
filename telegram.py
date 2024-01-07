import json
import logging
import os
import pathlib
import psutil
import sys

log = logging.getLogger(__name__)

from pytelegrambot import TelegramLongpollBot
from md_helpers import *

class TelBot(TelegramLongpollBot):
    def __init__(self, tok, poll_interval_secs,
                 accepted_chat_ids,
                 todo_filepath,
                 on_todo_file_updated=None):
        self._on_todo_file_updated = on_todo_file_updated
        self._accepted_chat_ids = accepted_chat_ids
        self._todo_filepath = todo_filepath
        md_create_if_not_exists(self._todo_filepath)

        cmds = [
            ('ls', 'Usage: /ls [section] - List all ToDos is section, or all ToDos everywhere if no section is provided. ', self._ls),
            ('sections', 'List sections', self._sects),
            ('add', 'Add ToDo. Use: /add <section> <ToDo>', self._add),
            ('done', 'Mark complete. Use: /done <number>', self._mark_done),
        ]
        super().__init__(tok, poll_interval_secs=poll_interval_secs, cmds=cmds)

    def _notify_todo_file_updated(self):
        if self._on_todo_file_updated is not None:
            try:
                self._on_todo_file_updated()
            except:
                # Never leak an exception up, an error here is not this class' responsibility
                log.error('Error processing callback for ToDo file updated', exc_info=True)

    def on_bot_connected(self, bot):
        log.info('Connected to Telegram bot %s', bot.bot_info['first_name'])

    def on_bot_received_message(self, msg):
        log.info('Telegram bot %s received a message: %s', bot.bot_info['first_name'], msg)

    def _validate_incoming_msg(self, msg):
        log.info('Received command %s', msg)
        try:
            valid = msg['from']['id'] in self._accepted_chat_ids
        except KeyError:
            valid = False
        if not valid:
            log.error('Unauthorized access detected %s', msg)
            smsg = json.dumps(msg)
            for cid in self._accepted_chat_ids:
                self.send_message(cid, f'Unauthorized access to bot {smsg}')
            # Terminating here means the message will remain unprocessed forever, and the
            # service will continue dying if restarted (as long as the message remains in the
            # Telegram servers)
            psutil.Process().terminate()

    def _ls(self, bot, msg):
        self._validate_incoming_msg(msg)
        if len(msg['cmd_args']) > 0:
            t = md_get_section_contents(self._todo_filepath, msg['cmd_args'][0])
        else:
            t = md_get_all(self._todo_filepath)
        self.send_message(msg['from']['id'], t)

    def _sects(self, bot, msg):
        self._validate_incoming_msg(msg)
        self.send_message(msg['from']['id'], md_get_sections(self._todo_filepath))

    def _add(self, bot, msg):
        self._validate_incoming_msg(msg)
        section = msg['cmd_args'][0]
        todo = ' '.join(msg['cmd_args'][1:])
        log.info("Add ToDo to section %s", section)
        md_add_to_section(self._todo_filepath, section, todo)
        self.send_message(msg['from']['id'], "OK")
        self._notify_todo_file_updated()

    def _mark_done(self, bot, msg):
        self._validate_incoming_msg(msg)
        try:
            num = int(msg['cmd_args'][0])
        except:
            self.send_message(msg['from']['id'], "Can't find ToDo number")
            return

        log.info("Mark ToDo #%s done", num)
        try:
            ok = md_mark_done(self._todo_filepath, num)
        except IndexError:
            self.send_message(msg['from']['id'], f"ToDo {num} doesn't exist")
            return

        if ok:
            self.send_message(msg['from']['id'], "OK")
        else:
            self.send_message(msg['from']['id'], f"ToDo #{num} can't be deleted")
        self._notify_todo_file_updated()

