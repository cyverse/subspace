import os
import operator

import logging

from ansible.inventory import Inventory
from ansible.vars import VariableManager
from ansible.parsing.dataloader import DataLoader
from ansible.executor import playbook_executor
from ansible.utils.display import Display

default_logger = logging.getLogger(__name__)


class RunnerOptions(object):
    """
    RunnerOptions class to replace Ansible OptParser
    """
    def __init__(self, verbosity=None, inventory=None, listhosts=None, subset=None, module_paths=None, extra_vars=None,
                 forks=None, ask_vault_pass=None, vault_password_files=None, new_vault_password_file=None,
                 output_file=None, tags=None, skip_tags=None, one_line=None, tree=None, ask_sudo_pass=None, ask_su_pass=None,
                 sudo=None, sudo_user=None, become=None, become_method=None, become_user=None, become_ask_pass=None,
                 ask_pass=None, private_key_file=None, remote_user=None, connection=None, timeout=None, ssh_common_args=None,
                 sftp_extra_args=None, scp_extra_args=None, ssh_extra_args=None, poll_interval=None, seconds=None, check=None,
                 syntax=None, diff=None, force_handlers=None, flush_cache=None, listtasks=None, listtags=None, module_path=None,
                 logger=None):
        # Dynamic sensible defaults
        if not logger:
            logger = default_logger
        # Set your options
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
        self.logger = logger


class Runner(object):

    inventory = None
    loader = None
    options = None
    playbooks = None
    run_data = None
    variable_manager = None

    def __init__(self, hosts_file, playbook, private_key_file, run_data,
                 limit_hosts=None, group_vars_map={}, become_pass=None, verbosity=0, logger=None):

        self.run_data = run_data

        self.options = RunnerOptions(
                verbosity=verbosity,
                private_key_file=private_key_file,
                subset=limit_hosts,
                connection='ssh',  # Need a connection type "smart" or "ssh"
                logger=logger,
                become=True,
                become_method='sudo',
                become_user='root',
            )

        self._set_verbosity()
        self._set_loader()
        self._set_variable_manager()
        self._set_inventory(hosts_file)
        self._set_playbooks(playbook)
        self._set_hosts(group_vars_map)

        # Become Pass Needed if not logging in as user root
        # passwords = {'become_pass': become_pass}

        # Setup playbook executor, but don't run until run() called
        self.pbex = playbook_executor.PlaybookExecutor(
            playbooks=self.playbooks,
            inventory=self.inventory,
            variable_manager=self.variable_manager,
            loader=self.loader,
            options=self.options,
            passwords=None)

    def _include_group_vars(self, group_vars_map={}):
        variables = self.inventory.get_vars(self.host_limit)
        group_names = variables.get('group_names',[])
        for group_name in group_names:
            file_path = group_vars_map.get(group_name,'')
            if os.path.exists(file_path):
                self.variable_manager.add_group_vars_file(file_path, self.loader)
        self.options.logger.info("Vars found for hostname %s: %s" % (self.host_limit, variables))

    def _set_playbooks_from_path(self, playbook_path):
        # Convert file path to list of playbooks:
        if not os.path.exists(playbook_path):
            raise ValueError("Could not find path: %s" % (playbook_path,))

        if os.path.isdir(playbook_path):
            playbook_list = get_playbook_files(playbook_path)
        else:
            playbook_list = [playbook_path]

        self.playbooks = playbook_list

    def _set_verbosity(self):
        """
        FIXME: Prove that this works.
        """
        # Set global verbosity
        self.display = Display()
        self.display.verbosity = self.options.verbosity
        # Executor appears to have it's own
        # verbosity object/setting as well
        playbook_executor.verbosity = self.options.verbosity

    def _set_loader(self):
        # Gets data from YAML/JSON files
        self.loader = DataLoader()
        if 'VAULT_PASS' in os.environ:
            self.loader.set_vault_password(os.environ['VAULT_PASS'])

    def _set_variable_manager(self):
        # All the variables from all the various places
        self.variable_manager = VariableManager()
        self.variable_manager.extra_vars = self.run_data

    def _set_inventory(self, hosts_file):
        if not os.path.exists(hosts_file):
            raise Exception("Could not find hosts file: %s" % hosts_file)

        # Set inventory, using most of above objects
        self.inventory = Inventory(loader=self.loader, variable_manager=self.variable_manager, host_list=hosts_file)
        self.variable_manager.set_inventory(self.inventory)

        # --limit is defined by the 'subset' option and inventory kwarg.
        self.host_limit = self._set_inventory_limit()

    def _set_inventory_limit(self):
        hostname = None
        if self.options.subset and 'hostname' in self.options.subset:
            hostname = self.options.subset['hostname']
        elif self.options.subset and 'ip' in self.options.subset:
            hostname = self.options.subset['ip']
        if hostname:
            self.inventory.subset(hostname)
        return hostname

    def _set_playbooks(self, playbook):
        # Set playbooks as list or string
        if isinstance(playbook, basestring):
            self._set_playbooks_from_path(playbook)
        elif isinstance(playbook, list):
           self.playbooks = playbook
        else:
           raise TypeError("Expected 'playbook' as list or string, received %s" % type(playbook))

    def _set_hosts(self, group_vars_map):
        hosts = self.inventory.get_hosts()
        self.options.logger.info("Running playbooks: %s on hosts: %s" % (self.playbooks, hosts))
        if self.host_limit:
            self._include_group_vars(group_vars_map)

    def run(self):
        self.pbex._tqm.load_callbacks()
        self.pbex._tqm.send_callback(
            'start_logging',
            logger=self.options.logger,
            username=self.run_data.get('ATMOUSERNAME',"No-User"),
        )
        # Results of PlaybookExecutor in stats.
        self.pbex.run()
        stats = self.pbex._tqm._stats
        hosts = sorted(stats.processed.keys())
        for h in hosts:
            t = stats.summarize(h)
            if t['unreachable'] > 0 or t['failures'] > 0:
                run_success = False
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


def get_playbook_runner(playbook, logger, **kwargs):
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
        logger.warn(
            "WARNING: Use 'run_data' to pass extra_vars to the playbook runner"
        )
        run_data = kwargs['extra_vars']
    else:
        run_data = kwargs.get('run_data', {})

    host_file = kwargs.get('host_list')
    group_vars_map = kwargs.get('group_vars_map')
    private_key_file = kwargs.get('private_key', 'No Private Key provided')
    runner = Runner(
        host_file,
        playbook=playbook,
        private_key_file=private_key_file,
        run_data=run_data,
        group_vars_map=group_vars_map,
        limit_hosts=kwargs.get('limit_hosts'),
        logger=logger
    )
    return runner


def get_playbook_files(playbook_dir, limit=[]):
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
    return [pb for pb in _get_files(playbook_dir) if not limit or pb.split('/')[-1] in limit]
