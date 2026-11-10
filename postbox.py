import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QColor, QFont, QTextCursor, QIcon, QPixmap, \
    QPainter, QPen
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QVBoxLayout, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QComboBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QListWidget,
                               QListWidgetItem, QSplitter, QLabel,
                               QTabWidget, QHeaderView, QDockWidget,
                               QFileDialog)

BG = "#2b2b2b"
PANEL = "#3a3a3a"
TXT = "#d8d8d8"
ACC = "#007acc"

HIST = Path(__file__).parent / "history.json"

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class Worker(QThread):
    done = Signal(dict)

    def __init__(self, method, url, headers, body):
        super().__init__()
        self.method, self.url, self.headers, self.body = \
            method, url, headers, body

    def run(self):
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(
                self.url, method=self.method,
                data=self.body or None,
                headers=self.headers or {})
            req.add_header("User-Agent", "postbox/1.0")
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                self.done.emit({
                    "ok": True, "status": r.status,
                    "reason": r.reason,
                    "headers": dict(r.headers),
                    "body": raw, "ms": (time.monotonic() - t0) * 1000,
                })
        except urllib.error.HTTPError as e:
            self.done.emit({
                "ok": True, "status": e.code, "reason": e.reason,
                "headers": dict(e.headers or {}), "body": e.read(),
                "ms": (time.monotonic() - t0) * 1000,
            })
        except Exception as e:
            self.done.emit({"ok": False, "error": str(e),
                            "ms": (time.monotonic() - t0) * 1000})


def mk_icon():
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#4ea3ff"), 2))
    p.setBrush(QColor("#1e4e7d"))
    p.drawRoundedRect(3, 7, 26, 18, 3, 3)
    p.setPen(QPen(QColor("#4ea3ff"), 2))
    p.drawLine(4, 9, 16, 18)
    p.drawLine(28, 9, 16, 18)
    p.end()
    return QIcon(px)


