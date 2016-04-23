import os
import operator

from datetime import datetime
from tempfile import NamedTemporaryFile

from ansible.inventory import Inventory
from ansible.vars import VariableManager
from ansible.parsing.dataloader import DataLoader
from ansible.executor import playbook_executor
from ansible.utils.display import Display
from ansible.plugins.callback import CallbackBase

class PlayLogger:
    """Store log output in a single object.
    We create a new object per Ansible run
    """
    def __init__(self):
        self.log = ''
        self.runtime = 0

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
    CALLBACK_TYPE = 'stored'
    CALLBACK_NAME = 'database'

    def __init__(self):
        super(CallbackModule, self).__init__()
        self.logger = PlayLogger()
        self.start_time = datetime.now()

    def v2_runner_on_failed(self, result, ignore_errors=False):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)

        # Catch an exception
        # This may never be called because default handler deletes
        # the exception, since Ansible thinks it knows better
        if 'exception' in result._result:
            # Extract the error message and log it
            error = result._result['exception'].strip().split('\n')[-1]
            self.logger.append(error)

            # Remove the exception from the result so it's not shown every time
            del result._result['exception']

        # Else log the reason for the failure
        if result._task.loop and 'results' in result._result:
            self._process_items(result)  # item_on_failed, item_on_skipped, item_on_ok
        else:
            if delegated_vars:
                self.logger.append("fatal: [%s -> %s]: FAILED! => %s" % (result._host.get_name(), delegated_vars['ansible_host'], self._dump_results(result._result)))
            else:
                self.logger.append("fatal: [%s]: FAILED! => %s" % (result._host.get_name(), self._dump_results(result._result)))

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
            self.logger.append(msg)

    def v2_runner_on_skipped(self, result):
        if result._task.loop and 'results' in result._result:
            self._process_items(result)  # item_on_failed, item_on_skipped, item_on_ok
        else:
            msg = "skipping: [%s]" % result._host.get_name()
            self.logger.append(msg)

    def v2_runner_on_unreachable(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if delegated_vars:
            self.logger.append("fatal: [%s -> %s]: UNREACHABLE! => %s" % (result._host.get_name(), delegated_vars['ansible_host'], self._dump_results(result._result)))
        else:
            self.logger.append("fatal: [%s]: UNREACHABLE! => %s" % (result._host.get_name(), self._dump_results(result._result)))

    def v2_runner_on_no_hosts(self, task):
        self.logger.append("skipping: no hosts matched")

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.logger.append("TASK [%s]" % task.get_name().strip())

    def v2_playbook_on_play_start(self, play):
        name = play.get_name().strip()
        if not name:
            msg = "PLAY"
        else:
            msg = "PLAY [%s]" % name

        self.logger.append(msg)

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

        self.logger.append(msg)

    def v2_playbook_item_on_failed(self, result):
        delegated_vars = result._result.get('_ansible_delegated_vars', None)
        if 'exception' in result._result:
            # Extract the error message and log it
            error = result._result['exception'].strip().split('\n')[-1]
            self.logger.append(error)

            # Remove the exception from the result so it's not shown every time
            del result._result['exception']

        if delegated_vars:
            self.logger.append("failed: [%s -> %s] => (item=%s) => %s" % (result._host.get_name(), delegated_vars['ansible_host'], result._result['item'], self._dump_results(result._result)))
        else:
            self.logger.append("failed: [%s] => (item=%s) => %s" % (result._host.get_name(), result._result['item'], self._dump_results(result._result)))

    def v2_playbook_item_on_skipped(self, result):
        msg = "skipping: [%s] => (item=%s) " % (result._host.get_name(), result._result['item'])
        self.logger.append(msg)

    def v2_playbook_on_stats(self, stats):
        run_time = datetime.now() - self.start_time
        self.logger.runtime = run_time.seconds  # returns an int, unlike run_time.total_seconds()

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

            self.logger.append(msg)

    def record_logs(self, user_id, success=False):
        """
        Special callback added to this callback plugin
        Called by Runner objet
        :param user_id:
        :return:
        """
        print "When this works i will 'store' the log results somewhere."
        print "For now: User: %s Runtime: %s - All logs:\n%s" % (user_id, self.logger.runtime, self.logger.log)



class Options(object):
    """
    Options class to replace Ansible OptParser
    """
    def __init__(self, verbosity=None, inventory=None, listhosts=None, subset=None, module_paths=None, extra_vars=None,
                 forks=None, ask_vault_pass=None, vault_password_files=None, new_vault_password_file=None,
                 output_file=None, tags=None, skip_tags=None, one_line=None, tree=None, ask_sudo_pass=None, ask_su_pass=None,
                 sudo=None, sudo_user=None, become=None, become_method=None, become_user=None, become_ask_pass=None,
                 ask_pass=None, private_key_file=None, remote_user=None, connection=None, timeout=None, ssh_common_args=None,
                 sftp_extra_args=None, scp_extra_args=None, ssh_extra_args=None, poll_interval=None, seconds=None, check=None,
                 syntax=None, diff=None, force_handlers=None, flush_cache=None, listtasks=None, listtags=None, module_path=None):
        self.verbosity = verbosity
        self.inventory = inventory
        self.listhosts = listhosts
        self.subset = subset
        self.module_paths = module_paths
        self.extra_vars = extra_vars
        self.forks = forks
        self.ask_vault_pass = ask_vault_pass
        self.vault_password_files = vault_password_files
        self.new_vault_password_file = new_vault_password_file
        self.output_file = output_file
        self.tags = tags
        self.skip_tags = skip_tags
        self.one_line = one_line
        self.tree = tree
        self.ask_sudo_pass = ask_sudo_pass
        self.ask_su_pass = ask_su_pass
        self.sudo = sudo
        self.sudo_user = sudo_user
        self.become = become
        self.become_method = become_method
        self.become_user = become_user
        self.become_ask_pass = become_ask_pass
        self.ask_pass = ask_pass
        self.private_key_file = private_key_file
        self.remote_user = remote_user
        self.connection = connection
        self.timeout = timeout
        self.ssh_common_args = ssh_common_args
        self.sftp_extra_args = sftp_extra_args
        self.scp_extra_args = scp_extra_args
        self.ssh_extra_args = ssh_extra_args
        self.poll_interval = poll_interval
        self.seconds = seconds
        self.check = check
        self.syntax = syntax
        self.diff = diff
        self.force_handlers = force_handlers
        self.flush_cache = flush_cache
        self.listtasks = listtasks
        self.listtags = listtags
        self.module_path = module_path


class Runner(object):

    def __init__(self, hosts_file, playbook, private_key_file, run_data,
                 limit_hosts=None, group_vars_map={}, become_pass=None, verbosity=4):

        self.run_data = run_data

        self.options = Options(
                verbosity=verbosity,
                private_key_file=private_key_file,
                subset=limit_hosts,
                connection='ssh',  # Need a connection type "smart" or "ssh"
                become=True,
                become_method='sudo',
                become_user='root',
            )
        # Set global verbosity
        self.display = Display()
        self.display.verbosity = self.options.verbosity
        # Executor appears to have it's own
        # verbosity object/setting as well
        playbook_executor.verbosity = self.options.verbosity

        # Become Pass Needed if not logging in as user root
        # passwords = {'become_pass': become_pass}

        # Gets data from YAML/JSON files
        self.loader = DataLoader()
        if 'VAULT_PASS' in os.environ:
            self.loader.set_vault_password(os.environ['VAULT_PASS'])

        # All the variables from all the various places
        self.variable_manager = VariableManager()
        self.variable_manager.extra_vars = self.run_data

        # Parse hosts, I haven't found a good way to
        # pass hosts in without using a parsed template :(
        # (Maybe you know how?)
        self.hosts = NamedTemporaryFile(delete=False)
        if not os.path.exists(hosts_file):
            raise Exception("Could not find hosts file: %s" % hosts_file)

        with open(hosts_file, 'r') as the_file:
            self.hosts.write(the_file.read())
        self.hosts.close()

        # Set inventory, using most of above objects
        self.inventory = Inventory(loader=self.loader, variable_manager=self.variable_manager, host_list=self.hosts.name)
        self.variable_manager.set_inventory(self.inventory)
        hostname = None
        if self.options.subset:
            hostname = self.options.subset['ip']  # ['hostname']
            self.inventory.subset(hostname)
        # Playbook to run. Assumes it is
        # local to this python file
        if isinstance(playbook, basestring):
            if not os.path.exists(playbook):
                # See if path is relative, not absolute..
                pb_dir = os.path.dirname(__file__)
                playbook = "%s/%s" % (pb_dir, playbook)
            if os.path.isdir(playbook):
                playbooks = list_playbooks(playbook)
            else:
                playbooks = [playbook]
        elif isinstance(playbook, list):
            playbooks = playbook

        self.playbook = playbook

        hosts = self.inventory.get_hosts()
        print "Running playbooks: %s on hosts: %s" % (playbooks, hosts)
        if hostname:
            variables = self.inventory.get_vars(hostname)
            group_names = variables.get('group_names',[])
            for group_name in group_names:
                file_path = group_vars_map.get(group_name,'')
                if os.path.exists(file_path):
                    self.variable_manager.add_group_vars_file(file_path,self.loader)
            print "Vars found: %s" % variables
        # Setup playbook executor, but don't run until run() called
        self.pbex = playbook_executor.PlaybookExecutor(
            playbooks=playbooks,
            inventory=self.inventory,
            variable_manager=self.variable_manager,
            loader=self.loader,
            options=self.options,
            passwords=None)

    def run(self):
        # Results of PlaybookExecutor in stats.
        self.pbex.run()
        stats = self.pbex._tqm._stats

        # Test if success for record_logs
        run_success = True
        hosts = sorted(stats.processed.keys())
        for h in hosts:
            t = stats.summarize(h)
            if t['unreachable'] > 0 or t['failures'] > 0:
                run_success = False

        # Dirty hack to send callback to save logs with data we want
        # Note that function "record_logs" is one I created and put into
        # the playbook callback file
        self.pbex._tqm.send_callback(
            'record_logs',
            user_id=self.run_data['ATMOUSERNAME'],  # FIXME yo
            success=run_success
        )
        os.remove(self.hosts.name)
        self.stats = stats


def _get_files(directory):
    """
    Walk the directory and retrieve each yml file.
    """
    files = []
    directories = list(os.walk(directory))
    directories.sort(cmp=operator.lt)
    for d in directories:
        a_dir = d[0]
        files_in_dir = d[2]
        files_in_dir.sort()
        if os.path.isdir(a_dir) and "playbooks" in a_dir:
            for f in files_in_dir:
                if os.path.splitext(f)[1] == ".yml":
                    files.append(os.path.join(a_dir, f))
    return files


def get_playbook_runner(playbook, **kwargs):
    """
    Walk the Directory structure and return an ordered list of
    playbook objects.

    :directory: The directory to walk and search for playbooks.
    :kwargs: The keywords that will be passed to the PlayBook.factory method.

    Notes: * Playbook files are identified as ending in .yml
           * Playbooks are created using the same **kwargs.
           * Playbooks are not run.
           * Playbook files use the .yml file extension.
    """
    if 'extra_vars' in kwargs and 'run_data' not in kwargs:
        print "WARNING: extra_vars is deprecated in ansible2.0 -- use run_data"
        run_data = kwargs['extra_vars']
    else:
        run_data = kwargs.get('run_data', {})
    host_file = kwargs.get('host_list')
    group_vars_map = kwargs.get('group_vars_map')
    private_key_file = kwargs.get('private_key', 'No Private Key provided')
    print "Use key: %s" % private_key_file
    runner = Runner(
        host_file,
        playbook=playbook,
        private_key_file=private_key_file,
        run_data=run_data,
        group_vars_map=group_vars_map,
        limit_hosts=kwargs.get('limit_hosts'),
        verbosity=4
    )
    return runner


def list_playbooks(directory, limit=[]):
    """
    Walk the Directory structure and return an ordered list of
    playbook objects.

    :directory: The directory to walk and search for playbooks.
    :kwargs: The keywords that will be passed to the PlayBook.factory method.

    Notes: * Playbook files are identified as ending in .yml
           * Playbooks are created using the same **kwargs.
           * Playbooks are not run.
           * Playbook files use the .yml file extension.
    """
    return [pb for pb in _get_files(directory) if not limit or pb.split('/')[-1] in limit]
