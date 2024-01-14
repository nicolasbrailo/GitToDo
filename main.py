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
from reminders import ReminderScheduler
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

# Throw on any missing cfg key
commit_delay = cfg['commit_delay_secs'] if 'commit_delay_secs' in cfg else None
git = GitIntegration(cfg['todo_filepath'], commit_delay)
reminders = ReminderScheduler(cfg['todo_filepath'])

def on_file_updated():
    git.on_todo_file_updated()
    reminders.reload_reminders_from_file()

bot = TelBot(cfg['tok'],
             cfg['poll_interval'],
             cfg['accepted_chat_ids'],
             cfg['todo_filepath'],
             on_file_updated)

git.register_failed_git_op_cb(bot.on_failed_git_op)
reminders.register_sender(bot)


log.info(
    "Running GitToDo service. Monitoring ToDo file @ %s",
    cfg['todo_filepath'])
log.info("Stop with `kill %s` or Ctrl-C", os.getpid())
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    log.info("User requested service stop")
