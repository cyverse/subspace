"""
This Custom stats module allows more detailed information to be recorded, including:
* What playbook is failed/unreachable
* What task in the playbook failed/unreachable
"""
DEBUG = False

class SubspaceAggregateStats:
    ''' holds stats about per-host activity during playbook runs '''

    def __init__(self, playbook_map):
        """
        Completed dict looks like this:
        self.ok= {
          'vm64-214.iplantcollaborative.org': {
            'Playbook by name': {
              'failed_task': 1,
            },
            ...
        """
        self.playbook_map = playbook_map
        """
        Completed processed_playbooks looks like this:
        self.processed_playbooks = {
          'vm64-214.iplantcollaborative.org': {
            'Playbook by name': {
              'role_or_task_name': {
                'ok': 2, 'failed': 5, 'skipped': 3, 'unreachable': 0
              }
            }
          }
          'hostname_2': { ... },
        }
        """
        self.processed_playbooks = {}
        self.processed = {}
        self.failures  = {}
        self.ok        = {}
        self.dark      = {}
        self.changed   = {}
        self.skipped   = {}

    def original_increment(self, what, host):
        prev = (getattr(self, what)).get(host, 0)
        getattr(self, what)[host] = prev+1
        return

    def increment(self, what, host, play=None, task=None):
        ''' helper function to bump a statistic '''
        self.processed[host] = 1
        self.original_increment(what, host)
        if not play and not task:
            return

        self._increment_playbook_dict(what, host, play, task)

    def _get_role_key(self, task):
        if not task:
            role_key = "Unnamed Task"
        elif getattr(task, 'name', None):
            role_key = task.name
        elif not getattr(task, '_role', None):
            role_key = "No Role"
        elif not getattr(task._role, '_role_name', None):
            role_key = "No Role Name"
        else:
            role_key = task._role._role_name

        return role_key

    def _get_playbook_key(self, play, use_path=True):
        if not play:
            playbook_key = "No play"
        elif not getattr(play,'name',None):
            playbook_key = "Unnamed Play"
        else:
            playbook_key = play.name
        if use_path:
            playbook_path = self.playbook_map.get(playbook_key,'N/A')
            return playbook_path
        else:
            return playbook_key

    def _increment_nested_dict(self, what, host, play, task):
        stat_dict = getattr(self,what)

        playbook_key = self._get_playbook_key(play)
        role_key = self._get_role_key(task)

        host_playbook_dict = stat_dict.get(host, {})
        playbook_role_dict = host_playbook_dict.get(playbook_key, {})

        task_count = playbook_role_dict.get(role_key, 0)
        playbook_role_dict[role_key] = task_count + 1

        host_playbook_dict[playbook_key] = playbook_role_dict
        stat_dict[host] = host_playbook_dict
        return

    def _increment_playbook_dict(self, what, host, play, task):
        if not DEBUG and what in ['skipped', 'ok', 'changed']:
            return

        playbook_key = self._get_playbook_key(play, use_path=True)
        role_key = self._get_role_key(task)

        host_dict = self.processed_playbooks.get(host, {})
        playbook_dict = host_dict.get(playbook_key, {})
        status_dict = playbook_dict.get(role_key, {})

        status_count = status_dict.get(what, 0)
        status_dict[what] = status_count+1

        playbook_dict[role_key] = status_dict
        host_dict[playbook_key] = playbook_dict
        self.processed_playbooks[host] = host_dict

    def summarize_playbooks(self, host):
        ''' return information about a particular host '''

        return self.processed_playbooks.get(host, {})

    def summarize(self, host):
        ''' return information about a particular host '''

        return dict(
            ok          = self.ok.get(host, {}),
            failures    = self.failures.get(host, {}),
            unreachable = self.dark.get(host,{}),
            changed     = self.changed.get(host, {}),
            skipped     = self.skipped.get(host, {})
        )

