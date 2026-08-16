from .searcher import Searcher

# Integration repair for feat/bgem3ocrasr: its helper insertion displaced the
# original @staticmethod decorator from _filter_exclude_videos. Rebind the raw
# class function as a static method so existing self._filter_exclude_videos(...)
# call sites keep the intended two-argument contract.
Searcher._filter_exclude_videos = staticmethod(Searcher.__dict__["_filter_exclude_videos"])
