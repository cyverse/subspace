"""
"""
import ansible.playbook


__all__ = ["bust"]


def bust(hostname):
    """
    Delete the caches related to hostname.

    NOTE: The __del__ is overloaded by Ansible's cache plugin
    So these are not just simple dictionary deletes.

    NOTE: Useful in the cloud when hostnames are reused.
    """
    try:
        del ansible.playbook.SETUP_CACHE[hostname]
        del ansible.playbook.VARS_CACHE[hostname]
    except KeyError:
        pass
