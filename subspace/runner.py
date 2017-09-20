import os
import stat
import operator

import logging

from ansible.inventory import Inventory
from ansible.vars import VariableManager
from ansible.cli.playbook import CLI, PlaybookCLI
from ansible.utils.vars import load_options_vars
from ansible.parsing.dataloader import DataLoader
from ansible.playbook.block import Block
from ansible.playbook.play_context import PlayContext
from ansible.utils.vars import load_extra_vars
from ansible import constants as C

from ansible.utils.display import Display
from ansible.errors import AnsibleError

from subspace.exceptions import NoValidHosts
from subspace.executor import PlaybookExecutor
from subspace.stats import SubspaceAggregateStats

display = Display()

default_logger = logging.getLogger(__name__)


class RunnerOptions(object):
    """
    RunnerOptions class is used to replace Ansible OptParser
    """

    def __str__(self):
        options = self.__dict__
        return str(options)

    def __repr__(self):
        return self.__str__()

    def __init__(
        self, verbosity=0, inventory=None, listhosts=None, subset=None, module_paths=None, extra_vars=[],
        forks=None, ask_vault_pass=False, vault_password_file=None, new_vault_password_file=None,
        output_file=None, tags=[], skip_tags=[], one_line=None, tree=None, ask_sudo_pass=False, ask_su_pass=False,
        sudo=False, sudo_user=None, become=False, become_method=None, become_user=None, become_ask_pass=False,
        ask_pass=False, private_key_file=None, remote_user='root', connection=None, timeout=None, ssh_common_args='',
        sftp_extra_args=None, scp_extra_args=None, ssh_extra_args='', poll_interval=None, seconds=None, check=False,
        syntax=None, diff=False, force_handlers=False, flush_cache=True, listtasks=None, listtags=None, module_path=None, su=None, 
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
        if not su:
            su = C.DEFAULT_SU
        if not subset:
            subset = C.DEFAULT_SUBSET
        if not forks:
            forks = C.DEFAULT_FORKS
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
        self.su = su
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


class PlaybookShell(PlaybookCLI):
    """
    PlaybookShell uses RunnerOptions to replace 'args'
    To create a PlaybookShell:
        runner_opts = {'verbosity':4}
        Runner.factory(
            host_file,
            os.path.join(playbook_dir, playbook_path),  # Also takes a playbook directory for list-of-files.
            extra_vars=extra_vars,
            limit_hosts='127.0.0.1',  # or IP/Hostname
            limit_playbooks=['check_networking.yml'] ,  #filename relative to the playbook directory
            private_key_file="/path/to/id_rsa",
            **runner_opts)
    """

    inventory = None
    loader = None
    options = None
    playbooks = None
    extra_vars = None
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

        if 'extra_vars' in runner_options and 'extra_vars' not in runner_options:
            logger.warn(
                "WARNING: Use 'extra_vars' to pass extra_vars into the playbooks"
            )
            extra_vars = runner_options['extra_vars']
        else:
            extra_vars = runner_options.pop('extra_vars', {})

        runner = Runner(
            host_file,
            playbook_path,
            extra_vars=extra_vars,
            logger=logger,
            **runner_options
        )
        return runner

    def __init__(self, hosts_file, playbook_path, extra_vars, private_key_file,
                 limit_hosts=None, limit_playbooks=None,
                 group_vars_map={}, logger=None,
                 use_password=None, callback=None, **runner_opts_args):

        self.callback = callback
        self.extra_vars = extra_vars  # Override 'extra vars'
        self.options = RunnerOptions(
                private_key_file=private_key_file,
                subset=limit_hosts,
                inventory=hosts_file,
                logger=logger,
                **runner_opts_args
            )

        # NOTE: Playbooks is usually a path
        # ex: deploy_playbooks/ _OR_ util_playbooks/check_networking.yml
        # it could also be a list of playbooks to be executed.
        self._set_playbooks(playbook_path, limit_playbooks)

        # Become Pass Needed if not logging in as user root
        if use_password:
            passwords = {'become_pass': use_password}
        else:
            passwords = None

    def run(self):

        # Note: slightly wrong, this is written so that implicit localhost
        # Manage passwords
        sshpass    = None
        becomepass    = None
        b_vault_pass = None
        passwords = {}

        # initial error check, to make sure all specified playbooks are accessible
        # before we start running anything through the playbook executor
        for playbook in self.playbooks:
            if not os.path.exists(playbook):
                raise AnsibleError("the playbook: %s could not be found" % playbook)
            if not (os.path.isfile(playbook) or stat.S_ISFIFO(os.stat(playbook).st_mode)):
                raise AnsibleError("the playbook: %s does not appear to be a file" % playbook)

        # don't deal with privilege escalation or passwords when we don't need to
        if not self.options.listhosts and not self.options.listtasks and not self.options.listtags and not self.options.syntax:
            self.normalize_become_options()
            (sshpass, becomepass) = self.ask_passwords()
            passwords = { 'conn_pass': sshpass, 'become_pass': becomepass }

        loader = DataLoader()

        if self.options.vault_password_file:
            # read vault_pass from a file
            b_vault_pass = CLI.read_vault_password_file(self.options.vault_password_file, loader=loader)
            loader.set_vault_password(b_vault_pass)
        elif self.options.ask_vault_pass:
            b_vault_pass = self.ask_vault_passwords()
            loader.set_vault_password(b_vault_pass)
        elif 'VAULT_PASS' in os.environ:
            loader.set_vault_password(os.environ['VAULT_PASS'])

        # create the variable manager, which will be shared throughout
        # the code, ensuring a consistent view of global variables
        variable_manager = VariableManager()

        # Subspace injection
        option_extra_vars = load_extra_vars(loader=loader, options=self.options)
        option_extra_vars.update(self.extra_vars)
        variable_manager.extra_vars = option_extra_vars
        # End Subspace injection

        variable_manager.options_vars = load_options_vars(self.options)

        # create the inventory, and filter it based on the subset specified (if any)
        inventory = Inventory(loader=loader, variable_manager=variable_manager, host_list=self.options.inventory)
        variable_manager.set_inventory(inventory)

        # (which is not returned in list_hosts()) is taken into account for
        # warning if inventory is empty.  But it can't be taken into account for
        # checking if limit doesn't match any hosts.  Instead we don't worry about
        # limit if only implicit localhost was in inventory to start with.
        #
        # Fix this when we rewrite inventory by making localhost a real host (and thus show up in list_hosts())
        no_hosts = False
        if len(inventory.list_hosts()) == 0:
            # Empty inventory
            display.warning("provided hosts list is empty, only localhost is available")
            no_hosts = True
        inventory.subset(self.options.subset)
        if len(inventory.list_hosts()) == 0 and no_hosts is False:
            # Invalid limit
            raise AnsibleError("Specified --limit does not match any hosts")

        # flush fact cache if requested
        if self.options.flush_cache:
            self._flush_cache(inventory, variable_manager)

        hosts = inventory.get_hosts()
        if self.options.subset and not hosts:
            raise NoValidHosts("The limit <%s> is not included in the inventory: %s" % (self.options.subset, inventory.host_list))
       # create the playbook executor, which manages running the plays via a task queue manager
        # Subspace injection
        pbex = PlaybookExecutor(
            playbooks=self.playbooks,
            inventory=inventory,
            variable_manager=variable_manager,
            loader=loader,
            options=self.options,
            passwords=passwords)
        playbook_map = self._get_playbook_map()
        pbex._tqm._stats = SubspaceAggregateStats(playbook_map)
        pbex._tqm.load_callbacks()
        pbex._tqm.send_callback(
            'start_logging',
            logger=self.options.logger,
            username=self.extra_vars.get('ATMOUSERNAME', "No-User"),
        )
        for host in inventory._subset:
            variables = inventory.get_vars(host)
            self.options.logger.info(
                "Vars found for hostname %s: %s" % (host, variables))
        # End Subspace injection

        results = pbex.run()
        # Subspace injection
        stats = pbex._tqm._stats
        self.stats = stats
        # Nonpersistent fact cache stores 'register' variables. We would like
        # to get access to stdout/stderr for specific commands and relay
        # some of that information back to the end user.
        self.results = dict(pbex._variable_manager._nonpersistent_fact_cache)
        # End Subspace injection

        if isinstance(results, list):
            for p in results:

                display.display('\nplaybook: %s' % p['playbook'])
                for idx, play in enumerate(p['plays']):
                    if play._included_path is not None:
                        loader.set_basedir(play._included_path)
                    else:
                        pb_dir = os.path.realpath(os.path.dirname(p['playbook']))
                        loader.set_basedir(pb_dir)

                    msg = "\n  play #%d (%s): %s" % (idx + 1, ','.join(play.hosts), play.name)
                    mytags = set(play.tags)
                    msg += '\tTAGS: [%s]' % (','.join(mytags))

                    if self.options.listhosts:
                        playhosts = set(inventory.get_hosts(play.hosts))
                        msg += "\n    pattern: %s\n    hosts (%d):" % (play.hosts, len(playhosts))
                        for host in playhosts:
                            msg += "\n      %s" % host

                    display.display(msg)

                    all_tags = set()
                    if self.options.listtags or self.options.listtasks:
                        taskmsg = ''
                        if self.options.listtasks:
                            taskmsg = '    tasks:\n'

                        def _process_block(b):
                            taskmsg = ''
                            for task in b.block:
                                if isinstance(task, Block):
                                    taskmsg += _process_block(task)
                                else:
                                    if task.action == 'meta':
                                        continue

                                    all_tags.update(task.tags)
                                    if self.options.listtasks:
                                        cur_tags = list(mytags.union(set(task.tags)))
                                        cur_tags.sort()
                                        if task.name:
                                            taskmsg += "      %s" % task.get_name()
                                        else:
                                            taskmsg += "      %s" % task.action
                                        taskmsg += "\tTAGS: [%s]\n" % ', '.join(cur_tags)

                            return taskmsg

                        all_vars = variable_manager.get_vars(loader=loader, play=play)
                        play_context = PlayContext(play=play, options=self.options)
                        for block in play.compile():
                            block = block.filter_tagged_tasks(play_context, all_vars)
                            if not block.has_tasks():
                                continue
                            taskmsg += _process_block(block)

                        if self.options.listtags:
                            cur_tags = list(mytags.union(all_tags))
                            cur_tags.sort()
                            taskmsg += "      TASK TAGS: [%s]\n" % ', '.join(cur_tags)

                        display.display(taskmsg)

            return 0
        else:
            return results

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

# For compatability
class Runner(PlaybookShell):
    pass
