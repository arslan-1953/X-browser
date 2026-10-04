from PyQt6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox
from PyQt6.QtCore import Qt, QSettings, QUrl
from PyQt6.QtGui import QFontDatabase, QIcon, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtCore import QStandardPaths, QTimer
from components.tool_bar import ToolBar
from components.main import Main
from components.downloader import DownloadWorker
import json
import os
import re
import sys
import uuid
from html import escape
from datetime import datetime
from urllib.parse import parse_qs


class MainWindow(QMainWindow):
    def __init__(self, private_browsing=False):
        super().__init__()
        self.private_browsing = private_browsing
        self._private_windows = []
        self.settings = QSettings("XBrowser", "X Browser")
        self.history = [] if private_browsing else self._normalize_history(self.settings.value("browser/history", [], type=list))
        self.downloads = [] if private_browsing else self._normalize_downloads(self.settings.value("browser/downloads", [], type=list))
        self.bookmarks = self._normalize_bookmarks(self.settings.value("browser/bookmarks", [], type=list))
        self.features_dir = os.path.join(os.path.dirname(__file__), "features")
        self.download_directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        os.makedirs(self.download_directory, exist_ok=True)
        self.active_downloads = set()
        self.pending_downloads = []
        self.download_workers = {}
        self.download_refresh_timer = QTimer(self)
        self.download_refresh_timer.setInterval(750)
        self.download_refresh_timer.timeout.connect(lambda: self._save_downloads(refresh=True))

        self.setWindowTitle("X Browser (Private)" if private_browsing else "X Browser")
        self.setWindowIcon(QIcon("assets/brand/logo-small.svg"))
        self.setMinimumSize(420, 480)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b1020;
                color: #e5e7eb;
                border: none;
            }
        """)

        self.main = Main(self)
        self.tool_bar = ToolBar(self)
        self.addToolBar(self.tool_bar)
        self.setCentralWidget(self.main)
        self.update_bookmark_button()
        self.private_window_shortcut = QShortcut(QKeySequence("Ctrl+Shift+T"), self)
        self.private_window_shortcut.activated.connect(self.open_private_window)

        if private_browsing or self.settings.value("browser/open_on_start", True, type=bool):
            startup_url = "" if private_browsing else self.settings.value("browser/startup_url", "").strip()
            if startup_url.startswith("x-browser://"):
                self.open_feature_page(startup_url[len("x-browser://"):].split("?", 1)[0])
            elif startup_url:
                self.main.navigate(startup_url)
            else:
                self.main.add_tab()

    def _normalize_history(self, entries):
        normalized = []
        for entry in entries or []:
            if isinstance(entry, dict):
                url = entry.get("url") or ""
                if not url:
                    continue
                normalized.append({
                    "title": entry.get("title") or url,
                    "url": url,
                    "time": entry.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
            elif isinstance(entry, str):
                normalized.append({
                    "title": entry,
                    "url": entry,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
        return normalized

    def _normalize_downloads(self, entries):
        normalized = []
        for entry in entries or []:
            if isinstance(entry, dict):
                name = entry.get("name") or "Download"
                path = entry.get("path") or ""
                if not path:
                    continue
                status = str(entry.get("status") or "Complete")
                if status.startswith("Downloading") or status in ("Queued", "Paused"):
                    status = "Interrupted"
                normalized.append({
                    "id": entry.get("id") or uuid.uuid4().hex,
                    "name": name,
                    "path": path,
                    "url": entry.get("url") or "",
                    "size": entry.get("size") or "",
                    "time": entry.get("time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": status,
                    "error": str(entry.get("error") or ""),
                    "progress": int(entry.get("progress") or 0),
                })
        return normalized

    @staticmethod
    def _normalize_bookmarks(entries):
        normalized = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url") or "").strip()
            if not url:
                continue
            normalized.append({"title": str(entry.get("title") or url), "url": url})
        return normalized

    def _feature_path(self, page_name):
        return os.path.join(self.features_dir, f"{page_name}.html")

    def _read_feature_file(self, page_name):
        with open(self._feature_path(page_name), "r", encoding="utf-8") as handle:
            return handle.read()

    def load_feature_page(self, tab, page_name):
        feature_base = QUrl.fromLocalFile(self.features_dir + os.sep)
        if page_name == "settings":
            html = self._read_feature_file(page_name)
            engine = self.settings.value("browser/search_engine", "duckduckgo")
            checked = "checked" if self.settings.value("browser/open_on_start", True, type=bool) else ""
            startup_url = escape(str(self.settings.value("browser/startup_url", "")), quote=True)
            fast_mode = "checked" if self.settings.value("browser/download_mode", "normal") == "fast" else ""
            news_checked = "checked" if self.settings.value("homepage/news_enabled", False, type=bool) else ""
            weather_checked = "checked" if self.settings.value("homepage/weather_enabled", False, type=bool) else ""
            city = self.settings.value("homepage/weather_city", "")
            wallpapers = self._available_wallpapers()
            wallpaper = self._homepage_wallpaper()
            html = html.replace("__SEARCH_ENGINE__", engine).replace("__OPEN_ON_START__", checked).replace("__FAST_DOWNLOAD__", fast_mode)
            html = html.replace("__STARTUP_URL__", startup_url)
            html = html.replace("__HOME_NEWS__", news_checked).replace("__HOME_WEATHER__", weather_checked).replace("__HOME_CITY__", escape(str(city), quote=True))
            html = html.replace("__WALLPAPER_OPTIONS__", self._json_for_html(wallpapers))
            html = html.replace("__HOME_WALLPAPER__", self._json_for_html(wallpaper))
            tab.setHtml(html, feature_base)
        elif page_name == "history":
            html = self._read_feature_file(page_name).replace("__HISTORY_ITEMS__", self._json_for_html(self.history))
            tab.setHtml(html, feature_base)
        elif page_name == "downloads":
            html = self._read_feature_file(page_name).replace("__DOWNLOAD_ITEMS__", self._json_for_html(self.downloads))
            tab.setHtml(html, feature_base)
        elif page_name == "bookmarks":
            html = self._read_feature_file(page_name).replace("__BOOKMARK_ITEMS__", self._json_for_html(self.bookmarks))
            tab.setHtml(html, feature_base)

    @staticmethod
    def _json_for_html(value):
        return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    def load_homepage(self, tab):
        homepage_path = os.path.join(os.path.dirname(__file__), "homepage", "index.html")
        tab.setUrl(QUrl.fromLocalFile(homepage_path))

    def configure_homepage(self, tab):
        config = {
            "news": self.settings.value("homepage/news_enabled", False, type=bool),
            "weather": self.settings.value("homepage/weather_enabled", False, type=bool),
            "city": self.settings.value("homepage/weather_city", ""),
            "wallpaper": self._homepage_wallpaper(),
        }
        tab.page().runJavaScript(f"window.configureHomepage({self._json_for_html(config)});")

    def _update_homepage_wallpapers(self):
        wallpaper = self._json_for_html(self._homepage_wallpaper())
        for index in range(self.main.count()):
            tab = self.main.widget(index)
            if tab.url().toString() == self.main.homepage_url.toString():
                tab.page().runJavaScript(f"if (window.setHomepageWallpaper) window.setHomepageWallpaper({wallpaper});")

    def _homepage_wallpaper(self):
        wallpaper = self.settings.value("homepage/wallpaper", "")
        if wallpaper and os.path.isfile(QUrl(wallpaper).toLocalFile()):
            return wallpaper
        default_wallpaper = os.path.join(os.path.dirname(__file__), "assets", "wallpapers", "1.jpg")
        return QUrl.fromLocalFile(default_wallpaper).toString()

    def _available_wallpapers(self):
        wallpaper_dir = os.path.join(os.path.dirname(__file__), "assets", "wallpapers")
        return [
            {
                "url": QUrl.fromLocalFile(os.path.join(wallpaper_dir, name)).toString(),
                "label": f"Wallpaper {os.path.splitext(name)[0]}",
            }
            for name in sorted(os.listdir(wallpaper_dir))
            if os.path.splitext(name)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
        ]

    def open_feature_page(self, page_name):
        self.main.open_feature_page(page_name)

    def update_bookmark_button(self):
        if not hasattr(self, "tool_bar") or not self.main.count():
            return
        tab = self.main.currentWidget()
        url = tab.url().toString()
        is_page = url.startswith(("http://", "https://")) and not tab.property("feature_page")
        bookmarked = any(item["url"] == url for item in self.bookmarks)
        self.tool_bar.bookmark_button.set_bookmarked(bookmarked, is_page)

    def toggle_current_bookmark(self):
        if not self.main.count():
            return
        tab = self.main.currentWidget()
        url = tab.url().toString()
        if not url.startswith(("http://", "https://")):
            self.update_bookmark_button()
            return

        existing = next((item for item in self.bookmarks if item["url"] == url), None)
        if existing:
            answer = QMessageBox.question(
                self,
                "Remove bookmark",
                f"Remove {existing['title']} from bookmarks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.bookmarks.remove(existing)
        else:
            title = tab.title() or QUrl(url).host() or url
            answer = QMessageBox.question(
                self,
                "Save bookmark",
                f"Save {title} to bookmarks?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.bookmarks.insert(0, {"title": title, "url": url})

        self.settings.setValue("browser/bookmarks", self.bookmarks)
        self.update_bookmark_button()

    def open_bookmark_page(self):
        self.open_feature_page("bookmarks")

    def open_private_window(self):
        private_window = MainWindow(private_browsing=True)
        self._private_windows.append(private_window)
        private_window.show()

    def handle_feature_action(self, tab, url):
        action_name = url.host() or url.path().lstrip("/")
        query = parse_qs(url.query())
        payload = query.get("payload", ["{}"])[0]
        try:
            value = json.loads(payload) if payload else {}
        except (TypeError, json.JSONDecodeError):
            value = {}

        if action_name == "settings-save":
            engine = value.get("searchEngine")
            if engine in ("duckduckgo", "google", "bing"):
                self.settings.setValue("browser/search_engine", engine)
            self.settings.setValue("browser/open_on_start", bool(value.get("openOnStart", False)))
            self.settings.setValue("browser/startup_url", value.get("startupUrl", "").strip()[:2048])
            download_mode = "fast" if value.get("fastDownload") else "normal"
            self.settings.setValue("browser/download_mode", download_mode)
            self.settings.setValue("homepage/news_enabled", bool(value.get("homepageNews", False)))
            self.settings.setValue("homepage/weather_enabled", bool(value.get("homepageWeather", False)))
            self.settings.setValue("homepage/weather_city", value.get("weatherCity", "").strip()[:80])
            selected_wallpaper = value.get("wallpaper", "")
            wallpaper_urls = {wallpaper["url"] for wallpaper in self._available_wallpapers()}
            current_wallpaper = self._homepage_wallpaper()
            if selected_wallpaper in wallpaper_urls or selected_wallpaper == current_wallpaper:
                self.settings.setValue("homepage/wallpaper", selected_wallpaper)
                self._update_homepage_wallpapers()
            if download_mode == "normal":
                while self.pending_downloads:
                    download_id = self.pending_downloads.pop(0)
                    record = self._find_download(download_id)
                    if record:
                        self._start_download(record)
            self.load_feature_page(tab, "settings")
        elif action_name == "search":
            query_text = value.get("query", "").strip()
            if query_text:
                self.main.navigate(query_text)
        elif action_name == "retry-tab":
            self.main.retry_tab(tab)
        elif action_name == "bookmark-open":
            target = value.get("url", "")
            if target:
                self.main.navigate(target)
        elif action_name == "bookmark-delete":
            target = value.get("url", "")
            self.bookmarks = [item for item in self.bookmarks if item["url"] != target]
            self.settings.setValue("browser/bookmarks", self.bookmarks)
            self.load_feature_page(tab, "bookmarks")
            self.update_bookmark_button()
        elif action_name == "bookmark-edit":
            old_url = value.get("oldUrl", "")
            new_url = value.get("url", "").strip()
            title = value.get("title", "").strip()
            if old_url and new_url and title:
                parsed = QUrl(new_url)
                if not parsed.scheme():
                    new_url = "https://" + new_url
                for item in self.bookmarks:
                    if item["url"] == old_url:
                        item.update({"url": new_url, "title": title})
                        break
                self.bookmarks = self._normalize_bookmarks(self.bookmarks)
                self.settings.setValue("browser/bookmarks", self.bookmarks)
            self.load_feature_page(tab, "bookmarks")
            self.update_bookmark_button()
        elif action_name == "history-open":
            target = value.get("url")
            if target:
                self.main.navigate(target)
        elif action_name == "history-delete":
            urls = set(value.get("items", []))
            self.history = [entry for entry in self.history if entry["url"] not in urls]
            if not self.private_browsing:
                self.settings.setValue("browser/history", self.history)
            self.load_feature_page(tab, "history")
        elif action_name == "history-clear":
            self.history = self._history_after_range_clear(value.get("range", "all"))
            if not self.private_browsing:
                self.settings.setValue("browser/history", self.history)
            self.load_feature_page(tab, "history")
        elif action_name in ("downloads-clear", "download-clear"):
            self.downloads = [
                item for item in self.downloads
                if item.get("id") in self.download_workers or item.get("status") == "Queued"
            ]
            self._save_downloads()
            self.load_feature_page(tab, "downloads")
        elif action_name == "wallpaper-choose":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Choose homepage wallpaper",
                "",
                "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
            )
            if path:
                self.settings.setValue("homepage/wallpaper", QUrl.fromLocalFile(path).toString())
                self._update_homepage_wallpapers()
            self.load_feature_page(tab, "settings")
        elif action_name == "download-open":
            path = value.get("path", "")
            if path and os.path.isfile(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif action_name == "download-copy-url":
            download = self._find_download(value.get("id", ""))
            if download and download.get("url"):
                QApplication.clipboard().setText(download["url"])
                self.statusBar().showMessage("Download URL copied to clipboard.", 3000)
            else:
                self.statusBar().showMessage("The original download URL is not available.", 4000)
        elif action_name == "download-toggle":
            self._toggle_download(value.get("id", ""))
        elif action_name in ("download-retry", "download-redownload"):
            download = self._find_download(value.get("id", ""))
            if download:
                self.retry_download(download["id"])
        elif action_name == "download-cancel":
            self.cancel_download(value.get("id", ""))
        elif action_name == "download-show-folder":
            path = value.get("path", "")
            folder = os.path.dirname(path) if path else self.download_directory
            if os.path.isdir(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _history_after_range_clear(self, history_range):
        durations = {"past-hour": 3600, "past-day": 86400, "past-week": 604800}
        seconds = durations.get(history_range)
        if seconds is None:
            return []
        cutoff = datetime.now().timestamp() - seconds
        retained = []
        for entry in self.history:
            try:
                timestamp = datetime.strptime(entry["time"], "%Y-%m-%d %H:%M:%S").timestamp()
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp < cutoff:
                retained.append(entry)
        return retained

    def handle_download_requested(self, request):
        source_url = request.url().toString()
        filename = request.downloadFileName() or "download"
        request.cancel()
        self.start_download(source_url, filename)

    def start_download(self, source_url, filename="download"):
        parsed_url = QUrl(source_url)
        is_supported_url = parsed_url.isValid() and parsed_url.scheme().lower() in ("http", "https")
        filename = self._available_download_name(filename)
        record = {
            "id": uuid.uuid4().hex,
            "name": filename,
            "path": os.path.join(self.download_directory, filename),
            "url": source_url,
            "size": "0 B",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Queued" if is_supported_url else "Failed",
            "error": "" if is_supported_url else "X Downloader v2 supports HTTP and HTTPS URLs only.",
            "progress": 0,
            "version": 2,
        }
        self.downloads.insert(0, record)
        self.downloads = self.downloads[:100]
        self._save_downloads(refresh=True)
        if not is_supported_url:
            self._refresh_download_indicator()
            return record["id"]
        if self.settings.value("browser/download_mode", "normal") == "fast" and self.active_downloads:
            self.pending_downloads.append(record["id"])
            self._refresh_download_indicator()
            return record["id"]
        self._start_download(record)
        return record["id"]

    def _start_download(self, record):
        download_id = record["id"]
        if download_id in self.download_workers:
            worker = self.download_workers[download_id]
            if self.settings.value("browser/download_mode", "normal") == "fast" and self.active_downloads - {download_id}:
                if download_id not in self.pending_downloads:
                    self.pending_downloads.append(download_id)
                record["status"] = "Queued"
            else:
                self.active_downloads.add(download_id)
                record["status"] = "Downloading"
                worker.resume()
            self._save_downloads(refresh=True)
            self._refresh_download_indicator()
            return

        self.active_downloads.add(download_id)
        record["status"] = "Downloading"
        record["error"] = ""
        worker = DownloadWorker(record["url"], record["path"], download_id, self)
        worker.progress_changed.connect(lambda received, total, key=download_id: self._download_progress_changed(key, received, total))
        worker.status_changed.connect(lambda status, key=download_id: self._download_status_changed(key, status))
        worker.completed.connect(lambda success, message, key=download_id: self._download_finished(key, success, message))
        worker.finished.connect(lambda key=download_id: self._release_download_worker(key))
        self.download_workers[download_id] = worker
        worker.start()
        self._save_downloads(refresh=True)
        self._refresh_download_indicator()

    def _download_progress_changed(self, download_id, received, total):
        record = self._find_download(download_id)
        if not record or record["status"] in ("Paused", "Pausing", "Queued", "Cancelling"):
            return
        record["size"] = self._format_download_size(received)
        record["progress"] = min(100, int(received * 100 / total)) if total > 0 else 0
        record["status"] = f"Downloading {record['progress']}%" if total > 0 else "Downloading"
        self._refresh_download_indicator()
        if not self.download_refresh_timer.isActive():
            self.download_refresh_timer.start()

    def _download_status_changed(self, download_id, status):
        record = self._find_download(download_id)
        if not record:
            return
        if status == "Paused":
            record["status"] = "Paused"
            self.active_downloads.discard(download_id)
            self._start_next_fast_download()
        elif status in ("Connecting", "Downloading"):
            record["status"] = "Downloading"
        elif status == "Merging file":
            record["status"] = "Finalizing"
        record["phase"] = status
        self._save_downloads(refresh=True)
        self._refresh_download_indicator()

    def _download_finished(self, download_id, success, message):
        record = self._find_download(download_id)
        self.active_downloads.discard(download_id)
        if record:
            if success:
                record["status"] = "Complete"
                record["size"] = self._format_download_size(os.path.getsize(record["path"]))
                record["progress"] = 100
                record["error"] = message
            else:
                record["status"] = "Cancelled" if message == "Cancelled" else "Failed"
                record["error"] = "" if message == "Cancelled" else message
        self._save_downloads(refresh=True)
        self._refresh_download_indicator()
        self._start_next_fast_download()

    def _release_download_worker(self, download_id):
        worker = self.download_workers.pop(download_id, None)
        if worker:
            worker.deleteLater()

    @staticmethod
    def _format_download_size(size):
        if size >= 1024 * 1024:
            return f"{size / 1024 / 1024:.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size} B"

    def _start_next_fast_download(self):
        if self.settings.value("browser/download_mode", "normal") != "fast" or self.active_downloads:
            return
        while self.pending_downloads:
            download_id = self.pending_downloads.pop(0)
            record = self._find_download(download_id)
            if record and record["status"] in ("Queued", "Paused"):
                self._start_download(record)
                return

    def _find_download(self, download_id):
        return next((item for item in self.downloads if item.get("id") == download_id), None)

    def _toggle_download(self, download_id):
        record = self._find_download(download_id)
        if not record:
            return
        worker = self.download_workers.get(download_id)
        if record["status"] == "Queued" and not worker:
            self.pending_downloads = [item for item in self.pending_downloads if item != download_id]
            record["status"] = "Cancelled"
            record["error"] = "Cancelled before the transfer started."
        elif record["status"] == "Paused" and worker:
            self.resume_download(download_id)
        elif record["status"].startswith("Downloading") and worker:
            self.pause_download(download_id)
        self._save_downloads(refresh=True)
        self._refresh_download_indicator()

    def pause_download(self, download_id):
        record = self._find_download(download_id)
        worker = self.download_workers.get(download_id)
        if not record or not worker or not record["status"].startswith("Downloading"):
            return False
        worker.pause()
        record["status"] = "Pausing"
        self._save_downloads(refresh=True)
        return True

    def resume_download(self, download_id):
        record = self._find_download(download_id)
        worker = self.download_workers.get(download_id)
        if not record or not worker or record["status"] != "Paused":
            return False
        if self.settings.value("browser/download_mode", "normal") == "fast" and self.active_downloads:
            if download_id not in self.pending_downloads:
                self.pending_downloads.append(download_id)
            record["status"] = "Queued"
        else:
            self._start_download(record)
        self._save_downloads(refresh=True)
        return True

    def cancel_download(self, download_id):
        record = self._find_download(download_id)
        if not record:
            return False
        worker = self.download_workers.get(download_id)
        if worker:
            worker.cancel()
            record["status"] = "Cancelling"
        elif record["status"] == "Queued":
            self.pending_downloads = [item for item in self.pending_downloads if item != download_id]
            record["status"] = "Cancelled"
            record["error"] = "Cancelled before the transfer started."
        else:
            return False
        self._save_downloads(refresh=True)
        self._refresh_download_indicator()
        return True

    def _available_download_name(self, filename):
        filename = os.path.basename(str(filename).replace("\\", "/")).strip() or "download"
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).rstrip(" .") or "download"
        stem, extension = os.path.splitext(filename)
        if stem.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)[1-9]", stem.upper()):
            filename = f"_{filename}"
            stem, extension = os.path.splitext(filename)
        candidate = filename
        suffix = 1
        reserved = {item.get("path") for item in self.downloads}
        while os.path.exists(os.path.join(self.download_directory, candidate)) or os.path.join(self.download_directory, candidate) in reserved:
            candidate = f"{stem} ({suffix}){extension}"
            suffix += 1
        return candidate

    def retry_download(self, download_id):
        record = self._find_download(download_id)
        if not record:
            return False
        source_url = record.get("url", "")
        url = QUrl(source_url)
        if not source_url or not url.isValid() or url.scheme().lower() not in ("http", "https"):
            self.statusBar().showMessage("This download does not have a retryable HTTP or HTTPS URL.", 4000)
            return False

        return self.start_download(source_url, record.get("name") or "download")

    def _save_downloads(self, refresh=False):
        if not self.private_browsing:
            self.settings.setValue("browser/downloads", self.downloads)
        if refresh:
            self.download_refresh_timer.stop()
            for index in range(self.main.count()):
                tab = self.main.widget(index)
                if tab.property("feature_page") == "downloads":
                    data = self._json_for_html(self.downloads)
                    tab.page().runJavaScript(f"if (window.updateDownloads) window.updateDownloads({data});")

    def _refresh_download_indicator(self):
        if not hasattr(self, "tool_bar"):
            return
        active_items = [item for item in self.downloads if item["id"] in self.active_downloads]
        queued_items = [item for item in self.downloads if item["status"] == "Queued"]
        visible_items = active_items or queued_items
        if visible_items and all(item.get("progress", 0) == 0 for item in visible_items):
            progress = None
        elif visible_items:
            progress = sum(item.get("progress", 0) for item in visible_items) / len(visible_items)
        else:
            progress = 0
        self.tool_bar.download_indicator.set_progress(progress, bool(visible_items))

    def add_history_entry(self, url):
        if self.private_browsing or not url:
            return
        for entry in self.history:
            if entry.get("url") == url:
                entry["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.settings.setValue("browser/history", self.history)
                return

        self.history.insert(0, {
            "title": url,
            "url": url,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.history = self.history[:30]
        self.settings.setValue("browser/history", self.history)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_L:
                self.tool_bar.url_edit.setFocus()
                self.tool_bar.url_edit.selectAll()
                return
            if event.key() == Qt.Key.Key_T:
                self.main.open_tab()
                return
            if event.key() == Qt.Key.Key_W:
                self.main.close_tab(self.main.currentIndex())
                return
            if event.key() == Qt.Key.Key_R:
                self.main.reload()
                return

        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            if event.key() == Qt.Key.Key_Left:
                self.main.back()
                return
            if event.key() == Qt.Key.Key_Right:
                self.main.forward()
                return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        running_workers = [worker for worker in self.download_workers.values() if worker.isRunning()]
        if running_workers:
            for worker in running_workers:
                worker.cancel()
            event.ignore()
            self.statusBar().showMessage("Stopping downloads before closing...")
            QTimer.singleShot(100, self.close)
            return
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont("assets/fonts/poppins/poppins-v19-latin-500.ttf")
    QFontDatabase.addApplicationFont("assets/fonts/poppins/poppins-v19-latin-600.ttf")
    QFontDatabase.addApplicationFont("assets/fonts/poppins/poppins-v19-latin-700.ttf")
    QFontDatabase.addApplicationFont("assets/fonts/poppins/poppins-v19-latin-regular.ttf")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
