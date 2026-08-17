import os
import inspect
from importlib import import_module
from pkgutil import iter_modules

from .command import BaseCommand

# Find all subclasses of BaseCommand and export them as available_commands
available_commands = set()
package_dir = os.path.dirname(__file__)
for _, module_name, _ in iter_modules([package_dir]):
    try:
        module = import_module(f"{__name__}.{module_name}")
    except Exception as e:
        print(f"[Warning] Failed to load CLI command module '{module_name}': {e}")
        continue
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and issubclass(obj, BaseCommand) and obj != BaseCommand:
            available_commands.add(obj)

