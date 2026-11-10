"""Console and log-file output.

Information goes to standard output, warnings and errors to standard error as 'hist: warning: ...' and
'hist: error: ...'. Long-running commands prefix their lines with the time and also append them to a log file.
"""
import logging
import sys
from pathlib import Path

log = logging.getLogger("hist")


class _Console(logging.Handler):
    def __init__(self, timestamps: bool):
        super().__init__()
        self.timestamps = timestamps

    def emit(self, record: logging.LogRecord) -> None:
        text = record.getMessage()
        if record.levelno >= logging.WARNING:
            stream, text = sys.stderr, f"hist: {record.levelname.lower()}: {text}"
        else:
            stream = sys.stdout
            if self.timestamps:
                text = f"{self.formatter.formatTime(record, '%H:%M:%S')} {text}"
        stream.write(text + "\n")
        stream.flush()


def setup(verbose: bool = False, quiet: bool = False) -> None:
    for handler in list(log.handlers):
        log.removeHandler(handler)
    console = _Console(timestamps=False)
    console.setFormatter(logging.Formatter())
    console.setLevel(logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO)
    log.addHandler(console)
    log.setLevel(logging.DEBUG)
    log.propagate = False


def long_running(log_file: Path) -> None:
    """Prefix console lines with the time and append every line to log_file."""
    for handler in log.handlers:
        if isinstance(handler, _Console):
            handler.timestamps = True
    log_file.parent.mkdir(parents=True, exist_ok=True)
    to_file = logging.FileHandler(log_file, encoding="utf-8")
    to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S"))
    to_file.setLevel(logging.DEBUG)
    log.addHandler(to_file)
