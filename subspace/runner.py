import os
import operator

import logging

from ansible.inventory import Inventory
from ansible.vars import VariableManager
from ansible.utils.vars import load_options_vars
from ansible.parsing.dataloader import DataLoader

from ansible.utils.display import Display
global_display = Display()

from subspace.executor import PlaybookExecutor
from subspace.stats import SubspaceAggregateStats
from subspace.task_queue_manager import TaskQueueManager

default_logger = logging.getLogger(__name__)

class RunnerOptions(object):
    """
    RunnerOptions class to replace Ansible OptParser
    """
    def __init__(
        self, verbosity=0, inventory=None, listhosts=None, subset=None, module_paths=None, extra_vars=None,
        forks=45, ask_vault_pass=False, vault_password_file=None, new_vault_password_file=None,
        output_file=None, tags='all', skip_tags=None, one_line=None, tree=None, ask_sudo_pass=False, ask_su_pass=False,
        sudo=False, sudo_user=None, become=False, become_method=None, become_user=None, become_ask_pass=False,
        ask_pass=False, private_key_file=None, remote_user='root', connection=None, timeout=None, ssh_common_args='',
        sftp_extra_args=None, scp_extra_args=None, ssh_extra_args='', poll_interval=None, seconds=None, check=False,
        syntax=None, diff=False, force_handlers=False, flush_cache=True, listtasks=None, listtags=None, module_path=None,
        logger=None):
        # Dynamic sensible defaults
        if not logger:
            logger = default_logger
        if not connection:
            connection = 'smart'
        if not become_method:
            become_method = 'sudo'
        if not become_user:
            become_user = 'root'
        # Set your options
        self.verbosity = verbosity
        self.inventory = inventory
        self.listhosts = listhosts
        self.subset = subset
        self.module_paths = module_paths
        self.extra_vars = extra_vars
        self.forks = forks
        self.ask_vault_pass = ask_vault_pass
        self.vault_password_file = vault_password_file
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

    @classmethod
    def factory(cls, host_file, playbook_path, logger,
                **runner_options):
        """
        Walk the Directory structure and return an ordered list of
        playbook objects.

        :playbook_path: The directory/path to use for playbook list.
        :runner_options: These keyword args will be passed into Runner

        Notes: * Playbook files are identified as ending in .yml
               * Playbooks are not executed until calling Runner.run()
        """

        if 'extra_vars' in runner_options and 'run_data' not in runner_options:
            logger.warn(
                "WARNING: Use 'run_data' to pass extra_vars into the playbooks"
            )
            run_data = runner_options['extra_vars']
        else:
            run_data = runner_options.pop('run_data', {})

        runner = Runner(
            host_file,
            playbook_path,
            run_data=run_data,
            logger=logger,
            **runner_options
        )
        return runner

    def __init__(self, hosts_file, playbook_path, run_data, private_key_file,
                 limit_hosts=None, limit_playbooks=None,
                 group_vars_map={}, logger=None,
                 use_password=None, **runner_opts_args):

        self.run_data = run_data
        self.options = RunnerOptions(
                private_key_file=private_key_file,
                subset=limit_hosts,
                logger=logger,
                **runner_opts_args
            )

        # Order matters here:
        self._set_loader()
        self._set_variable_manager()
        self._set_inventory(hosts_file)

        # NOTE: Playbooks is usually a path
        # ex:deploy_playbooks/ _OR_ util_playbooks/check_networking.yml
        # it could also be a list of playbooks to be executed.
        self._set_playbooks(playbook_path, limit_playbooks)
        self._update_variables(group_vars_map)

        # Become Pass Needed if not logging in as user root
        if use_password:
            passwords = {'become_pass': use_password}
        else:
            passwords = None

        # Setup playbook executor, but don't run until run() called
        tqm = TaskQueueManager(
            inventory=self.inventory,
            variable_manager=self.variable_manager,
            loader=self.loader,
            options=self.options,
            passwords=passwords)
        # Someday, we may have a method for this.
        # For now, use 'debug = True' in ansible.cfg
        # self._set_verbosity()
        self.pbex = PlaybookExecutor(
            playbooks=self.playbooks,
            inventory=self.inventory,
            variable_manager=self.variable_manager,
            loader=self.loader,
            options=self.options,
            passwords=passwords,
            tqm=tqm)

    def _include_group_vars(self, host, group_vars_map={}):
        """
        Look up group variables in the inventory file,
        add to the variable_manager and loader
        before creating a PlaybookExecutor
        """
        host_groups = host.groups
        for group in host_groups:
            file_path = group_vars_map.get(group.name, '')
            if os.path.exists(file_path):
                self.options.logger.info(
                    "Adding group_vars file: %s" % (file_path,))
                self.variable_manager.add_group_vars_file(
                    file_path, loader=self.loader)
        variables = self.inventory.get_vars(host.name)
        self.options.logger.info(
            "Vars found for hostname %s: %s" % (host.name, variables))

    def _set_verbosity(self):
        """
        NOTE: Use 'debug = True' in ansible.cfg to get full verbosity
        """
        pass

    def _set_loader(self):
        # Gets data from YAML/JSON files
        self.loader = DataLoader()
        if 'VAULT_PASS' in os.environ:
            self.loader.set_vault_password(os.environ['VAULT_PASS'])

    def _set_variable_manager(self):
        # All the variables from all the various places
        self.variable_manager = VariableManager()
        self.variable_manager.extra_vars = self.run_data
        self.variable_manager.options_vars = load_options_vars(self.options)


    def _set_inventory(self, hosts_file):
        if not os.path.exists(hosts_file):
            raise Exception("Could not find hosts file: %s" % hosts_file)

        # Set inventory, using most of above objects
        self.inventory = Inventory(
            loader=self.loader,
            variable_manager=self.variable_manager,
            host_list=hosts_file)
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
            if self.options.flush_cache:
                self.variable_manager.clear_facts(hostname)
        #TODO: Return to fix the condition where you want to clear facts and run against a list of hosts or (all)
        return hostname

    def _set_playbooks(self, playbook_path, limit_playbooks):
        if not isinstance(playbook_path, basestring):
            raise TypeError(
                "Expected 'playbook_path' as string,"
                " received %s" % type(playbook_path))
        # Convert file path to list of playbooks:
        if not os.path.exists(playbook_path):
            raise ValueError("Could not find path: %s" % (playbook_path,))

        if os.path.isdir(playbook_path):
            playbook_list = self._get_playbook_files(
                playbook_path, limit_playbooks)
        else:
            playbook_list = [playbook_path]

        self.playbooks = playbook_list
        return self.playbooks

    def _get_playbook_files(self, playbook_dir, limit=[]):
        """
        Walk the Directory structure and return an ordered list of
        playbook objects.

        :directory: The directory to walk and search for playbooks.
        Notes: * Playbook files are identified as ending in .yml
        """
        return [pb for pb in self._get_files(playbook_dir)
                if not limit or pb.split('/')[-1] in limit]

    def _get_files(self, directory):
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

    def _update_variables(self, group_vars_map):
        """
        Used primarily to include group variables in the inventory
        """
        hosts = self.inventory.get_hosts()
        self.options.logger.info(
            "Running playbooks: %s on hosts: %s"
            % (self.playbooks, hosts))
        for host in hosts:
            self._include_group_vars(host, group_vars_map)

    def _get_playbook_name(self, playbook):
        key_name = ''
        with open(playbook,'r') as the_file:
            for line in the_file.readlines():
                if 'name:' in line.strip():
                    # This is the name you will find in stats.
                    key_name = line.replace('name:','').replace('- ','').strip()
        if not key_name:
            raise Exception(
                "Unnamed playbooks will not allow CustomSubspaceStats to work properly.")
        return key_name

    def _get_playbook_map(self):
        """
        """
        playbook_map = {
            self._get_playbook_name(playbook): playbook
            for playbook in self.playbooks}
        if len(playbook_map) != len(self.playbooks):
            raise ValueError("Non unique names in your playbooks will not allow CustomSubspaceStats to work properly. %s" % self.playbooks)
        return playbook_map

    def run(self):
        playbook_map = self._get_playbook_map()
        self.pbex._tqm._stats = SubspaceAggregateStats(playbook_map)
        self.pbex._tqm.load_callbacks()
        self.pbex._tqm.send_callback(
            'start_logging',
            logger=self.options.logger,
            username=self.run_data.get('ATMOUSERNAME', "No-User"),
        )
        # Results of PlaybookExecutor in stats.
        self.pbex.run()
        stats = self.pbex._tqm._stats
        self.stats = stats


