subspace
========

A pragmatic interface to programmatically use [Ansible](https://github.com/ansible/ansible).

## Example

```python
import subspace
import logging
my_limits = [{"hostname": "vm3-4", "ip": "1.2.3.4"},
	      {"hostname": "vm3-5", "ip": "1.2.3.5"}]
logger = logging.getlogger("subspace") # Use your own logger.
subspace.use_logger(logger)
subspace.constants("HOST_KEY_CHECKING", False)
subspace.constants("DEFAULT_ROLES_PATH", "/opt/any/roles/path")
playbook_file = "/opt/any/ansible/playbooks/deploy.yml"
host_list_file = "/opt/any/ansible/hosts"
pb = subspace.PlayBook.factory(playbook_file,
                               host_list=host_list_file,
                               limit=my_limits)
```

To follow Ansible's naming, we're named after [Star Trek's subspace technology](http://en.wikipedia.org/wiki/Technology_in_Star_Trek#Subspace).
