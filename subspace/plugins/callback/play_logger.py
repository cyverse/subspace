import os

from datetime import datetime

from ansible.plugins.callback import CallbackBase


class PlayLogger:
    """Store log output in a single object.
    We create a new object per Ansible run
    """
    def __init__(self, logger=None):
        self.logger = logger
        self.log = ''
        self.runtime = 0

    def set_logger(self, logger):
        self.logger = logger

    def print_to_logger(self, user_id):
        """
        Record all logs to the python logger
        """
        self.logger.info("User: %s Runtime: %s - All logs:\n%s" % (user_id, self.logger.runtime, self.logger.log))

    def append(self, log_line):
        """append to log"""
        self.log += log_line+"\n\n"

    def banner(self, msg):
        """Output Trailing Stars"""
        width = 78 - len(msg)
        if width < 3:
            width = 3
        filler = "*" * width
        return "\n%s %s " % (msg, filler)


class CallbackModule(CallbackBase):
    """
    Reference: https://github.com/ansible/ansible/blob/v2.0.0.2-1/lib/ansible/plugins/callback/default.py
    """

    CALLBACK_VERSION = 2.0
    #CALLBACK_NEEDS_WHITELIST = False
    CALLBACK_TYPE = 'stdout'
    CALLBACK_NAME = 'play_logger'

    def __init__(self, python_play_logger=None):
        super(CallbackModule, self).__init__()
        import ipdb;ipdb.set_trace()
        self.play_logger = PlayLogger()
        self.start_time = datetime.now()

    def v2_runner_on_failed(self, result, ignore_errors=False):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)

        # Catch an exception
        # This may never be called because default handler deletes
        # the exception, since Ansible thinks it knows better
        if 'exception' in result._result:
            # Extract the error message and log it
            error = result._result['exception'].strip().split('\n')[-1]
            self.play_logger.append(error)

            # Remove the exception from the result so it's not shown every time
            del result._result['exception']

        # Else log the reason for the failure
        if result._task.loop and 'results' in result._result:
            self._process_items(result)  # item_on_failed, item_on_skipped, item_on_ok
        else:
            if delegated_vars:
                self.play_logger.append("fatal: [%s -> %s]: FAILED! => %s" % (result._host.get_name(), delegated_vars['ansible_host'], self._dump_results(result._result)))
            else:
                self.play_logger.append("fatal: [%s]: FAILED! => %s" % (result._host.get_name(), self._dump_results(result._result)))

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
            self.play_logger.append(msg)

    def v2_runner_on_skipped(self, result):
        if result._task.loop and 'results' in result._result:
            self._process_items(result)  # item_on_failed, item_on_skipped, item_on_ok
        else:
            msg = "skipping: [%s]" % result._host.get_name()
            self.play_logger.append(msg)

    def v2_runner_on_unreachable(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if delegated_vars:
            self.play_logger.append("fatal: [%s -> %s]: UNREACHABLE! => %s" % (result._host.get_name(), delegated_vars['ansible_host'], self._dump_results(result._result)))
        else:
            self.play_logger.append("fatal: [%s]: UNREACHABLE! => %s" % (result._host.get_name(), self._dump_results(result._result)))

    def v2_runner_on_no_hosts(self, task):
        self.play_logger.append("skipping: no hosts matched")

    def v2_playbook_on_task_start(self, task, is_conditional):
        import ipdb;ipdb.set_trace()
        self.play_logger.append("TASK [%s]" % task.get_name().strip())

    def v2_playbook_on_play_start(self, play):
        import ipdb;ipdb.set_trace()
        name = play.get_name().strip()
        if not name:
            msg = "PLAY"
        else:
            msg = "PLAY [%s]" % name

        self.play_logger.append(msg)

    def v2_playbook_item_on_ok(self, result):
        import ipdb;ipdb.set_trace()
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

        self.play_logger.append(msg)

    def v2_playbook_item_on_failed(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if 'exception' in result._result:
            # Extract the error message and log it
            error = result._result['exception'].strip().split('\n')[-1]
            self.play_logger.append(error)

            # Remove the exception from the result so it's not shown every time
            del result._result['exception']

        if delegated_vars:
            self.play_logger.append("failed: [%s -> %s] => (item=%s) => %s" % (result._host.get_name(), delegated_vars['ansible_host'], result._result['item'], self._dump_results(result._result)))
        else:
            self.play_logger.append("failed: [%s] => (item=%s) => %s" % (result._host.get_name(), result._result['item'], self._dump_results(result._result)))

    def v2_playbook_item_on_skipped(self, result):
        msg = "skipping: [%s] => (item=%s) " % (result._host.get_name(), result._result['item'])
        self.play_logger.append(msg)

    def v2_playbook_on_stats(self, stats):
        import ipdb;ipdb.set_trace()
        run_time = datetime.now() - self.start_time
        self.play_logger.runtime = run_time.seconds  # returns an int, unlike run_time.total_seconds()

        hosts = sorted(stats.processed.keys())
        for h in hosts:
            t = stats.summarize(h)

            msg = "PLAY RECAP [%s] : %s %s %s %s %s" % (
                h,
                "ok: %s" % (t['ok']),
                "changed: %s" % (t['changed']),
                "unreachable: %s" % (t['unreachable']),
                "skipped: %s" % (t['skipped']),
                "failed: %s" % (t['failures']),
            )
            self.play_logger.append(msg)

    def set_logger(self, logger=None):
        """
        Special callback added to this callback plugin
        Called by Runner objet
        :param logger:
        :return:
        """
        self.play_logger.set_logger(logger)

    def record_logs(self, user_id, success=False):
        """
        Special callback added to this callback plugin
        Called by Runner objet
        :param user_id:
        :return:
        """
        self.play_logger.print_to_logger(user_id)
