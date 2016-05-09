from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import time
from ansible.compat.six import iteritems, text_type

from ansible.errors import AnsibleError
from ansible.template import Templar

from ansible.compat.six.moves import queue as Queue
from ansible.inventory.host import Host
from ansible.vars.unsafe_proxy import wrap_var

#Some deep level cruft
from ansible.compat.six import iteritems, text_type, string_types
from ansible.playbook.helpers import load_list_of_blocks
from ansible.executor.task_result import TaskResult
from ansible.errors import AnsibleParserError

from ansible.plugins.strategy import StrategyBase \
    as AnsibleStrategyBase
from ansible.plugins.strategy.linear import StrategyModule \
    as AnsibleLinearStrategyModule
try:
    from __main__ import display
except ImportError:
    from ansible.utils.display import Display
    display = Display()

from subspace.task_queue_manager import TaskQueueManager as SubspaceTQM
__all__ = ['StrategyModule']


class StrategyModule(AnsibleLinearStrategyModule, AnsibleStrategyBase):

    def increment_stat(self, what, host_name, play, task):
        if type(self._tqm) == SubspaceTQM:
            return self._tqm._stats.increment(what, host_name, play, task)
        else:
            self._tqm.send_callback('record_log', "Using the 'traditional' TQM results in loss of functionality")
            return self._tqm._stats.increment(what, host_name)
            
    def _process_pending_results(self, iterator, one_pass=False):
        '''
        Reads results off the final queue and takes appropriate action
        based on the result (executing callbacks, updating state, etc.).
        '''
        ret_results = []

        while not self._final_q.empty() and not self._tqm._terminated:
            try:
                result = self._final_q.get()
                display.debug("got result from result worker: %s" % ([text_type(x) for x in result],))

                # helper method, used to find the original host from the one
                # returned in the result/message, which has been serialized and
                # thus had some information stripped from it to speed up the
                # serialization process
                def get_original_host(host):
                    if host.name in self._inventory._hosts_cache:
                       return self._inventory._hosts_cache[host.name]
                    else:
                       return self._inventory.get_host(host.name)

                # all host status messages contain 2 entries: (msg, task_result)
                if result[0] in ('host_task_ok', 'host_task_failed', 'host_task_skipped', 'host_unreachable'):
                    task_result = result[1]
                    host = get_original_host(task_result._host)
                    task = task_result._task
                    if result[0] == 'host_task_failed' or task_result.is_failed():
                        if not task.ignore_errors:
                            display.debug("marking %s as failed" % host.name)
                            if task.run_once:
                                # if we're using run_once, we have to fail every host here
                                [iterator.mark_host_failed(h) for h in self._inventory.get_hosts(iterator._play.hosts) if h.name not in self._tqm._unreachable_hosts]
                            else:
                                iterator.mark_host_failed(host)

                            # only add the host to the failed list officially if it has
                            # been failed by the iterator
                            if iterator.is_failed(host):
                                self._tqm._failed_hosts[host.name] = True
                                self.increment_stat('failures', host.name, iterator._play, task)
                            else:
                                # otherwise, we grab the current state and if we're iterating on
                                # the rescue portion of a block then we save the failed task in a
                                # special var for use within the rescue/always
                                state, _ = iterator.get_next_task_for_host(host, peek=True)
                                if state.run_state == iterator.ITERATING_RESCUE:
                                    original_task = iterator.get_original_task(host, task)
                                    self._variable_manager.set_nonpersistent_facts(
                                        host,
                                        dict(
                                            ansible_failed_task=original_task.serialize(),
                                            ansible_failed_result=task_result._result,
                                        ),
                                    )
                        else:
                            self.increment_stat('ok', host.name, iterator._play, task)
                        self._tqm.send_callback('v2_runner_on_failed', task_result, ignore_errors=task.ignore_errors)
                    elif result[0] == 'host_unreachable':
                        self._tqm._unreachable_hosts[host.name] = True
                        self.increment_stat('dark', host.name, iterator._play, task)
                        self._tqm.send_callback('v2_runner_on_unreachable', task_result)
                    elif result[0] == 'host_task_skipped':
                        self.increment_stat('skipped', host.name, iterator._play, task)
                        self._tqm.send_callback('v2_runner_on_skipped', task_result)
                    elif result[0] == 'host_task_ok':
                        if task.action != 'include':
                            self.increment_stat('ok', host.name, iterator._play, task)
                            if 'changed' in task_result._result and task_result._result['changed']:
                                self.increment_stat('changed', host.name, iterator._play, task)
                            self._tqm.send_callback('v2_runner_on_ok', task_result)

                        if self._diff:
                            self._tqm.send_callback('v2_on_file_diff', task_result)

                    self._pending_results -= 1
                    if host.name in self._blocked_hosts:
                        del self._blocked_hosts[host.name]

                    # If this is a role task, mark the parent role as being run (if
                    # the task was ok or failed, but not skipped or unreachable)
                    if task_result._task._role is not None and result[0] in ('host_task_ok', 'host_task_failed'):
                        # lookup the role in the ROLE_CACHE to make sure we're dealing
                        # with the correct object and mark it as executed
                        for (entry, role_obj) in iteritems(iterator._play.ROLE_CACHE[task_result._task._role._role_name]):
                            if role_obj._uuid == task_result._task._role._uuid:
                                role_obj._had_task_run[host.name] = True

                    ret_results.append(task_result)

                elif result[0] == 'add_host':
                    result_item = result[1]
                    new_host_info = result_item.get('add_host', dict())

                    self._add_host(new_host_info, iterator)

                elif result[0] == 'add_group':
                    host = get_original_host(result[1])
                    result_item = result[2]
                    self._add_group(host, result_item)

                elif result[0] == 'notify_handler':
                    task_result  = result[1]
                    handler_name = result[2]

                    original_host = get_original_host(task_result._host)
                    original_task = iterator.get_original_task(original_host, task_result._task)
                    if handler_name not in self._notified_handlers:
                        self._notified_handlers[handler_name] = []

                    if original_host not in self._notified_handlers[handler_name]:
                        self._notified_handlers[handler_name].append(original_host)
                        display.vv("NOTIFIED HANDLER %s" % (handler_name,))

                elif result[0] == 'register_host_var':
                    # essentially the same as 'set_host_var' below, however we
                    # never follow the delegate_to value for registered vars and
                    # the variable goes in the fact_cache
                    host      = get_original_host(result[1])
                    task      = result[2]
                    var_value = wrap_var(result[3])
                    var_name  = task.register

                    if task.run_once:
                        host_list = [host for host in self._inventory.get_hosts(iterator._play.hosts) if host.name not in self._tqm._unreachable_hosts]
                    else:
                        host_list = [host]

                    for target_host in host_list:
                        self._variable_manager.set_nonpersistent_facts(target_host, {var_name: var_value})

                elif result[0] in ('set_host_var', 'set_host_facts'):
                    host = get_original_host(result[1])
                    task = result[2]
                    item = result[3]

                    # find the host we're actually refering too here, which may
                    # be a host that is not really in inventory at all
                    if task.delegate_to is not None and task.delegate_facts:
                        task_vars = self._variable_manager.get_vars(loader=self._loader, play=iterator._play, host=host, task=task)
                        task_vars = self.add_tqm_variables(task_vars, play=iterator._play)
                        loop_var = 'item'
                        if task.loop_control:
                            loop_var = task.loop_control.loop_var or 'item'
                        if item is not None:
                            task_vars[loop_var] = item
                        templar = Templar(loader=self._loader, variables=task_vars)
                        host_name = templar.template(task.delegate_to)
                        actual_host = self._inventory.get_host(host_name)
                        if actual_host is None:
                            actual_host = Host(name=host_name)
                    else:
                        actual_host = host

                    if task.run_once:
                        host_list = [host for host in self._inventory.get_hosts(iterator._play.hosts) if host.name not in self._tqm._unreachable_hosts]
                    else:
                        host_list = [actual_host]

                    if result[0] == 'set_host_var':
                        var_name  = result[4]
                        var_value = result[5]
                        for target_host in host_list:
                            self._variable_manager.set_host_variable(target_host, var_name, var_value)
                    elif result[0] == 'set_host_facts':
                        facts = result[4]
                        for target_host in host_list:
                            if task.action == 'set_fact':
                                self._variable_manager.set_nonpersistent_facts(target_host, facts)
                            else:
                                self._variable_manager.set_host_facts(target_host, facts)
                elif result[0].startswith('v2_runner_item') or result[0] == 'v2_runner_retry':
                    self._tqm.send_callback(result[0], result[1])
                elif result[0] == 'v2_on_file_diff':
                    if self._diff:
                        self._tqm.send_callback('v2_on_file_diff', result[1])
                else:
                    raise AnsibleError("unknown result message received: %s" % result[0])

            except Queue.Empty:
                time.sleep(0.0001)

            if one_pass:
                break

        return ret_results

    def _load_included_file(self, included_file, iterator, is_handler=False):
        '''
        Loads an included YAML file of tasks, applying the optional set of variables.
        '''

        display.debug("loading included file: %s" % included_file._filename)
        try:
            data = self._loader.load_from_file(included_file._filename)
            if data is None:
                return []
            elif not isinstance(data, list):
                raise AnsibleError("included task files must contain a list of tasks")

            block_list = load_list_of_blocks(
                data,
                play=included_file._task._block._play,
                parent_block=None,
                task_include=included_file._task,
                role=included_file._task._role,
                use_handlers=is_handler,
                loader=self._loader,
                variable_manager=self._variable_manager,
            )

            # since we skip incrementing the stats when the task result is
            # first processed, we do so now for each host in the list
            for host in included_file._hosts:
                self.increment_stat('ok', host.name, included_file._task._block._play, included_file._task)

        except AnsibleError as e:
            # mark all of the hosts including this file as failed, send callbacks,
            # and increment the stats for this host
            for host in included_file._hosts:
                tr = TaskResult(host=host, task=included_file._task, return_data=dict(failed=True, reason=to_unicode(e)))
                iterator.mark_host_failed(host)
                self._tqm._failed_hosts[host.name] = True
                self.increment_stat('failures', host.name, included_file._task._block._play, included_file._task)
                self._tqm.send_callback('v2_runner_on_failed', tr)
            return []

        # set the vars for this task from those specified as params to the include
        for b in block_list:
            # first make a copy of the including task, so that each has a unique copy to modify
            b._task_include = b._task_include.copy()
            # then we create a temporary set of vars to ensure the variable reference is unique
            temp_vars = b._task_include.vars.copy()
            temp_vars.update(included_file._args.copy())
            # pop tags out of the include args, if they were specified there, and assign
            # them to the include. If the include already had tags specified, we raise an
            # error so that users know not to specify them both ways
            tags = temp_vars.pop('tags', [])
            if isinstance(tags, string_types):
                tags = tags.split(',')
            if len(tags) > 0:
                if len(b._task_include.tags) > 0:
                    raise AnsibleParserError("Include tasks should not specify tags in more than one way (both via args and directly on the task). Mixing tag specify styles is prohibited for whole import hierarchy, not only for single import statement",
                            obj=included_file._task._ds)
                display.deprecated("You should not specify tags in the include parameters. All tags should be specified using the task-level option")
                b._task_include.tags = tags
            b._task_include.vars = temp_vars

        # finally, send the callback and return the list of blocks loaded
        self._tqm.send_callback('v2_playbook_on_include', included_file)
        display.debug("done processing included file")
        return block_list
