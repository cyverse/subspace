subspace
========

A pragmatic interface to programmatically use [Ansible](https://github.com/ansible/ansible).

## Example

```python
import subspace
import logging

# Use a custom logger
logger = logging.getlogger("subspace")

# Set ansible configuration
subspace.configure({
    "HOST_KEY_CHECKING": False,
    "DEFAULT_ROLES_PATH": "/opt/any/roles/path"
})

# Run playbooks
host_file = "/opt/any/ansible/hosts"
playbook_dir = "/opt/any/ansible/playbooks"
hosts = [ "vm3-4", vm3-5" ]
pb = subspace.Runner.factory(host_file,
                             playbook_dir,
                             limit_hosts=hosts,
                             logger=logger)
pb.run()
```

To follow Ansible's naming, we're named after [Star Trek's subspace technology](http://en.wikipedia.org/wiki/Technology_in_Star_Trek#Subspace).
