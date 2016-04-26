from ansible.executor import playbook_executor


class PlaybookExecutor(playbook_executor.PlaybookExecutor):
    '''
    This is an extension of ansible playbook_excutor.PlaybookExecutor
    Its sole purpose is to provide the ability to pass a *custom* TaskQueueManager.
    '''

    def __init__(self, playbooks, inventory, variable_manager, loader, options, passwords, tqm=None):
        super(PlaybookExecutor, self).__init__(playbooks, inventory, variable_manager, loader, options, passwords)
        # _tqm has been set by default..  this is our chance to override.
        if options.listhosts or options.listtasks or options.listtags or options.syntax:
            self._tqm = None
        elif tqm:
            self._tqm = tqm

