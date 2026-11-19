CORE_APP = f"{__name__}.core:app"
FILE_APP = f"{__name__}.file:app"
# Issue #68 promotion: import the normal search app unchanged and register the
# explicit pure-ASR operator endpoint in a thin extension module.
SEARCH_APP = f"{__name__}.search_issue68:app"
