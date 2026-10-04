# X Browser

X Browser is a desktop browser built with Python, PyQt6, and Qt WebEngine (Chromium). It provides tabbed browsing, an address/search bar, built-in settings/history/download pages, an opt-in API-powered homepage, private windows, X Downloader v2, and per-tab renderer recovery.

## Requirements

- Windows 10/11, macOS, or a supported Linux desktop
- Python 3.10 or newer
- A working Qt/WebEngine runtime supported by the installed PyQt6 wheels
- Internet access for websites and optional homepage feeds

## Install

From the repository directory, create and activate a virtual environment.

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PyQt6 PyQt6-WebEngine validators requests
python main.py
```

If PowerShell prevents activation, run the install command with the virtual environment interpreter directly:

```powershell
.venv\Scripts\python.exe -m pip install PyQt6 PyQt6-WebEngine validators requests
.venv\Scripts\python.exe main.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PyQt6 PyQt6-WebEngine validators requests
python main.py
```

### Pipenv

The repository includes a `Pipfile`:

```bash
python -m pip install pipenv
pipenv install
pipenv run python main.py
```

The equivalent direct pip dependencies are `PyQt6`, `PyQt6-WebEngine`, `validators`, and `requests`. Requests brings `urllib3`, `certifi`, `charset-normalizer`, and `idna` as transitive dependencies.

## Start the Browser

Run `python main.py` from the repository root. The root directory is the expected working directory because local pages, icons, fonts, and wallpapers use project-relative paths.

The application creates a main window, a `QTabWidget`, and a toolbar. A new tab loads `homepage/index.html`; entering a URL or search query in the address bar navigates the current tab. Internal pages are opened from the three-line menu or by entering an `x-browser://` address.

### Application startup flow

1. `main.py` creates the Qt application, registers local fonts, and constructs `MainWindow`.
2. `MainWindow` reads persisted preferences and history/download/bookmark records through `QSettings`.
3. `components/main.py` creates the tab widget and WebEngine profile. Regular windows use the shared profile; private windows create an off-the-record profile.
4. The startup preference selects the homepage or configured startup destination. Each normal browser tab gets its own `BrowserPage` and `BrowserView`.
5. The homepage is loaded as a local file so its CSS and SVG assets resolve. Once it finishes loading, Python sends the user's homepage widget settings into the page with `runJavaScript`.
6. Navigation from the address bar, homepage search, built-in feature pages, downloads, and bookmarks are routed through `Main` and `MainWindow`.

The normal browser UI is a desktop Qt application; the files under `homepage/` and `features/` are HTML/CSS/JavaScript documents rendered by Qt WebEngine, not a separate web server.

### Main modules

- `main.py` owns the main window, preference loading/saving, internal page actions, history, bookmarks, the downloader app API, and private-window creation.
- X Downloader v1 remains a separate standalone downloader; the browser's integrated transfer flow uses the independent X Downloader v2 component.
- `components/downloader.py` implements X Downloader v2: an independent `QThread`/`requests` worker with parallel byte-range downloads, single-stream fallback, progress signals, pause/resume, cancellation, and safe file merging.
- `components/main.py` owns tabs, Chromium profiles, navigation, new-window tab creation, media context menus, renderer-crash recovery, and page load progress.
- `components/tool_bar.py` owns navigation actions, the address field, the bookmark star, the download progress indicator, and the three-line menu.
- `homepage/index.html`, `homepage/styles.css`, and `homepage/scripts.js` implement the new-tab interface, site shortcuts, optional feeds, and clock.
- `features/*.html` implement the settings, history, downloads, and bookmarks interfaces. Their actions are delegated to Python through internal `x-browser://` navigation requests.

## Features

### Tabs and navigation

- Open tabs with the plus button or `Ctrl+T`.
- Close the current tab with `Ctrl+W`.
- Focus and select the address bar with `Ctrl+L`.
- Reload with `Ctrl+R`; use `Alt+Left` and `Alt+Right` for back/forward.
- Each tab has its own `QWebEnginePage` and load-progress display.
- If a Chromium renderer terminates, that tab shows a retry page. Other browser windows and tabs remain available.

### Search engine

Open Settings and choose DuckDuckGo, Google, or Bing. Address-bar searches and homepage searches both go through the same Python navigation function and use the saved choice. Enter a domain or full URL to navigate directly instead of searching.

The homepage includes shortcuts for ChatGPT, Qwen, Online Tools Pro, YouTube, and Hacker News. Each shortcut displays the site's favicon, fetched through Google's public favicon endpoint, beside the site name. There is no text-initial placeholder; if a remote icon cannot be loaded, the shortcut name remains available.

### Startup destination and bookmarks

Settings can open the startup page on launch and optionally load a custom URL. Leave the URL blank to use the built-in homepage; an `x-browser://` URL can select a built-in page.

Use the star at the right end of the address field to save or remove the active page. The browser asks for confirmation before changing a bookmark. The Bookmarks item in the three-line menu opens the built-in bookmarks page, where saved titles and URLs can be edited, opened, or deleted. Bookmark data is persisted with `QSettings`.

