import sys
import ansible
from ansible import constants as ansible_constants


__all__ = ["set", "get", "reload_config"]

def reload_config():
    config_parser, file_loc = ansible_constants.load_config_file()
    reload(ansible_constants)
    reload(ansible.plugins)
    reload(ansible.executor.task_queue_manager)


def set_value(key, value):
    setattr(ansible_constants, key, value)


def get(key):
    return getattr(ansible_constants, key)
