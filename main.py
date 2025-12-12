""" Manage a git repo as a ToDo list with Telegram integration """

import json
import logging
import os
import pathlib
import sys
import threading
import time

from flask import Flask, Response, request, redirect
from html import escape as html_escape
from urllib.parse import quote, unquote

sys.path.append(os.path.join(pathlib.Path(__file__).parent.resolve(), "./PyTelegramBot"))

from telegram import TelBot
from reminders import ReminderScheduler, guess_reminder_date, mark_for_reminder_date
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
app = Flask(__name__)


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
            todo = ' '.join(args[1:])
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


@app.route('/telegram_test', methods=['GET', 'POST'])
def telegram_test_page():
    """ HTML page to test Telegram commands """
    if request.method == 'POST':
        cmd_input = request.form.get('cmd', '')
        success, result = process_command(cmd_input)
        return redirect(f'/telegram_test?response={quote(result)}')

    response = request.args.get('response', '')
    if response:
        response = html_escape(unquote(response))

    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Telegram Bot Test</title>
    <style>
        body {{ font-family: monospace; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
        h1 {{ color: #333; }}
        .commands {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .commands code {{ display: block; margin: 5px 0; }}
        form {{ margin: 20px 0; }}
        input[type="text"] {{ width: 100%; padding: 10px; font-family: monospace; font-size: 14px; box-sizing: border-box; }}
        button {{ padding: 10px 20px; background: #0088cc; color: white; border: none; cursor: pointer; margin-top: 10px; }}
        button:hover {{ background: #006699; }}
        .response {{ background: #e8f4e8; border: 1px solid #4a4; padding: 15px; border-radius: 5px; margin: 20px 0; white-space: pre-wrap; }}
        .response.empty {{ background: #f5f5f5; border-color: #ccc; color: #666; }}
    </style>
</head>
<body>
    <h1>Telegram Bot Test</h1>

    <div class="commands">
        <strong>Available Commands:</strong>
        <code>/ls [section]</code> - List all ToDos (optionally in a section)
        <code>/sections</code> - List all sections
        <code>/add &lt;section&gt; &lt;todo&gt;</code> - Add a ToDo to a section
        <code>/done &lt;number&gt;</code> - Mark a ToDo as complete
        <code>/pull</code> - Force git pull
        <code>/push</code> - Force git commit and push
    </div>

    <form method="POST">
        <input type="text" name="cmd" placeholder="Enter command, e.g. /ls" autofocus>
        <button type="submit">Send</button>
    </form>

    <h3>Response (as Telegram would send):</h3>
    <div class="response{' empty' if not response else ''}">{response if response else 'No response yet. Send a command above.'}</div>
</body>
</html>'''
    return Response(html, mimetype='text/html')


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
    sections = parse_todo_file()

    todos_html = ''
    for section in sections:
        todos_html += f'<div class="section"><h2>{html_escape(section["name"])}</h2>'
        todos_html += '<ul class="todo-list">'
        for idx, todo in enumerate(section['todos']):
            line_num = todo['line_num']
            text = html_escape(todo['text'])
            can_move_up = idx > 0
            can_move_down = idx < len(section['todos']) - 1

            todos_html += f'''<li data-line="{line_num}">
                <span class="todo-text">{text}</span>
                <span class="actions">
                    <button class="move-btn" onclick="moveTodo({line_num}, -1)" {'disabled' if not can_move_up else ''}>&#9650;</button>
                    <button class="move-btn" onclick="moveTodo({line_num}, 1)" {'disabled' if not can_move_down else ''}>&#9660;</button>
                    <button class="done-btn" onclick="confirmDone({line_num}, '{text.replace("'", "\\'")}')">Done</button>
                </span>
            </li>'''
        todos_html += '</ul>'
        todos_html += f'''<form class="add-form" onsubmit="addTodo(event, '{html_escape(section["name"])}')">
            <input type="text" placeholder="Add new todo..." required>
            <button type="submit">Add</button>
        </form>'''
        todos_html += '</div>'

    if not sections:
        todos_html = '<p class="empty">No sections yet. Add a todo using /add command.</p>'

    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>ToDo List</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #f5f5f5; }}
        h1 {{ color: #333; margin-bottom: 30px; }}
        .section {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .section h2 {{ margin: 0 0 15px 0; color: #444; font-size: 1.3em; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        .todo-list {{ list-style: none; padding: 0; margin: 0; }}
        .todo-list li {{ display: flex; align-items: center; padding: 12px 0; border-bottom: 1px solid #eee; }}
        .todo-list li:last-child {{ border-bottom: none; }}
        .todo-text {{ flex: 1; color: #333; }}
        .actions {{ display: flex; gap: 5px; }}
        .actions button {{ padding: 5px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }}
        .move-btn {{ background: #e0e0e0; color: #555; }}
        .move-btn:hover:not(:disabled) {{ background: #ccc; }}
        .move-btn:disabled {{ opacity: 0.3; cursor: not-allowed; }}
        .done-btn {{ background: #4CAF50; color: white; }}
        .done-btn:hover {{ background: #45a049; }}
        .add-form {{ display: flex; gap: 10px; margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; }}
        .add-form input {{ flex: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }}
        .add-form button {{ padding: 10px 20px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        .add-form button:hover {{ background: #1976D2; }}
        .empty {{ color: #666; text-align: center; padding: 40px; }}
        .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); justify-content: center; align-items: center; z-index: 1000; }}
        .modal.show {{ display: flex; }}
        .modal-content {{ background: white; padding: 25px; border-radius: 8px; max-width: 400px; text-align: center; }}
        .modal-content p {{ margin: 0 0 20px 0; color: #333; }}
        .modal-content .todo-preview {{ background: #f5f5f5; padding: 10px; border-radius: 4px; margin: 15px 0; font-family: monospace; }}
        .modal-buttons {{ display: flex; gap: 10px; justify-content: center; }}
        .modal-buttons button {{ padding: 10px 25px; border: none; border-radius: 4px; cursor: pointer; }}
        .cancel-btn {{ background: #e0e0e0; }}
        .confirm-btn {{ background: #f44336; color: white; }}
        nav {{ margin-bottom: 20px; }}
        nav a {{ color: #2196F3; margin-right: 15px; }}
    </style>
</head>
<body>
    <nav><a href="/">ToDos</a> <a href="/raw">Raw</a> <a href="/telegram_test">Commands</a></nav>
    <h1>ToDo List</h1>
    {todos_html}

    <div id="modal" class="modal">
        <div class="modal-content">
            <p>Mark this todo as done?</p>
            <div id="modal-todo" class="todo-preview"></div>
            <div class="modal-buttons">
                <button class="cancel-btn" onclick="closeModal()">Cancel</button>
                <button class="confirm-btn" onclick="doDelete()">Mark Done</button>
            </div>
        </div>
    </div>

    <script>
        let pendingDeleteLine = null;

        function confirmDone(lineNum, text) {{
            pendingDeleteLine = lineNum;
            document.getElementById('modal-todo').textContent = text;
            document.getElementById('modal').classList.add('show');
        }}

        function closeModal() {{
            document.getElementById('modal').classList.remove('show');
            pendingDeleteLine = null;
        }}

        function doDelete() {{
            if (pendingDeleteLine !== null) {{
                fetch('/api/done/' + pendingDeleteLine, {{ method: 'POST' }})
                    .then(r => r.json())
                    .then(data => {{
                        if (data.success) location.reload();
                        else alert('Error: ' + data.error);
                    }});
            }}
            closeModal();
        }}

        function moveTodo(lineNum, direction) {{
            fetch('/api/move', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ line: lineNum, direction: direction }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) location.reload();
                else alert('Error: ' + data.error);
            }});
        }}

        function addTodo(event, section) {{
            event.preventDefault();
            const input = event.target.querySelector('input');
            const text = input.value.trim();
            if (!text) return;

            fetch('/api/add', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ section: section, text: text }})
            }})
            .then(r => r.json())
            .then(data => {{
                if (data.success) location.reload();
                else alert('Error: ' + data.error);
            }});
        }}
    </script>
</body>
</html>'''
    return Response(html, mimetype='text/html')


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
        text = data['text']
        md_add_to_section(cfg['todo_filepath'], section, text)
        on_file_updated()
        return {'success': True}
    except Exception as ex:
        return {'success': False, 'error': str(ex)}


def run_flask():
    """ Run Flask in a separate thread """
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


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
