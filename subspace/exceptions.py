class SubspaceException(Exception):
    """
    Catch-all exceptions class for Subspace
    """
    pass


class NoValidHosts(SubspaceException):
    """
    Thrown when no valid hosts are available
    """
    pass
