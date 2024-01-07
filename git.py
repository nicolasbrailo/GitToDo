""" Git integration: will commit and push a file to git once a callback is triggered """

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

import logging
import pathlib
import subprocess

log = logging.getLogger(__name__)


class GitIntegration:
    """ Listens for a callback to on_todo_file_updated(). When called, it will
    schedule a commit a todo_filepath and push it to a remote repo. The commit
    and push are scheduled in $commit_delay_secs, so that multiple changes to
    todo_filepath may be coalesced into a single commit. A new call to
    on_todo_file_updated() will reset the commit schedule. """

    def __init__(self, todo_filepath, commit_delay_secs=30):
        path = pathlib.Path(todo_filepath)
        self._todo_filename = path.name
        self._git_path = path.parent.resolve()
        # Don't commit changes immediately, wait a while to give the user the opportunity to
        # make multiple changes in a single commit
        self._commit_delay_secs = commit_delay_secs
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()

    def on_todo_file_updated(self):
        """ Callback to notify the file under monitoring was changed """
        if self._commit_delay_secs is None:
            self._commit()
        else:
            log.info(
                "ToDo change notification, will schedule a commit in %s seconds",
                self._commit_delay_secs)
            self._scheduler.remove_all_jobs()
            self._scheduler.add_job(
                self._commit,
                'date',
                run_date=datetime.now() +
                timedelta(
                    seconds=self._commit_delay_secs))

    def _commit(self):
        def run(cmd):
            result = subprocess.run(
                cmd,
                cwd=self._git_path,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            log.debug('Exec %s', cmd)
            if result.returncode != 0:
                stdout = result.stdout.decode('utf-8')
                stderr = result.stderr.decode('utf-8')
                raise RuntimeError(
                    f'Failed to exec {cmd} cwd={self._git_path}' +
                    f'\nstderr:\n{stderr}\nstdout\n{stdout}')

        log.info("Will commit and push changes to ToDo file")
        run(f'git add {self._todo_filename}')
        run('git commit -m "ToDo file updated by GitToDo"')
        run('git push')
