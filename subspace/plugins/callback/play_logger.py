import os
import sys

from datetime import datetime

from ansible.plugins.callback import CallbackBase
import logging

default_logger = logging.getLogger(__name__)
default_logger.setLevel(logging.DEBUG)
stderr_handler = logging.StreamHandler(sys.stderr)
# default_logger.addHandler(stderr_handler)

class PythonLogger:
    """
    Dead simple object that holds the 'logger'
    All calls will be made via:
    self.log.[debug/info/warn/...]
    """
    def __init__(self, logger=None):
        self.log = logger

    def set_logger(self, logger):
        self.log = logger



class CallbackModule(CallbackBase):
    """
    Reference: https://github.com/ansible/ansible/blob/v2.0.0.2-1/lib/ansible/plugins/callback/default.py
    """

    CALLBACK_VERSION = 2.0
    #CALLBACK_NEEDS_WHITELIST = False
    CALLBACK_TYPE = 'storage'
    CALLBACK_NAME = 'play_logger'
    username = None

    def __init__(self, python_play_logger=None, username=None):
        super(CallbackModule, self).__init__()
        if not python_play_logger:
            python_play_logger = default_logger
        self.play_logger = PythonLogger(python_play_logger)
        self.username = username
        # Start counting time from creation to completion of exection.
        self.start_time = datetime.now()

    def __unicode__(self):
        return "Callback logger for Username:%s" % self.username

    def v2_runner_on_failed(self, result, ignore_errors=False):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)

        # Catch an exception
        # This may never be called because default handler deletes
        # the exception, since Ansible thinks it knows better
        if 'exception' in result._result:
            # Extract the error message and log it
            error = result._result['exception'].strip().split('\n')[-1]
            self.play_logger.log.info(error)

            # Remove the exception from the result so it's not shown every time
            del result._result['exception']

        # Else log the reason for the failure
        if result._task.loop and 'results' in result._result:
            self._process_items(result)  # item_on_failed, item_on_skipped, item_on_ok
        else:
            if delegated_vars:
                self.play_logger.log.error("fatal: [%s -> %s]: FAILED! => %s" % (result._host.get_name(), delegated_vars['ansible_host'], self._dump_results(result._result)))
            else:
                self.play_logger.log.error("fatal: [%s]: FAILED! => %s" % (result._host.get_name(), self._dump_results(result._result)))

    def v2_runner_on_ok(self, result):
        self._clean_results(result._result, result._task.action)
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if result._task.action == 'include':
            return
        elif result._result.get('changed', False):
            if delegated_vars:
                msg = "changed: [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
            else:
                msg = "changed: [%s]" % result._host.get_name()
        else:
            if delegated_vars:
                msg = "ok: [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
            else:
                msg = "ok: [%s]" % result._host.get_name()

        if result._task.loop and 'results' in result._result:
            self._process_items(result)  # item_on_failed, item_on_skipped, item_on_ok
        else:
            self.play_logger.log.info(msg)

    def v2_runner_on_skipped(self, result):
        if result._task.loop and 'results' in result._result:
            self._process_items(result)  # item_on_failed, item_on_skipped, item_on_ok
        else:
            msg = "skipping: [%s]" % result._host.get_name()
            self.play_logger.log.info(msg)

    def v2_runner_on_unreachable(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if delegated_vars:
            self.play_logger.log.error("fatal: [%s -> %s]: UNREACHABLE! => %s" % (result._host.get_name(), delegated_vars['ansible_host'], self._dump_results(result._result)))
        else:
            self.play_logger.log.error("fatal: [%s]: UNREACHABLE! => %s" % (result._host.get_name(), self._dump_results(result._result)))

    def v2_runner_on_no_hosts(self, task):
        self.play_logger.log.warn("skipping: no hosts matched")

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.play_logger.log.info("TASK [%s]" % task.get_name().strip())

    def v2_playbook_on_play_start(self, play):
        name = play.get_name().strip()
        if not name:
            msg = "PLAY"
        else:
            msg = "PLAY [%s]" % name

        self.play_logger.log.info(msg)

    def v2_playbook_item_on_ok(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if result._task.action == 'include':
            return
        elif result._result.get('changed', False):
            if delegated_vars:
                msg = "changed: [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
            else:
                msg = "changed: [%s]" % result._host.get_name()
        else:
            if delegated_vars:
                msg = "ok: [%s -> %s]" % (result._host.get_name(), delegated_vars['ansible_host'])
            else:
                msg = "ok: [%s]" % result._host.get_name()

        msg += " => (item=%s)" % (result._result['item'])

        self.play_logger.log.info(msg)

    def v2_playbook_item_on_failed(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if 'exception' in result._result:
            # Extract the error message and log it
            error = result._result['exception'].strip().split('\n')[-1]
            self.play_logger.log.info(error)

            # Remove the exception from the result so it's not shown every time
            del result._result['exception']

        if delegated_vars:
            self.play_logger.log.info("failed: [%s -> %s] => (item=%s) => %s" % (result._host.get_name(), delegated_vars['ansible_host'], result._result['item'], self._dump_results(result._result)))
        else:
            self.play_logger.log.info("failed: [%s] => (item=%s) => %s" % (result._host.get_name(), result._result['item'], self._dump_results(result._result)))

    def v2_playbook_item_on_skipped(self, result):
        msg = "skipping: [%s] => (item=%s) " % (result._host.get_name(), result._result['item'])
        self.play_logger.log.info(msg)

    def v2_playbook_on_stats(self, stats):
        run_time = datetime.now() - self.start_time

        hosts = sorted(stats.processed.keys())
        for h in hosts:
            self._traditional_summary(stats, h, run_time)
            self.playbook_summary(stats, h, run_time)

    def playbook_summary(self, stats, h, run_time):
        if not hasattr(stats, 'summarize_playbooks'):
            self.play_logger.log.info("This execution is not using the subspace playbook executor. Default log shown")
            return
        playbook_summary = stats.summarize_playbooks(h)
        msg = "PLAYBOOK RECAP [%s] Runtime: %s : %s" % (
            h,
            run_time,
            playbook_summary
        )
        self.play_logger.log.info(msg)

    def _traditional_summary(self, stats, h, run_time):
        t = stats.summarize(h)

        msg = "PLAY RECAP [%s] : %s %s %s %s %s %s" % (
            h,
            "ok: %s" % (t['ok']),
            "changed: %s" % (t['changed']),
            "unreachable: %s" % (t['unreachable']),
            "skipped: %s" % (t['skipped']),
            "failed: %s" % (t['failures']),
            "runtime: %s seconds" % run_time.seconds
        )
        self.play_logger.log.info(msg)

    def start_logging(self, logger=None, username=None):
        """
        Special callback added to this callback plugin
        * Called by Runner objet
        :param logger:
        :return:
        """
        self.username = username
        if logger:
            self.play_logger.set_logger(logger)
        if username:
            self.play_logger.log.debug("Username set: %s" % self.username)
        # NOTE: We may want to 're-set' the `start_time` here

    def record_log(self, message=None, level='info'):
        """
        Special callback added to this callback plugin
        * Called by Strategy objet
        :param logger:
        :return:
        """
        if level not in ['debug','info','warn','error']:
           self.play_logger.log.error("Invalid level: %s" % level)
           level = 'warn'
        if message:
            getattr(self.play_logger.log, level)(message)
        # NOTE: We may want to 're-set' the `start_time` here
