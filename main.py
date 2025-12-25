""" Manage a git repo as a ToDo list with Telegram integration """

import json
import logging
import os
import pathlib
import sys
import threading
import time

from flask import Flask, Response, request, send_from_directory

sys.path.append(os.path.join(pathlib.Path(__file__).parent.resolve(), "./PyTelegramBot"))

from telegram import TelBot
from reminders import ReminderScheduler, guess_reminder_date, mark_for_reminder_date, normalize_reminder_token
from git import GitIntegration
from md_helpers import (md_get_all,
                        md_get_sections,
                        md_get_section_contents,
                        md_add_to_section,
                        md_mark_done,
                        md_move_todo)

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

# Create todo file if it doesn't exist
pathlib.Path(cfg['todo_filepath']).touch(exist_ok=True)

# Throw on any missing cfg key
commit_delay = cfg['commit_delay_secs'] if 'commit_delay_secs' in cfg else None
git = GitIntegration(cfg['todo_filepath'], commit_delay)
reminders = ReminderScheduler(cfg['todo_filepath'])


def on_file_updated():
    """ Trampoline for all actions required on file update """
    git.on_todo_file_updated()
    reminders.reload_reminders_from_file()


bot = TelBot(cfg['tok'],
             cfg['short_poll_interval'],
             cfg['long_poll_interval'],
             cfg['accepted_chat_ids'],
             cfg['todo_filepath'],
             on_file_updated,
             git.pull,
             git.commit)

git.register_failed_git_op_cb(bot.on_failed_git_op)
reminders.register_sender(bot)

# Flask web UI
app = Flask(__name__, static_folder='www', static_url_path='/static')


def process_command(cmd_input):
    """ Process a command and return (success, result) tuple """
    cmd_input = cmd_input.strip()
    if not cmd_input:
        return (False, 'Error: No command provided')

    if cmd_input.startswith('/'):
        cmd_input = cmd_input[1:]
    parts = cmd_input.split()
    if not parts:
        return (False, 'Error: Empty command')

    cmd = parts[0].lower()
    args = parts[1:]

    try:
        if cmd == 'ls':
            if args:
                result = md_get_section_contents(cfg['todo_filepath'], args[0])
            else:
                result = md_get_all(cfg['todo_filepath'])
        elif cmd == 'sections':
            result = md_get_sections(cfg['todo_filepath'])
        elif cmd == 'add':
            if len(args) < 2:
                return (False, 'Error: Usage /add <section> <todo>')
            section = args[0]
            todo = normalize_reminder_token(' '.join(args[1:]))
            result = 'OK'
            try:
                maybe_reminder = guess_reminder_date(todo)
            except ValueError as ex:
                maybe_reminder = None
                result = f"ToDo added. Detected a reminder, but can't parse it: {ex}"
            if maybe_reminder is not None:
                result = f"OK. Set reminder for {maybe_reminder}"
                todo = mark_for_reminder_date(todo, maybe_reminder)
            md_add_to_section(cfg['todo_filepath'], section, todo)
            on_file_updated()
        elif cmd == 'done':
            if not args:
                return (False, 'Error: Usage /done <number>')
            try:
                todo_nums = [int(n) for n in args]
                todo_nums.sort(reverse=True)
            except ValueError:
                return (False, f"Error: Can't parse todo numbers: {args}")
            action_report = []
            for num in todo_nums:
                try:
                    deleted_line = md_mark_done(cfg['todo_filepath'], num)
                except IndexError:
                    action_report.append(f"ToDo {num} doesn't exist")
                    continue
                if deleted_line is None:
                    action_report.append(f"ToDo #{num} can't be deleted")
                else:
                    action_report.append(f"ToDo #{num} deleted")
                    on_file_updated()
            result = '\n'.join(action_report) if action_report else 'Nothing changed?'
        elif cmd == 'pull':
            git.pull()
            result = 'Pull complete'
        elif cmd == 'push':
            git.commit()
            result = 'Push complete'
        else:
            return (False, f'Error: Unknown command: {cmd}')

        return (True, result)
    except Exception as ex:
        log.error('Error processing command', exc_info=True)
        return (False, f'Error: {ex}')


@app.route('/raw')
def raw_page():
    """ Serve the todo file as plain text """
    with open(cfg['todo_filepath'], 'r', encoding='utf-8') as f:
        content = f.read()
    return Response(content, mimetype='text/plain')


