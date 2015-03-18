subspace
========

A pragmatic interface to programmatically use Ansible. 

```python
import subspace
import logging
my_limits = [{"hostname": "vm3-4", "ip": "1.2.3.4"},
	      {"hostname": "vm3-5", "ip": "1.2.3.5"}]
logger = logging.getlogger("subspace")
subspace.use_logger(logger)
subspace.constants("HOST_KEY_CHECKING", False)
subspace.constants("DEFAULT_ROLES_PATH", "/opt/dev/atmosphere/service/ansible/roles")
playbook_file = "/opt/dev/atmosphere/service/ansible/playbooks/test_integration.yml"
pb = subspace.PlayBook.factory(playbook_file,
                               host_list="/opt/dev/atmosphere/service/ansible/hosts",
			                   limit=my_limits)
```

To follow Ansible's naming, we're named after [Star Trek's subspace technology](http://en.wikipedia.org/wiki/Technology_in_Star_Trek#Subspace).