### Homepage and public APIs

The homepage includes a clock, search field, and quick links. Optional widgets are controlled in Settings and default to off:

- **Wallpaper:** Select an image in `assets/wallpapers` or choose a local image file. The selection is saved and applies to open homepage tabs.
- **Top stories:** Fetches current story IDs and story details from the public Hacker News Firebase API. No API key is required.
- **Weather:** Uses Open-Meteo's geocoding and forecast APIs. Enable the widget and enter a city in Settings. No API key is required.

No request is made to either service while its widget is disabled. When enabled, the homepage fetches the data on new-tab load. Feed availability, rate limits, and network access are controlled by the public services. Their responses are rendered as text; story links open in the current tab.

### Settings and internal pages

Settings, History, Downloads, and Bookmarks are local HTML pages in `features/`. Python loads the page data and handles page actions via the `x-browser://` scheme. Settings, bookmarks, history, and download records are stored as JSON-compatible values through `QSettings`. Download records include filename, path, source URL, time, size, state, and progress.

The main persisted `QSettings` keys are:

| Key | Purpose |
| --- | --- |
| `browser/search_engine` | Selected address-bar and homepage search engine |
| `browser/open_on_start` | Whether to create the startup tab/window at launch |
| `browser/startup_url` | Optional custom startup URL or built-in `x-browser://` page |
| `browser/download_mode` | `normal` or sequential `fast` download mode |
| `browser/history` | Recent normal-window visits |
| `browser/downloads` | Normal-window download metadata and progress |
| `browser/bookmarks` | Saved title and URL pairs |
| `homepage/news_enabled` | Hacker News widget preference; defaults to false |
| `homepage/weather_enabled` | Weather widget preference; defaults to false |
| `homepage/weather_city` | City name used for Open-Meteo geocoding |
| `homepage/wallpaper` | Selected built-in or local wallpaper URL |

### Built-in page actions

The local pages use `window.location` with an internal URL. `BrowserPage.acceptNavigationRequest` catches these requests and delegates them to `MainWindow.handle_feature_action`, preventing them from being loaded as external websites.

| Internal URL | Effect |
| --- | --- |
| `x-browser://settings-save?payload=...` | Save settings and startup preferences |
| `x-browser://search?payload=...` | Search using the selected search engine |
| `x-browser://history-open?payload=...` | Open a history item |
| `x-browser://history-delete?payload=...` | Delete selected history items |
| `x-browser://history-clear?payload=...` | Clear history for a selected time range |
| `x-browser://bookmark-open?payload=...` | Open a saved bookmark |
| `x-browser://bookmark-edit?payload=...` | Update a bookmark title and URL |
| `x-browser://bookmark-delete?payload=...` | Delete a bookmark |
| `x-browser://download-clear?payload=...` | Clear the displayed download records |
| `x-browser://download-show-folder?payload=...` | Open the containing folder in the system file manager |
| `x-browser://download-toggle?payload=...` | Pause or resume an active download |
| `x-browser://download-retry?payload=...` | Retry a failed or cancelled download |
| `x-browser://download-redownload?payload=...` | Download another copy of a completed file |
| `x-browser://download-copy-url?payload=...` | Copy a download's source URL to the clipboard |
| `x-browser://wallpaper-choose` | Choose a local homepage wallpaper |

Payloads are JSON encoded in the query string. Page rendering uses HTML-safe JSON serialization and DOM `textContent` for user-controlled bookmark labels and URLs.

### Downloads

- Browser download requests and right-click **Download image** / **Download video** actions are handed from Qt WebEngine to X Downloader v2. X Downloader v1 remains standalone and unchanged; v2 is a separate worker component controlled through the browser's download API.
- Downloads are saved to the operating system's Downloads folder. The filename suggested by Chromium is retained when available; duplicate names receive a numbered suffix.
- The Downloads page displays each transfer's status, size, progress bar, actionable network/file errors, and an SVG file-type icon. Active transfers can be paused/resumed; failed or cancelled transfers can be retried as a new transfer, and completed files can be downloaded again without overwriting existing copies.
- **Copy URL** copies the source address; **Open** opens a completed file, and **Show folder** opens its containing directory in the system file manager.
- V2 checks whether the server supports byte ranges. When supported, it downloads up to four ranges concurrently and merges them in order; otherwise, it uses a single stream. Partial data is retained while paused and removed after completion, cancellation, or failure.
- Fast download mode queues files so only one file transfers at a time; parallel ranges within that file remain enabled. It cannot reserve network bandwidth against websites or other applications.
- The app API is exposed by `MainWindow.start_download(url, filename)`, `pause_download(download_id)`, `resume_download(download_id)`, `cancel_download(download_id)`, and `retry_download(download_id)`. `start_download` returns the new download ID. Existing `x-browser://download-*` page actions continue to call these app APIs.
- Transfers are not restored across browser restarts; unfinished records are marked interrupted, and Retry starts a fresh request using the saved source URL. Direct URL retries use HTTP GET and do not inherit browser cookies, POST bodies, or one-time headers; URLs that require these may fail. Only HTTP and HTTPS downloads are supported.

