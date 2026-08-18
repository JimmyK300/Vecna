import logging
import sys

from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install

# Fix Windows console cp1252 UnicodeEncodeError for Vietnamese characters
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(highlight=False)

FORMAT = "%(message)s"
DATE_FORMAT = "[%X]"
logging.basicConfig(
    level=logging.INFO,
    format=FORMAT,
    datefmt=DATE_FORMAT,
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger("AIC51")

install()


