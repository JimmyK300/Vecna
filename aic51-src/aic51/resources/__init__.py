from .file_paths import *

try:
    from .TransNetV2.inference.transnetv2 import TransNetV2
except ImportError:  # TransNetV2 is optional for analyse/index-only workspaces
    TransNetV2 = None
