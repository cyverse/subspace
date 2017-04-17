from ansible.executor import playbook_executor
from ansible.utils.ssh_functions import check_for_controlpersist
from ansible import constants as C

from subspace.task_queue_manager import SubspaceTaskQueueManager

class PlaybookExecutor(playbook_executor.PlaybookExecutor):
    '''
    This is an extension of ansible playbook_excutor.PlaybookExecutor
    Its sole purpose is to provide the ability to pass a *custom* TaskQueueManager.
    '''

    def __init__(self, playbooks, inventory, variable_manager, loader, options, passwords):
        self._playbooks        = playbooks
        self._inventory        = inventory
        self._variable_manager = variable_manager
        self._loader           = loader
        self._options          = options
        self.passwords         = passwords
        self._unreachable_hosts = dict()

        if options.listhosts or options.listtasks or options.listtags or options.syntax:
            self._tqm = None
        else:
            self._tqm = SubspaceTaskQueueManager(inventory=inventory, variable_manager=variable_manager, loader=loader, options=options, passwords=self.passwords)

        # Note: We run this here to cache whether the default ansible ssh
        # executable supports control persist.  Sometime in the future we may
        # need to enhance this to check that ansible_ssh_executable specified
        # in inventory is also cached.  We can't do this caching at the point
        # where it is used (in task_executor) because that is post-fork and
        # therefore would be discarded after every task.
        check_for_controlpersist(C.ANSIBLE_SSH_EXECUTABLE)
