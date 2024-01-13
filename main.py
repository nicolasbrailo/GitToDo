import logging
import os
import pathlib
import sys
import time
import json

sys.path.append(
    os.path.join(
        pathlib.Path(__file__).parent.resolve(),
        "./PyTelegramBot"))

from git import GitIntegration
from reminders import foreach_md_line_with_set_reminder
from telegram import TelBot


root = logging.getLogger()
root.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root.addHandler(handler)

log = logging.getLogger(__name__)


with open('config.json', 'r', encoding="utf-8") as fp:
    cfg = json.loads(fp.read())

def on_reminder_todo_added(reminder_date, todo_ln):
    print("TODO: schedule reminder @ ", reminder_date, todo_ln)

def on_reminder_todo_marked_done(reminder_date, removed_todo_ln):
    print("TODO: REMOVE reminder @ ", reminder_date, removed_todo_ln)

foreach_md_line_with_set_reminder(cfg['todo_filepath'], on_reminder_todo_added)

# Throw on any missing cfg key
commit_delay = cfg['commit_delay_secs'] if 'commit_delay_secs' in cfg else None
git = GitIntegration(cfg['todo_filepath'], commit_delay)

bot = TelBot(cfg['tok'],
             cfg['poll_interval'],
             cfg['accepted_chat_ids'],
             cfg['todo_filepath'],
             git.on_todo_file_updated,
             on_reminder_todo_added,
             on_reminder_todo_marked_done)

git.register_failed_git_op_cb(bot.on_failed_git_op)


log.info(
    "Running GitToDo service. Monitoring ToDo file @ %s",
    cfg['todo_filepath'])
log.info("Stop with `kill %s` or Ctrl-C", os.getpid())
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    log.info("User requested service stop")
