def __getattr__(name):
    if name == "Searcher":
        from .searcher import Searcher

        # Integration repair for feat/bgem3ocrasr: its helper insertion
        # displaced the original @staticmethod decorator from
        # _filter_exclude_videos. Rebind the raw class function as a static
        # method so existing self._filter_exclude_videos(...) call sites keep
        # the intended two-argument contract.
        Searcher._filter_exclude_videos = staticmethod(
            Searcher.__dict__["_filter_exclude_videos"]
        )

        # Thread 5A is an opt-in adapter only. The wrapper returns the original
        # search result object unchanged unless evidence_bundle_path is supplied.
        from .evidence_provider import attach_thread3_evidence_provider

        attach_thread3_evidence_provider(Searcher)
        return Searcher
    if name == "SearchCancelledException":
        from .searcher import SearchCancelledException
        return SearchCancelledException
    if name == "EvidenceBundleError":
        from .evidence_provider import EvidenceBundleError
        return EvidenceBundleError
    if name == "load_thread3_evidence_bundle":
        from .evidence_provider import load_thread3_evidence_bundle
        return load_thread3_evidence_bundle
    raise AttributeError(name)
