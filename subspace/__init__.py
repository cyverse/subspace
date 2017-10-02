from .version import VERSION

__all__ = ['configure', 'VERSION']

def configure(settings=None):
    if not settings:
        settings = {}

    import ansible.constants
    import ansible.plugins
    import ansible.executor.task_queue_manager
    reload(ansible.constants)
    reload(ansible.constants)
    reload(ansible.executor.task_queue_manager)

    for k,v in settings.iteritems():
        setattr(ansible.constants, k, v)
