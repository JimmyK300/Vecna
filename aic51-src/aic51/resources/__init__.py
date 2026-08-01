from .file_paths import *

try:
    from .TransNetV2.inference.transnetv2 import TransNetV2
except ModuleNotFoundError:
    # The TransNetV2 repository is a separately initialized submodule. Its
    # absence must not prevent Milvus/search/API modules from importing.
    TransNetV2 = None
