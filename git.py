""" Git integration: will commit and push a file to git once a callback is triggered """

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta

import logging
import pathlib
import subprocess

log = logging.getLogger(__name__)


def _run(cwd, cmd):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    log.debug('Exec %s', cmd)
    if result.returncode != 0:
        stdout = result.stdout.decode('utf-8')
        stderr = result.stderr.decode('utf-8')
        raise RuntimeError(
            f'Failed to exec {cmd} cwd={cwd}' +
            f'\nstderr:\n{stderr}\nstdout\n{stdout}')


class GitIntegration:
    """ Listens for a callback to on_todo_file_updated(). When called, it will
    schedule a commit a todo_filepath and push it to a remote repo. The commit
    and push are scheduled in $commit_delay_secs, so that multiple changes to
    todo_filepath may be coalesced into a single commit. A new call to
    on_todo_file_updated() will reset the commit schedule. """

    def __init__(self, todo_filepath, commit_delay_secs=300):
        path = pathlib.Path(todo_filepath)
        self._todo_filename = path.name
        self._git_path = path.parent.resolve()
        self._on_failed_git_op_cb = None
        # Don't commit changes immediately, wait a while to give the user the opportunity to
        # make multiple changes in a single commit
        self._commit_delay_secs = commit_delay_secs
        self._scheduler = BackgroundScheduler()
        self._scheduler.start()

        self._scheduler.add_job(
            self.pull,
            trigger=CronTrigger(hour=8, minute=0, second=0),
            id='morning_pull'
        )
        self._scheduler.add_job(
            self.pull,
            trigger=CronTrigger(hour=21, minute=0, second=0),
            id='night_pull'
        )

    def pull(self):
        """ Pull changes from remote """
        try:
            log.info("Pulling git...")
            _run(self._git_path, 'git pull')
        except (subprocess.CalledProcessError, RuntimeError) as ex:
            if self._on_failed_git_op_cb is not None:
                self._on_failed_git_op_cb(str(ex))
            raise

    def register_failed_git_op_cb(self, fail_git_op_cb):
        """ Callback to be invoked when a git operation fails """
        self._on_failed_git_op_cb = fail_git_op_cb

    def on_todo_file_updated(self):
        """ Callback to notify the file under monitoring was changed """
        if self._commit_delay_secs is None:
            self.commit()
        else:
            log.info(
                "ToDo change notification, will schedule a commit in %s seconds",
                self._commit_delay_secs)
            self._scheduler.remove_all_jobs()
            self._scheduler.add_job(
                self.commit,
                'date',
                run_date=datetime.now() +
                timedelta(
                    seconds=self._commit_delay_secs))

    def commit(self):
        """ Commit and push changes to managed repo """
        try:
            log.info("Will commit and push changes to ToDo file")
            # This order will only work with rebase
            _run(self._git_path, f'git add {self._todo_filename}')
            _run(self._git_path, 'git commit -m "ToDo file updated by GitToDo"')
            _run(self._git_path, 'git pull')
            _run(self._git_path, 'git push')
        except (subprocess.CalledProcessError, RuntimeError) as ex:
            if self._on_failed_git_op_cb is not None:
                self._on_failed_git_op_cb(str(ex))
            raise