class Win(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("postbox")
        self.setWindowIcon(mk_icon())
        self.resize(1100, 720)
        self.worker = None

        bar = QHBoxLayout()
        self.method = QComboBox()
        self.method.addItems(METHODS)
        self.method.setFixedWidth(100)
        bar.addWidget(self.method)
        self.url = QLineEdit("https://api.github.com")
        self.url.setFont(QFont("Consolas", 10))
        self.url.setPlaceholderText("https://...")
        bar.addWidget(self.url, 1)
        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet(
            "QPushButton { background:%s; color:#fff; border:0; "
            "padding:6px 20px; } QPushButton:hover { background:#1490e0; }"
            % ACC)
        self.send_btn.clicked.connect(self.send)
        bar.addWidget(self.send_btn)

        self.tabs = QTabWidget()
        self.body = QPlainTextEdit()
        self.body.setFont(QFont("Consolas", 10))
        self.body.setPlaceholderText('{"json": "body"}')
        self.tabs.addTab(self.body, "Body")
        self.headers = QTableWidget(2, 2)
        self.headers.setHorizontalHeaderLabels(["header", "value"])
        self.headers.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.headers.setItem(0, 0, QTableWidgetItem("User-Agent"))
        self.headers.setItem(0, 1, QTableWidgetItem("postbox"))
        self.headers.itemChanged.connect(self._grow_rows)
        self.tabs.addTab(self.headers, "Headers")

        self.resp = QPlainTextEdit()
        self.resp.setReadOnly(True)
        self.resp.setFont(QFont("Consolas", 10))
        self.resp.setPlaceholderText("response shows here")

        right = QSplitter(Qt.Vertical)
        right.addWidget(self.tabs)
        right.addWidget(self.resp)
        right.setSizes([300, 400])

        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(6, 6, 6, 6)
        ml.addLayout(bar)
        ml.addWidget(right)

        self.hist = QListWidget()
        self.hist.itemDoubleClicked.connect(self._hist_load)
        dock = QDockWidget("History", self)
        dock.setObjectName("hist")
        dock.setWidget(self.hist)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        split = QSplitter(Qt.Horizontal)
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(mid)
        self.setCentralWidget(cw)

        self._load_history()
        self.statusBar().showMessage("ready")

    def _grow_rows(self, item):
        if item.row() == self.headers.rowCount() - 1 and item.text().strip():
            self.headers.blockSignals(True)
            self.headers.setRowCount(self.headers.rowCount() + 1)
            self.headers.blockSignals(False)

    def _hdrs(self):
        out = {}
        for r in range(self.headers.rowCount()):
            k = self.headers.item(r, 0)
            v = self.headers.item(r, 1)
            if k and k.text().strip():
                out[k.text().strip()] = v.text() if v else ""
        return out

    def send(self):
        if self.worker and self.worker.isRunning():
            return
        url = self.url.text().strip()
        if not url:
            return
        body = self.body.toPlainText().encode() or None
        self.send_btn.setEnabled(False)
        self.resp.setPlainText("sending...")
        self.worker = Worker(self.method.currentText(), url,
                             self._hdrs(), body)
        self.worker.done.connect(self._done)
        self.worker.start()

    def _done(self, r):
        self.send_btn.setEnabled(True)
        if not r["ok"]:
            self.resp.setPlainText("request failed: " + r["error"])
            self.statusBar().showMessage("failed")
            return
        body = r["body"]
        try:
            pretty = json.dumps(json.loads(body.decode("utf-8")),
                                indent=2, ensure_ascii=False)
        except Exception:
            pretty = body.decode("utf-8", errors="replace")
        hdr = "\n".join("%s: %s" % kv for kv in
                        list(r["headers"].items())[:12])
        self.resp.setPlainText(
            "HTTP %s %s   %.0f ms   %d bytes\n\n%s\n\n--- body ---\n%s"
            % (r["status"], r["reason"], r["ms"], len(body), hdr, pretty))
        col = "#7bc96f" if r["status"] < 400 else "#d15b5b"
        self.statusBar().showMessage(
            "%s %s -> %s in %.0f ms" % (self.method.currentText(),
                                        self.url.text()[:40],
                                        r["status"], r["ms"]))
        self._add_hist(self.method.currentText(), self.url.text(),
                       r["status"], col)

    def _add_hist(self, m, u, status, col):
        it = QListWidgetItem("%s  %s  -> %s" % (m, u, status))
        it.setData(Qt.UserRole, (m, u))
        it.setForeground(QColor(col))
        self.hist.insertItem(0, it)
        while self.hist.count() > 50:
            self.hist.takeItem(self.hist.count() - 1)
        self._save_history()

    def _hist_load(self, it):
        m, u = it.data(Qt.UserRole)
        self.method.setCurrentText(m)
        self.url.setText(u)

    def _load_history(self):
        if HIST.exists():
            try:
                for m, u, s in json.loads(HIST.read_text())[:50]:
                    col = "#7bc96f" if str(s)[0] in "23" else "#d15b5b"
                    it = QListWidgetItem("%s  %s  -> %s" % (m, u, s))
                    it.setData(Qt.UserRole, (m, u))
                    it.setForeground(QColor(col))
                    self.hist.addItem(it)
            except Exception:
                pass

    def _save_history(self):
        out = []
        for i in range(self.hist.count()):
            it = self.hist.item(i)
            m, u = it.data(Qt.UserRole)
            s = it.text().rsplit("-> ", 1)[-1]
            out.append((m, u, s))
        HIST.write_text(json.dumps(out))


def launch():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow, QWidget, QDockWidget { background: %s; color: %s; }
        QLineEdit, QPlainTextEdit, QTableWidget, QListWidget, QComboBox {
            background: %s; color: %s; border: 1px solid #222;
            selection-background-color: #5a6b7d; }
        QTabWidget::pane { border: 1px solid #222; }
        QTabBar::tab { background: %s; color: %s; padding: 5px 14px; }
        QTabBar::tab:selected { background: %s; color: #fff; }
        QHeaderView::section { background: %s; color: %s; border: 0;
            padding: 4px; }
        QPushButton { background: %s; color: #fff; border: 0;
            padding: 5px 14px; }
        QPushButton:hover { background: #5a5a5a; }
        QDockWidget { font-weight: bold; }
        QDockWidget::title { background: %s; padding: 5px;
            border-bottom: 1px solid #222; }
        QStatusBar { background: #007acc; color: #fff; }
        QSplitter::handle { background: #222; }
    """ % (PANEL, TXT, BG, TXT, PANEL, TXT, BG, PANEL, TXT, "#4a4a4a",
           "#3a3a3a"))
    w = Win()
    w.show()
    if "--shot" in sys.argv:
        def snap():
            w.grab().toImage().save("shot.png")
            app.quit()
        QTimer.singleShot(2500, snap)
    app.exec()


if __name__ == "__main__":
    launch()