Media downloads depend on the source site exposing a downloadable media URL. DRM-protected streams, segmented streaming formats, and sites requiring special authentication may not be downloadable as a single file through the context menu.

### Private windows

Open **New private window** from the toolbar menu or press `Ctrl+Shift+T`. Each private window uses a separate off-the-record `QWebEngineProfile`, so cookies, cache, visited links, and browser history are not persisted to the regular profile. Private history/download records remain in memory only for that window. Files explicitly downloaded in private mode are still written to the normal Downloads folder and remain on disk.

### Homepage shortcut customization

Edit the `.shortcuts` links in `homepage/index.html`. Each shortcut needs an `href` and matching `data-site-url`; JavaScript uses `data-site-url` to request its favicon. Keep the visible site label as ordinary text after the image. The favicon service is an external dependency and may rate-limit or fail; the link itself still works without its icon.

### Rendering and resource use

Qt WebEngine uses Chromium's normal process, thread-pool, CPU-core, and hardware-acceleration policies. X Browser enables WebGL and accelerated 2D canvas where the Qt/driver combination supports them, and enables back/forward cache when available. It does not pin Chromium to a selected core count or force vendor-specific GPU flags; doing so can reduce stability or disable acceleration on some machines. GPU availability ultimately depends on the system driver and Qt WebEngine build.

## Project Layout

```text
main.py                  Main window, settings, internal routes, history, downloads
components/main.py       Tab widget, WebEngine pages/views, navigation and crash recovery
components/downloader.py X Downloader v2 background worker and HTTP transfer logic
components/tool_bar.py   Address bar, toolbar menu, download progress indicator
features/settings.html   Search, startup, fast-download, and homepage preferences
features/history.html    Browsing history interface
features/downloads.html  Download list, progress, and folder actions
features/bookmarks.html Editable bookmark list and actions
homepage/index.html      New-tab page structure
homepage/scripts.js      Search, clock, and opt-in public API widgets
homepage/styles.css      New-tab layout and responsive styles
assets/                  Icons, fonts, wallpaper, and branding
```

## Data and Privacy

- Application preferences and normal browsing records are stored through Qt `QSettings` under the `XBrowser` / `X Browser` application keys.
- Normal downloads are written to the OS Downloads directory; metadata is stored with browser settings.
- X Downloader v2 makes HTTP requests from Python `requests`, independently of Chromium's cookie store. Download URLs are sent to their target servers; URLs requiring browser-only authentication context may fail.
- Private profiles do not share regular cookies/cache and do not write private history/download metadata to normal settings.
- Homepage news/weather calls go directly from Qt WebEngine to Hacker News and Open-Meteo only after the user enables each widget.
- Websites opened in the browser can still make their own network requests as usual.

## Troubleshooting

- **Qt WebEngine fails to initialize:** Update graphics drivers and reinstall the matching PyQt6 and PyQt6-WebEngine packages in the active virtual environment.
- **Homepage widgets are empty:** Confirm the relevant widget is enabled in Settings, a city is set for weather, and the network allows access to the documented public APIs.
- **A download fails:** Read the reason shown in Downloads, check that the destination has write permission and enough free space, then use Retry. Retry creates a new transfer; it cannot restore expired links, browser cookies, POST bodies, or one-time authentication headers.
- **Pause/resume does not take effect:** Pause is observed at the next received network chunk. Resume continues from saved partial data when possible. A transfer interrupted by closing the browser must be retried as a new transfer.
- **A download does not start:** Confirm the source URL is directly downloadable and not protected by DRM or a site-specific login flow.
- **Local assets appear missing:** Start `main.py` from the repository root so the relative asset paths resolve correctly.

## Development Checks

Compile the Python entry point and browser components with:

```bash
python -m py_compile main.py components/main.py components/tool_bar.py
```

Before a release, manually verify these UI workflows in a normal desktop session:

1. Search from the homepage with each configured search engine and open a result in the current tab and a new tab.
2. Visit an HTTPS page, add/remove it with the star, restart the app, and confirm the bookmark remains.
3. Open Bookmarks from the menu; open, edit, and delete entries and verify each change persists after reopening the page.
4. Set a custom startup URL, enable startup-page loading, restart, and confirm the configured URL opens. Repeat with the URL blank to confirm the homepage opens.
5. Enable/disable homepage widgets and verify disabled widgets make no API requests; test weather with a valid city and an invalid city.
6. Confirm regular browsing history/downloads persist, then open a private window and confirm its visit records are not added to normal history.
7. Change the homepage wallpaper to a bundled image and a local image, and verify the choice persists and updates existing homepage tabs.
8. Right-click an image and an eligible video, verify the download appears in X Downloader v2, the toolbar indicator advances, and test pause/resume, cancel, retry, redownload, Copy URL, and **Show folder**. Verify a range-capable server uses multiple segments, a server without byte ranges uses the fallback stream, fast mode queues additional files, and failures show an actionable reason.

The app is under active development. Contributions and focused bug reports are welcome.