@app.route('/cmd', methods=['GET', 'POST'])
def cmd_page():
    """ Process commands like the Telegram bot """
    if request.method == 'GET':
        return Response('''Commands:
  /ls [section]          - List all ToDos (optionally in a section)
  /sections              - List all sections
  /add <section> <todo>  - Add a ToDo to a section
  /done <number>         - Mark a ToDo as complete
  /pull                  - Force git pull
  /push                  - Force git commit and push

Usage: POST to /cmd with 'cmd' parameter
Example: curl -X POST -d "cmd=/ls" http://localhost:5000/cmd
''', mimetype='text/plain')

    cmd_input = request.form.get('cmd', '')
    success, result = process_command(cmd_input)
    status = 200 if success else 400
    return Response(result, mimetype='text/plain'), status


@app.route('/telegram_test')
def telegram_test_page():
    """ HTML page to test Telegram commands """
    return send_from_directory('www', 'telegram_test.html')


@app.route('/api/cmd', methods=['POST'])
def api_cmd():
    """ API endpoint to process commands and return JSON """
    try:
        data = request.get_json()
        cmd_input = data.get('cmd', '')
        success, result = process_command(cmd_input)
        return {'success': success, 'result': result}
    except Exception as ex:
        return {'success': False, 'result': str(ex)}


def parse_todo_file():
    """ Parse the todo file into sections with their todos """
    with open(cfg['todo_filepath'], 'r', encoding='utf-8') as f:
        lines = f.readlines()

    sections = []
    current_section = None

    for i, line in enumerate(lines):
        if line.startswith('## '):
            if current_section:
                sections.append(current_section)
            current_section = {
                'name': line[3:].strip(),
                'todos': []
            }
        elif current_section and line.strip() and not line.startswith('#'):
            todo_text = line.strip()
            if todo_text.startswith('* '):
                todo_text = todo_text[2:]
            current_section['todos'].append({
                'line_num': i,
                'text': todo_text
            })

    if current_section:
        sections.append(current_section)

    return sections

@app.route('/')
def todos_page():
    """ Interactive todo list page """
    return send_from_directory('www', 'index.html')


@app.route('/api/todos')
def api_todos():
    """ API endpoint to get all todos as JSON """
    sections = parse_todo_file()
    return {'sections': sections}


@app.route('/api/done/<int:line_num>', methods=['POST'])
def api_done(line_num):
    """ API endpoint to mark a todo as done """
    try:
        result = md_mark_done(cfg['todo_filepath'], line_num)
        if result is None:
            return {'success': False, 'error': 'Cannot delete this line'}
        on_file_updated()
        return {'success': True}
    except Exception as ex:
        return {'success': False, 'error': str(ex)}


@app.route('/api/move', methods=['POST'])
def api_move():
    """ API endpoint to move a todo up or down """
    try:
        data = request.get_json()
        line_num = data['line']
        direction = data['direction']
        result = md_move_todo(cfg['todo_filepath'], line_num, direction)
        if not result:
            return {'success': False, 'error': 'Cannot move this todo'}
        on_file_updated()
        return {'success': True}
    except Exception as ex:
        return {'success': False, 'error': str(ex)}


@app.route('/api/add', methods=['POST'])
def api_add():
    """ API endpoint to add a new todo """
    try:
        data = request.get_json()
        section = data['section']
        text = normalize_reminder_token(data['text'])
        try:
            maybe_reminder = guess_reminder_date(text)
            if maybe_reminder is not None:
                text = mark_for_reminder_date(text, maybe_reminder)
        except ValueError:
            pass  # Ignore reminder parsing errors for API
        md_add_to_section(cfg['todo_filepath'], section, text)
        on_file_updated()
        return {'success': True}
    except Exception as ex:
        return {'success': False, 'error': str(ex)}


def run_flask():
    """ Run Flask in a separate thread """
    app.run(host='0.0.0.0', port=4300, debug=False, use_reloader=False)


flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

log.info(
    "Running GitToDo service. Monitoring ToDo file @ %s",
    cfg['todo_filepath'])
log.info("Web UI at http://0.0.0.0:5000/ | Raw: /raw | Commands: /cmd | Test: /telegram_test")
log.info("Stop with `kill %s` or Ctrl-C", os.getpid())
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    log.info("User requested service stop")
