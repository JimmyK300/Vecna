# Issue #71 — OpenCubee realtime team-shortlist donor

## Decision target

Determine whether a small server-authoritative shared frame shortlist is useful enough for Vecna contest operators to retain, without importing OpenCubee's broader contest policy or touching retrieval/submission semantics.

## Donor mapping

Frozen OpenCubee source: `k19tvan/Opencubee2@0412b55a0f9a3c9642805a669efd871fddf3e970`.

Relevant source:

- `backend/api/realtime.py`
  - `/ws` WebSocket endpoint;
  - initial full `team_sync` snapshot;
  - stable-key deduplication;
  - add/remove/clear mutations;
  - authoritative full-snapshot broadcast after mutations;
  - bounded panel size and message validation.
- `backend/core/runtime.py::ConnectionManager`
  - connection set;
  - per-socket send serialization;
  - send timeout and dead-socket removal;
  - broadcast.
- `opencubee2-ui/src/App.jsx`
  - teamwork panel consumes websocket snapshots and sends explicit mutations.

## Vecna adaptation

Only the reusable collaboration primitive is ported.

Frozen v1 identity:

```text
video_id#frame_id
```

The backend canonicalizes numeric frame IDs to six digits. The server owns list ordering and timestamps. Clients may attach optional `sender` and `note` strings, but these are non-authoritative metadata.

Supported messages:

```text
ping
add_frame
remove_frame
clear_panel
```

Server events:

```text
pong
team_sync
error
```

A successful mutation broadcasts the complete current `team_sync` snapshot to all active clients. This follows OpenCubee's useful repair property: a client that missed an incremental event is corrected by the next authoritative snapshot.

## Explicit omissions

Do not interpret this donor as porting:

- global correct/wrong-submission policy;
- TRAKE ordering/state;
- DRES behavior;
- chat;
- auth/user accounts;
- persistence;
- automatic search-result sharing;
- automatic submission;
- distributed state.

## Runtime contract

State is process-local memory with a maximum of 200 entries and newest-first ordering.

This is correct for Vecna's current core deployment contract because `serve.py` defaults the core backend to one worker when no `backends.core.workers` value is configured. The current repository config has no explicit core worker count, so it resolves to one.

### Reversal condition

If Vecna is changed to any of the following, Issue #71 v1 must no longer be described as globally synchronized:

- `backends.core.workers > 1`;
- multiple core backend processes/hosts behind a load balancer;
- users need shortlist survival across backend restart.

At that point, use a shared authoritative store/broker or explicitly disable the realtime claim. Do not silently retain per-process state.

## Integration shape

Backend:

- `webui/backend/teamwork.py`: pure state + websocket manager + router;
- `webui/backend/core_issue71.py`: imports the existing core app unchanged and mounts the router;
- `webui/backend/__init__.py`: only redirects `CORE_APP` to the thin extension.

Frontend:

- `services/teamwork.js`: WebSocket client resolving against the actual browser-visible Vecna host;
- `routes/Team.jsx`: shared shortlist surface;
- `routes/RootWithTeamNav.jsx`: thin wrapper adding a Team navigation button without editing `Root.jsx`;
- `main.jsx`: registers `/team` and the wrapper.

The existing `Root`, `Search`, `Searcher`, search backend, file backend, selection provider, answer/submission logic, and ranking code are not changed.

## Operator flow

1. Search normally and select one or more frames.
2. Click **Team shortlist**. The existing `SelectedProvider` remains mounted, so selection is preserved.
3. Optionally enter sender/note.
4. Click **Share selected**.
5. Every teammate connected to the same core process receives the same full shortlist.
6. Any teammate may remove one frame or clear the list.

Publishing does not clear or otherwise mutate the local Vecna selection.

## Frozen acceptance evidence required

Before promotion:

- pure state tests: canonical identity, invalid identity, dedup, newest-first ordering, cap, remove, clear, snapshot copy;
- two simultaneous WebSocket clients receive identical initial/mutation snapshots;
- one client disconnect does not break the other;
- frontend build succeeds;
- live two-browser/client smoke on the accepted repaired Vecna runtime;
- publishing selected frames does not mutate local selected state;
- a fixed normal search canary is unchanged;
- primary Git/config/Milvus/index/corpus state is unchanged.

## Terminal policy

- `REJECT_DONOR`: reliable collaboration requires broad architecture or destabilizes normal Vecna operation.
- `KEEP_EXPERIMENTAL`: sync works, but the operator workflow is too awkward to justify normal contest use.
- `PROMOTE_CANDIDATE`: two-client sync is reliable, sharing selected frames is low-friction/useful, and normal Vecna search/submission stays unaffected.
