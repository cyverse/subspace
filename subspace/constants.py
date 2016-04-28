import ansible
from ansible import constants as ansible_constants


__all__ = ["set_value", "get", "reload_config", "force_reload"]


def reload_config():
    config_parser, file_loc = ansible_constants.load_config_file()
    force_reload()  # New config file takes affect after force_reload
    return config_parser, file_loc


def force_reload():
    reload(ansible_constants)
    reload(ansible.plugins)
    reload(ansible.executor.task_queue_manager)


def set_value(key, value):
    setattr(ansible_constants, key, value)


def get(key):
    return getattr(ansible_constants, key)
