"""
"""
import ansible.playbook


def bust(hostname):
    """
    Delete the caches related to hostname.

    NOTE: Useful in the cloud when hostnames are reused.
    """
    try:
        del ansible.playbook.SETUP_CACHE[hostname]
        del ansible.playbook.VARS_CACHE[hostname]
    except KeyError:
        pass
