"""The base class of every error that hist reports without a traceback."""


class HistError(Exception):
    """An expected failure: hist prints the message and exits with status 1.

    code is the short name that '--json' error output reports.
    """

    code = "error"
