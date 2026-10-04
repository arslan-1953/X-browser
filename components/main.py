from PyQt6.QtWidgets import QTabWidget, QPushButton, QMenu
from PyQt6.QtCore import QUrl, QSize
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from urllib.parse import quote
import validators
import os


class BrowserPage(QWebEnginePage):
    def __init__(self, profile, view, browser_window):
        super().__init__(profile, view)
        self.view = view
        self.browser_window = browser_window

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if is_main_frame and url.scheme() == "x-browser":
            self.browser_window.handle_feature_action(self.view, url)
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class BrowserView(QWebEngineView):
    def __init__(self, tab_manager, parent=None):
        super().__init__(parent)
        self.tab_manager = tab_manager

    def createWindow(self, window_type):
        background = window_type == QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        return self.tab_manager.add_tab(popup=True, background=background)

    def contextMenuEvent(self, event):
        request = self.lastContextMenuRequest()
        raw_media_type = request.mediaType() if request else 0
        media_type = int(getattr(raw_media_type, "value", raw_media_type))
        media_url = QUrl(request.mediaUrl()) if request and media_type in (1, 2) else QUrl()
        menu = self.createStandardContextMenu()

        if media_url.isValid():
            menu.addSeparator()
            label = "Download image" if media_type == 1 else "Download video"
            action = menu.addAction(label)
            action.triggered.connect(lambda: self.page().download(media_url))

        menu.exec(event.globalPos())
        menu.deleteLater()


