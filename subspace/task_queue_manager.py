from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
import os

from ansible.errors import AnsibleError
from ansible.executor.play_iterator import PlayIterator
from ansible.playbook.play_context import PlayContext
from ansible.plugins import strategy_loader
from ansible.template import Templar
from ansible.vars.hostvars import HostVars

try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()
from ansible.plugins.strategy.linear import StrategyModule \
    as AnsibleLinearStrategy

from ansible.executor.task_queue_manager import TaskQueueManager \
    as AnsibleTaskQueueManager

class TaskQueueManager(AnsibleTaskQueueManager):

    default_strategy = 'subspace'  # Use the subspace strategy by default.
    def run(self, play):
        '''
        Iterates over the roles/tasks in a play, using the given (or default)
        strategy for queueing tasks. The default is the linear strategy, which
        operates like classic Ansible by keeping all hosts in lock-step with
        a given task (meaning no hosts move on to the next task until all hosts
        are done with the current task).
        '''

        if not self._callbacks_loaded:
            self.load_callbacks()

        all_vars = self._variable_manager.get_vars(loader=self._loader, play=play)
        templar = Templar(loader=self._loader, variables=all_vars)

        new_play = play.copy()
        new_play.post_validate(templar)

        self.hostvars = HostVars(
            inventory=self._inventory,
            variable_manager=self._variable_manager,
            loader=self._loader,
        )

        # Fork # of forks, # of hosts or serial, whichever is lowest
        contenders =  [self._options.forks, play.serial, len(self._inventory.get_hosts(new_play.hosts))]
        contenders =  [ v for v in contenders if v is not None and v > 0 ]
        self._initialize_processes(min(contenders))

        play_context = PlayContext(new_play, self._options, self.passwords, self._connection_lockfile.fileno())
        for callback_plugin in self._callback_plugins:
            if hasattr(callback_plugin, 'set_play_context'):
                callback_plugin.set_play_context(play_context)

        self.send_callback('v2_playbook_on_play_start', new_play)

        # initialize the shared dictionary containing the notified handlers
        self._initialize_notified_handlers(new_play.handlers)

        # IF the method for loading strategy fails,
        #  this hack will ensure
        # 'Subspace' linear strategy is what gets used.
        strategy = self._ensure_subspace_plugin(new_play)

        # build the iterator
        iterator = PlayIterator(
            inventory=self._inventory,
            play=new_play,
            play_context=play_context,
            variable_manager=self._variable_manager,
            all_vars=all_vars,
            start_at_done=self._start_at_done,
        )

        # during initialization, the PlayContext will clear the start_at_task
        # field to signal that a matching task was found, so check that here
        # and remember it so we don't try to skip tasks on future plays
        if getattr(self._options, 'start_at_task', None) is not None and play_context.start_at_task is None:
            self._start_at_done = True

        # and run the play using the strategy and cleanup on way out
        play_return = strategy.run(iterator, play_context)
        self._cleanup_processes()
        return play_return

    def _ensure_subspace_plugin(self, new_play):
        from subspace.plugins.strategy.subspace import StrategyModule

        # NOTE: Requires *ALL* strategies to use subspace-linear for now.
        new_play.strategy = self.default_strategy

	# NOTE: these lines can be removed upon release of ansi-2.1
        subspace_dir = os.path.dirname(__file__)
        strategy_loader.config = os.path.join(subspace_dir, 'plugins/strategy')
        strategy = strategy_loader.get(new_play.strategy, self)

        if strategy is None or not isinstance(strategy, StrategyModule):
            strategy = StrategyModule(self)

        if not isinstance(strategy, StrategyModule):
            raise AnsibleError("Invalid play strategy specified: %s" % new_play.strategy, obj=play._ds)
        return strategy
