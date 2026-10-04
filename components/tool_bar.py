from PyQt6.QtWidgets import QToolBar, QLabel, QLineEdit, QToolButton, QMenu
from PyQt6.QtCore import QSize, Qt, QTimer, QRectF
from PyQt6.QtGui import QIcon, QFont, QAction, QPainter, QPen, QColor


class DownloadProgressButton(QToolButton):
    def __init__(self, parent):
        super().__init__(parent)
        self._progress = 0
        self._active = False
        self._angle = 0
        self.setFixedSize(36, 34)
        self.setIcon(QIcon("assets/icons/download.svg"))
        self.setIconSize(QSize(17, 17))
        self.setToolTip("Downloads")
        self._spinner = QTimer(self)
        self._spinner.setInterval(60)
        self._spinner.timeout.connect(self._rotate)
        self.clicked.connect(lambda: parent.open_feature_page("downloads"))

    def set_progress(self, progress, active):
        indeterminate = progress is None
        self._progress = 0 if indeterminate else max(0, min(100, int(progress)))
        self._active = active
        if active and indeterminate:
            self._spinner.start()
        else:
            self._spinner.stop()
        self.setToolTip(f"Downloads ({self._progress}%)" if active else "Downloads")
        self.update()

    def _rotate(self):
        self._angle = (self._angle + 24) % 360
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(3, 3, self.width() - 6, self.height() - 6)
        painter.setPen(QPen(QColor("#52616a"), 2))
        painter.drawArc(ring, 0, 360 * 16)
        painter.setPen(QPen(QColor("#c5e982"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        span = 86 * 16 if self._spinner.isActive() else int(360 * 16 * self._progress / 100)
        start = self._angle * 16 if self._spinner.isActive() else 90 * 16
        painter.drawArc(ring, start, span)
        painter.end()


class BookmarkButton(QToolButton):
    def __init__(self, parent):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(36, 34)
        self.setIconSize(QSize(19, 19))
        self.setToolTip("Save bookmark")
        self.clicked.connect(lambda _: parent.toggle_current_bookmark())
        self.set_bookmarked(False, False)

    def set_bookmarked(self, bookmarked, enabled):
        self.setChecked(bookmarked)
        self.setEnabled(enabled)
        self.setIcon(QIcon("assets/icons/star-filled.svg" if bookmarked else "assets/icons/star-empty.svg"))
        self.setToolTip("Remove bookmark" if bookmarked else "Save bookmark")


class ToolBar(QToolBar):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setMovable(False)

        self.setStyleSheet("""
            QToolBar {
                border: none;
                background-color: #0f172a;
                padding: 6px 8px;
            }

            QToolButton {
                color: #e5e7eb;
                background: transparent;
                border: none;
                padding: 4px;
            }

            QToolButton:hover {
                background-color: #1f2937;
                border-radius: 8px;
            }

            QLineEdit {
                background-color: #111827;
                color: #f3f4f6;
                border: 1px solid #374151;
                border-radius: 10px;
                padding: 6px 12px;
            }
        """)
        self.setIconSize(QSize(16, 16))

        button_back = self.addAction("Back")
        button_back.setIcon(QIcon("assets/icons/arrow-left.svg"))
        button_back.setToolTip("Back")
        button_back.triggered.connect(self.parent.main.back)

        button_forward = self.addAction("Forward")
        button_forward.setIcon(QIcon("assets/icons/arrow-right.svg"))
        button_forward.setToolTip("Forward")
        button_forward.triggered.connect(self.parent.main.forward)

        button_refresh = self.addAction("Refresh")
        button_refresh.setIcon(QIcon("assets/icons/refresh.svg"))
        button_refresh.setToolTip("Refresh")
        button_refresh.triggered.connect(self.parent.main.reload)

        search_label = QLabel()
        search_label.setPixmap(QIcon("assets/icons/search.svg").pixmap(QSize(14, 14)))
        search_label.setStyleSheet("background: #1f2937; border: 1px solid #374151; border-radius: 10px 0 0 10px; padding: 6px 10px; margin: 0;")
        self.addWidget(search_label)

        self.url_edit = QLineEdit()
        self.url_edit.setFixedHeight(34)
        self.url_edit.returnPressed.connect(lambda: self.parent.main.navigate(self.url_edit.text()))
        self.url_edit.setPlaceholderText("Search or enter address")
        self.url_edit.setFont(QFont("Poppins", 11))
        self.url_edit.setStyleSheet("QLineEdit { border-left: none; border-radius: 0 10px 10px 0; }")
        self.addWidget(self.url_edit)

        self.bookmark_button = BookmarkButton(parent)
        self.bookmark_button.setToolTip("Save bookmark")
        self.addWidget(self.bookmark_button)

        self.download_indicator = DownloadProgressButton(parent)
        self.addWidget(self.download_indicator)

        self.menu_button = QToolButton()
        self.menu_button.setIcon(QIcon("assets/icons/menu.svg"))
        self.menu_button.setFixedSize(42, 34)
        self.menu_button.setIconSize(QSize(20, 20))
        self.menu_button.setToolTip("Menu")
        self.menu_button.setStyleSheet("QToolButton { background: #1f2937; border: 1px solid #374151; border-radius: 10px; padding: 6px; } QToolButton::menu-indicator { image: none; width: 0; }")
        self.menu = QMenu(self)
        self.menu_button.setMenu(self.menu)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        private_action = QAction(QIcon("assets/icons/incognito.svg"), "New private window", self)
        private_action.triggered.connect(self.parent.open_private_window)
        self.menu.addAction(private_action)
        self.menu.addSeparator()

        for label, icon_name, page in [
            ("Settings", "assets/icons/gear.svg", "settings"),
            ("History", "assets/icons/history.svg", "history"),
            ("Downloads", "assets/icons/download.svg", "downloads"),
            ("Bookmarks", "assets/icons/bookmark.svg", "bookmarks"),
        ]:
            action = QAction(QIcon(icon_name), label, self)
            action.triggered.connect(lambda _, page_name=page: self.parent.open_feature_page(page_name))
            self.menu.addAction(action)

        self.addWidget(self.menu_button)