class Main(QTabWidget):
    def __init__(self, parent):
        super().__init__()

        self.parent = parent
        self._tab_titles = {}

        self.homepage_url = QUrl.fromLocalFile(os.path.abspath("homepage/index.html"))

        self.setStyleSheet("""
            QPushButton,
            QTabBar::tab {
                color: #0f172a;
            }

            QPushButton {
                background-color: transparent;
                border: none;
            }

            QTabWidget::pane {
                border: none;
            }

            QPushButton:hover,
            QTabBar::tab,
            QTabBar {
                background-color: #e2e8f0;
            }

            QTabBar::tab {
                padding: 8px 12px;
                border-radius: 8px 8px 0 0;
            }

            QTabBar::tab:selected {
                background-color: #93c5fd;
                color: #0f172a;
            }

            QTabBar::close-button {
                image: url(assets/icons/close.svg);
                padding: 3px;
                margin-bottom: 1px;
            }

            QTabBar QToolButton,
            QTabBar QToolButton:selected {
                background-color: transparent;
                color: #0f172a;
            }
        """)

        self.setFont(QFont("Poppins", 10))

        self.add_tab_button = QPushButton(clicked=self.open_tab)
        self.add_tab_button.setFixedSize(QSize(36, 30))
        self.add_tab_button.setIcon(QIcon("assets/icons/plus.svg"))
        self.add_tab_button.setIconSize(QSize(16, 16))
        self.add_tab_button.setToolTip("New tab")
        self.add_tab_button.setStyleSheet("""
            QPushButton {
                background-color: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 8px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #dbeafe;
            }
        """)

        self.add_tab_button.setParent(self)

        self.tabBarClicked.connect(self.select_tab)
        self.tabCloseRequested.connect(self.close_tab)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setDocumentMode(True)

        self.profile = QWebEngineProfile(self.parent) if self.parent.private_browsing else QWebEngineProfile.defaultProfile()
        if not self.parent.private_browsing:
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.downloadRequested.connect(self.parent.handle_download_requested)

        settings = self.profile.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        if hasattr(QWebEngineSettings.WebAttribute, "BackForwardCacheEnabled"):
            settings.setAttribute(QWebEngineSettings.WebAttribute.BackForwardCacheEnabled, True)

    def start_tab_loading(self, tab):
        index = self.indexOf(tab)
        if index == -1:
            return

        tab.setProperty("loading", True)
        title = self._tab_titles.get(tab, "New Tab")
        self.setTabText(index, f"{title} (0%)")

    def update_tab_progress(self, tab, progress):
        index = self.indexOf(tab)
        if index == -1:
            return

        if progress >= 100:
            self.finish_tab_loading(tab)
            return

        title = self._tab_titles.get(tab, "New Tab")
        self.setTabText(index, f"{title} ({progress}%)")

    def finish_tab_loading(self, tab):
        index = self.indexOf(tab)
        if index == -1:
            return

        tab.setProperty("loading", False)
        title = self._tab_titles.get(tab, "New Tab")
        self.setTabText(index, title)

    def change_url(self):
        tab = self.currentWidget()
        feature_page = tab.property("feature_page")
        url = f"x-browser://{feature_page}" if feature_page else tab.url().toString()
        self.parent.tool_bar.url_edit.setText("" if url == self.homepage_url.toString() else url)
        self.parent.update_bookmark_button()

    def change_title(self, tab, title):
        title = title or "New Tab"
        self._tab_titles[tab] = title

        if not tab.property("loading"):
            self.setTabText(self.indexOf(tab), title)

        self.move_add_tab_button()

    def change_icon(self, tab, icon):
        self.setTabIcon(self.indexOf(tab), icon)
        self.move_add_tab_button()

    def resizeEvent(self, event):
        self.move_add_tab_button()

    def move_add_tab_button(self):
        tap_bar = self.tabBar()
        tap_bar.setFixedWidth(0)

        tabs_width = 0

        for i in range(tap_bar.count()):
            tabs_width += tap_bar.tabRect(i).width()

        tap_bar.setFixedWidth(tabs_width)

        width = self.width()
        button_width = self.add_tab_button.width()
        available_width = width - button_width - 12

        if tabs_width > available_width:
            tap_bar.setFixedWidth(max(0, available_width))

        self.add_tab_button.move(tap_bar.width() + 8, 4)

    def select_tab(self, index):
        self.setCurrentIndex(index)
        self.change_url()

    def close_tab(self, index):
        if self.count() > 1:
            self.removeTab(index)
            self.move_add_tab_button()
        else:
            self.parent.close()

    def open_tab(self):
        self.add_tab()
        self.move_add_tab_button()

    def add_tab(self, url=None, feature_page=None, popup=False, background=False):
        tab = BrowserView(self)
        tab.setPage(BrowserPage(self.profile, tab, self.parent))
        self._tab_titles[tab] = "New Tab"
        tab.urlChanged.connect(self.change_url)
        tab.loadStarted.connect(lambda: self.start_tab_loading(tab))
        tab.loadProgress.connect(lambda progress: self.update_tab_progress(tab, progress))
        tab.loadFinished.connect(lambda ok, t=tab: self._finish_loading(t, ok))
        tab.titleChanged.connect(lambda title: self.change_title(tab, title))
        tab.iconChanged.connect(lambda icon: self.change_icon(tab, icon))
        tab.renderProcessTerminated.connect(lambda status, code, t=tab: self._handle_renderer_crash(t, status, code))

        tab.setProperty("feature_page", feature_page or "")
        self.addTab(tab, feature_page.title() if feature_page else "New Tab")
        if not background:
            self.setCurrentWidget(tab)

        if not popup and feature_page:
            self.parent.load_feature_page(tab, feature_page)
        elif not popup:
            if url:
                tab.setUrl(QUrl(url))
            else:
                self.parent.load_homepage(tab)

        self.change_url()
        return tab

    def _handle_renderer_crash(self, tab, status, exit_code):
        tab.setProperty("crashed_url", tab.url().toString())
        tab.setHtml(
            "<!doctype html><html><meta charset='utf-8'><title>Page stopped</title>"
            "<style>body{margin:0;background:#101b20;color:#edf2ef;font:16px sans-serif;display:grid;place-items:center;height:100vh}"
            "main{max-width:440px;padding:32px;border:1px solid #35474b;border-radius:8px;background:#17262b}"
            "button{padding:10px 16px;background:#c5e982;border:0;border-radius:4px;font:inherit;cursor:pointer}</style>"
            "<main><h1>Page stopped unexpectedly</h1><p>This page could not continue. Other tabs are still available.</p>"
            "<button onclick=\"location.href='x-browser://retry-tab'\">Reload page</button></main></html>"
        )
        self.parent.statusBar().showMessage(f"A page renderer stopped (exit code {exit_code}). Other tabs were not affected.", 6000)

    def retry_tab(self, tab):
        feature_page = tab.property("feature_page")
        if feature_page:
            self.parent.load_feature_page(tab, feature_page)
            return
        url = tab.property("crashed_url")
        if url and url.startswith("file:") and url == self.homepage_url.toString():
            self.parent.load_homepage(tab)
        elif url:
            tab.setUrl(QUrl(url))
        else:
            self.parent.load_homepage(tab)

    def _finish_loading(self, tab, ok):
        self.finish_tab_loading(tab)
        if ok and tab.url().toString() == self.homepage_url.toString():
            self.parent.configure_homepage(tab)

    def open_feature_page(self, page_name):
        if page_name not in ("settings", "history", "downloads", "bookmarks"):
            return
        self.add_tab(feature_page=page_name)

    def back(self):
        self.currentWidget().back()

    def forward(self):
        self.currentWidget().forward()

    def reload(self):
        self.currentWidget().reload()

    def navigate(self, url):
        if url.lower().startswith("x-browser://"):
            page_name = url[len("x-browser://"):].split("/", 1)[0].split("?", 1)[0]
            if page_name == "retry-tab":
                self.retry_tab(self.currentWidget())
                return
            self.open_feature_page(page_name)
            return

        if not self.count():
            self.add_tab()
        browser = self.currentWidget()
        browser.setProperty("feature_page", "")
        browser.setProperty("is_homepage", False)

        if os.path.exists(url):
            browser.setUrl(QUrl.fromLocalFile(url))
            return

        if validators.url(url):
            normalized_url = url
        elif validators.domain(url):
            normalized_url = f"http://{url}"
        else:
            engine = self.parent.settings.value("browser/search_engine", "duckduckgo")
            query = quote(url)

            if engine == "google":
                normalized_url = f"https://www.google.com/search?q={query}"
            elif engine == "bing":
                normalized_url = f"https://www.bing.com/search?q={query}"
            else:
                normalized_url = f"https://duckduckgo.com/?q={query}"

        browser.setUrl(QUrl(normalized_url))
        self.parent.add_history_entry(normalized_url)
