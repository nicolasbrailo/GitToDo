import logging
import os
import pathlib
import sys
import time
import json

sys.path.append(os.path.join(pathlib.Path(__file__).parent.resolve(), "./PyTelegramBot"))
from telegram import TelBot

root = logging.getLogger()
root.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root.addHandler(handler)

log = logging.getLogger(__name__)


with open('config.json', 'r') as fp:
    cfg = json.loads(fp.read())
    bot = TelBot(cfg['tok'], cfg['poll_interval'], cfg['accepted_chat_ids'], cfg['todo_filepath'])

while True:
    log.info("RUNNING")
    time.sleep(4)


