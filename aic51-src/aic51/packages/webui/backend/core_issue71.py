"""Thin Vecna core extension for Issue #71 realtime teamwork.

The existing core app remains unchanged. This module only mounts the bounded
teamwork router so ordinary search/file proxy behavior is inherited verbatim.
"""
from .core import app
from .teamwork import create_teamwork_router

app.include_router(create_teamwork_router())
