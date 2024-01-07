from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

import logging
import pathlib
import subprocess

log = logging.getLogger(__name__)

class GitIntegration:
    def __init__(self, todo_filepath, commit_delay_secs=30):
        p = pathlib.Path(__file__)
        self._todo_filename = p.name
        self._git_path = p.parent.resolve()
        # Don't commit changes immediately, wait a while to give the user the opportunity to
        # make multiple changes in a single commit
        self._commit_delay_secs = commit_delay_secs
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()

    def on_todo_file_updated(self):
        if self._commit_delay_secs is None:
            self._commit()
        else:
            log.info("ToDo change notification, will schedule a commit in %s seconds", self._commit_delay_secs)
            self._scheduler.remove_all_jobs()
            self._scheduler.add_job(self._commit, 'date', run_date=datetime.now() + timedelta(seconds=self._commit_delay_secs))

    def _commit(self):
        def run(cmd):
            result = subprocess.run(cmd, cwd=self._git_path,
                                    shell=True, check=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                stdout = result.stdout.decode('utf-8')
                stderr = result.stderr.decode('utf-8')
                raise RuntimeError(f'Failed to exec {cmd} cwd={self._git_path}' +
                                   f'\nstderr:\n{stderr}\nstdout\n{stdout}')

        log.info("Will commit and push changes to ToDo file")
        run(f'git add {self._todo_filename}')
        run(f'git commit -m "ToDo file updated by GitToDo"')
        run(f'git push')

