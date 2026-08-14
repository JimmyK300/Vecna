# `webui/frontend/src/routes/Search.jsx` & UI Components

## Purpose

Documents all keyboard shortcuts (hotkeys), UI navigation features, query input parameters, and CSV payload export logic implemented in the Web UI frontend application for rapid navigation, query switching, video playback control, frame selection, and submission during AI Challenge video retrieval tasks.

---

## Global & Search Navigation Shortcuts

These shortcuts work across the main search interface when focus is not inside a text input field.

| Hotkey | Action | Description |
|---|---|---|
| `/` | **Focus Search Bar** | Smoothly scrolls to the search section and focuses the main `#search-bar` input. |
| `Tab` / `Shift + Tab` | **Cycle Input Fields** | Cycles focus forward/backward between `#search-bar` and Advanced Query inputs (`main`, `ocr`, `speech`, `include_videos`, `exclude_videos`). |
| `Up Arrow` ($\uparrow$) | **Previous Page** | Navigates to the previous page of search results (`goToPreviousPage`). |
| `Down Arrow` ($\downarrow$) | **Next Page** | Navigates to the next page of search results (`goToNextPage`). |
| `Shift + 1` ... `Shift + 9` | **Play Result 1–9** | Instantly opens the Video Player modal for the 1st through 9th displayed search result keyframe. |
| `Shift + 0` | **Play Result 10** | Instantly opens the Video Player modal for the 10th displayed search result keyframe. |
| `Shift + ?` (`Shift + /`) | **Jump to Answer** | Smoothly scrolls down to the Answer Submission section on the left sidebar. |
| `Shift + Enter` | **Submit Answer** | Triggers answer payload submission (`handleSubmitSelected`). |

> **Note:** Navigation shortcuts (`Up Arrow`, `Down Arrow`, etc.) are ignored while the cursor is inside an `<input>` or `<textarea>` element to allow normal text editing.

---

## Video Player Modal Shortcuts

Active when the Video Player popup modal is open (`VideoPlayer.jsx`).

| Hotkey | Action | Description |
|---|---|---|
| `K` | **Play / Pause** | Toggles video playback pause or play state. |
| `Left Arrow` ($\leftarrow$) | **Seek Backward** | Seeks backward by the configured seek interval (e.g. 5 seconds). |
| `Right Arrow` ($\rightarrow$) | **Seek Forward** | Seeks forward by the configured seek interval (e.g. 5 seconds). |
| `Ctrl + Left Arrow` | **Prev BTC Keyframe** | Jumps directly to the previous official BTC keyframe loaded from `map-keyframes`. |
| `Ctrl + Right Arrow` | **Next BTC Keyframe** | Jumps directly to the next official BTC keyframe loaded from `map-keyframes`. |
| `Shift + Left Arrow` | **Step 1 Frame Back** | Rewinds video playback by exactly 1 frame ($1 / \text{FPS}$). |
| `Shift + Right Arrow` | **Step 1 Frame Forward** | Advances video playback by exactly 1 frame ($1 / \text{FPS}$). |
| `[` | **Step 1 Frame Back** | Alternative shortcut to rewind video playback by 1 frame. |
| `]` | **Step 1 Frame Forward** | Alternative shortcut to advance video playback by 1 frame. |
| `+` | **Increase Speed** | Increases video playback speed by $+0.25\text{x}$ (up to $4.0\text{x}$). |
| ``-`` | **Decrease Speed** | Decreases video playback speed by $-0.25\text{x}$ (down to $0.25\text{x}$). |
| `S` | **Select Keyframe** | Toggles frame selection (`frame_id`) for answer submission payload. |
| `Enter` | **Focus Answer Input** | Focuses the answer text input field inside the video player modal. |
| `Shift + Enter` | **Submit Selected** | Submits current selected answer frame payload. |
| `Esc` | **Close Player** | Closes the Video Player modal and returns to the search grid. |

---

## Modal Overlays & Frame View Shortcuts

Active when viewing enlarged frame images, keyframe map context, nearby keyframes, or OCR modals (`Frame.jsx`).

| Hotkey | Action | Description |
|---|---|---|
| `Esc` | **Close Active Modal** | Closes any open modal overlay (Zoom View, Map Keyframes Context, Nearby Keyframes, or OCR Modal). |

---

## Advanced Query & Input Field Controls

Active inside Advanced Query inputs (`AdvanceQuery.jsx` & `SearchParams.jsx`).

| Control / Hotkey | Action | Description |
|---|---|---|
| `Enter` *(without Shift)* | **Execute Search** | Submits and triggers search query execution. |
| `Shift + Enter` | **New Line** | Inserts a line break inside multi-line text input fields. |
| **Include Videos Input** | `[video:...]` | Filter query results to include only specified video IDs (supports inline tags or UI tag pills). |
| **Exclude Videos Input** | `[!video:...]` | Filter query results to exclude specified video IDs (supports `[!video:...]` or `[exclude_video:...]`). |

---

## Answer Payload CSV Export Features

Active in the Answer Submission Sidebar (`Answer.jsx`, `answer.js`, `files.js`).

- **Dynamic Frame Expansion (`step` & `n`)**:
  - Automatically expands selected keyframes using step interval `step` up to `n` frames before/after.
  - Implements interleaved subtraction/addition branching with dynamic `getVideoMaxFrame` boundary enforcement.
- **UTF-8 BOM Compatibility (`files.js`)**:
  - Automatically prepends UTF-8 Byte Order Mark (`\uFEFF`) to CSV exports, ensuring Vietnamese characters (e.g. `đ`, `ổ`, `ê`, `á`) render correctly in Microsoft Excel.

