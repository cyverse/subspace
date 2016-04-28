"""
This Custom stats module allows more detailed information to be recorded, including:
* What playbook is failed/unreachable
* What task in the playbook failed/unreachable
"""


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
        self.processed = {}
        self.failures  = {}
        self.ok        = {}
        self.dark      = {}
        self.changed   = {}
        self.skipped   = {}

    def increment(self, what, host, play, task):
        ''' helper function to bump a statistic '''

        self.processed[host] = 1

        stat_dict = getattr(self,what)
        host_playbook_dict = stat_dict.get(host, {})
        playbook_key = self.playbook_map[play.name]
        playbook_role_dict = host_playbook_dict.get(playbook_key, {})
        if not task:
            role_key = "Unnamed Task"
        elif not task._role:
            role_key = "Unnamed Role"
            print "WARNING: There is something fishy here: %s" % (task.__dict__,)
        else:
            role_key = task._role._role_name
        task_count = playbook_role_dict.get(role_key, 0)
        playbook_role_dict[role_key] = task_count + 1
        host_playbook_dict[playbook_key] = playbook_role_dict
        stat_dict[host] = host_playbook_dict


    def summarize(self, host):
        ''' return information about a particular host '''

        return dict(
            ok          = self.ok.get(host, {}),
            failures    = self.failures.get(host, {}),
            unreachable = self.dark.get(host,{}),
            changed     = self.changed.get(host, {}),
            skipped     = self.skipped.get(host, {})
        )

