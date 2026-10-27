from pathlib import Path
import os
import re
import sys
import traceback

from PySide6.QtCore import QThread, Signal, QSettings, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QProgressBar,
    QPlainTextEdit, QFileDialog, QMessageBox, QInputDialog)
from deck_installer import core


TEXT = {
    'title': ('巴扎加加 · Steam Deck 安装器', 'BazaarPlusPlus · Steam Deck Installer'),
    'subtitle': ('为 Proton 版 The Bazaar 安装官方 Windows Mod', 'Install the official Windows mod for The Bazaar under Proton'),
    'directory': ('游戏目录', 'Game folder'),
    'browse': ('选择目录…', 'Browse…'),
    'detect': ('自动检测', 'Detect game'),
    'install': ('一键安装 / 更新', 'Install / Update'),
    'local': ('导入本地 EXE…', 'Import local EXE…'),
    'restore': ('恢复最近备份', 'Restore last backup'),
    'logs': ('打开日志文件夹', 'Open logs folder'),
    'ready': ('准备就绪。请先关闭游戏。', 'Ready. Close the game before installing.'),
    'none': ('未检测到游戏，请手动选择游戏目录。', 'Game not detected. Please choose its folder.'),
    'scanning': ('正在扫描 Steam 游戏库，请稍候…', 'Scanning Steam libraries, please wait…'),
    'notfound': ('未找到包含 TheBazaar.exe 和 TheBazaar_Data 的目录。\n\n在 Steam 中打开：游戏 → 属性 → 已安装文件 → 浏览。\n然后回到安装器点击「选择目录」，选择 Steam 打开的目录。\n\n扫描过的位置和读取错误已记录在下方日志中。',
                 'No folder containing TheBazaar.exe and TheBazaar_Data was found.\n\nIn Steam, open Game → Properties → Installed Files → Browse.\nThen use Browse in this installer to select that folder.\n\nScanned locations and read errors are listed in the log.'),
    'multiple': ('检测到多个游戏目录，请选择', 'Multiple game folders found; choose one'),
    'installed': ('当前 Mod：', 'Installed mod: '),
    'unknown': ('未安装 / 未知', 'Not installed / unknown'),
    'done': ('安装完成', 'Installation complete'),
    'failed': ('操作失败', 'Operation failed'),
    'close': ('任务进行中，请等待完成后关闭。', 'An operation is running. Wait for it to finish before closing.'),
    'hash': ('可选：输入来自可信来源的 EXE SHA256。\n留空时联网按官方当前版本校验；旧版或离线安装需提供校验值。',
             'Optional: enter an EXE SHA256 from a trusted source.\nLeave blank to verify against the current official release online. Older/offline packages require a hash.'),
    'hashbad': ('SHA256 必须是 64 位十六进制字符', 'SHA256 must contain 64 hexadecimal characters'),
    'restoreask': ('将恢复最近一次安装前的 Mod 文件。请确认游戏已关闭。',
                   'Restore the mod files saved before the last installation. Close the game first.'),
    'restored': ('备份已恢复', 'Backup restored'),
    'launch': ('首次通过 Proton 加载 Mod：在 Steam → 游戏属性 → 启动选项中加入下面这行。\n已有启动选项时请合并；安装器不会自动更改。',
               'To load the mod under Proton: add this line in Steam → Properties → Launch Options.\nMerge with any existing options. This installer does not edit them.'),
    'copy': ('复制启动选项', 'Copy launch options'),
}


class Detector(QThread):
    message = Signal(str, str)
    result = Signal(object)
    error = Signal(str)

    def run(self):
        try:
            self.result.emit(core.discover(report=self.message.emit))
        except Exception:
            self.error.emit(traceback.format_exc())


class Worker(QThread):
    progress = Signal(int, str, str)
    result = Signal(bool, str, str)

    def __init__(self, game, exe=None, digest=None, restore=False):
        super().__init__()
        self.game, self.exe, self.digest, self.restore = game, exe, digest, restore

    def run(self):
        try:
            if self.restore:
                path = core.restore_latest(self.game)
                self.result.emit(True, '备份已恢复：' + str(path), 'Backup restored: ' + str(path))
            else:
                digest = self.digest
                if self.exe and not digest:
                    release = core.latest(self.progress.emit)
                    core.verify(self.exe, release)
                    digest = release['sha256']
                version = core.run_install(self.game, self.exe, digest, self.progress.emit)
                self.result.emit(True, '安装完成：' + version, 'Installed: ' + version)
        except Exception as exc:
            detail = traceback.format_exc()
            self.progress.emit(-1, detail, detail)
            if isinstance(exc, core.InstallError):
                self.result.emit(False, exc.zh, exc.en)
            else:
                self.result.emit(False, '操作失败：' + str(exc), 'Operation failed: ' + str(exc))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'bazaarplusplus-deck/settings.ini'
        config.parent.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(config), QSettings.IniFormat)
        self.lang = int(self.settings.value('language', 0))
        self.worker = None
        self.logdir = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'bazaarplusplus-deck'
        self.logdir.mkdir(parents=True, exist_ok=True)
        self.resize(870, 650)
        self.setMinimumSize(640, 520)
        main = QWidget()
        self.setCentralWidget(main)
        layout = QVBoxLayout(main)
        layout.setContentsMargins(24, 20, 24, 20)
        top = QHBoxLayout()
        self.heading = QLabel()
        self.heading.setStyleSheet('font-size: 23px; font-weight: bold;')
        top.addWidget(self.heading, 1)
        self.language = QComboBox()
        self.language.addItems(['中文', 'English'])
        self.language.setCurrentIndex(self.lang)
        self.language.currentIndexChanged.connect(self.translate)
        top.addWidget(self.language)
        layout.addLayout(top)
        self.subtitle = QLabel()
        layout.addWidget(self.subtitle)
        self.directory = QLabel()
        layout.addWidget(self.directory)
        row = QHBoxLayout()
        self.path = QLineEdit(str(self.settings.value('game', '')))
        self.path.textChanged.connect(self.show_version)
        row.addWidget(self.path, 1)
        self.browse = QPushButton()
        self.browse.clicked.connect(self.choose_folder)
        row.addWidget(self.browse)
        self.detect = QPushButton()
        self.detect.clicked.connect(lambda: self.detect_game(True))
        row.addWidget(self.detect)
        layout.addLayout(row)
        self.version = QLabel()
        layout.addWidget(self.version)
        actions = QHBoxLayout()
        self.install = QPushButton()
        self.install.setStyleSheet('background: #205cbe; color: white; font-weight: bold; padding: 10px;')
        self.install.clicked.connect(lambda: self.start())
        self.local = QPushButton()
        self.local.clicked.connect(self.import_exe)
        self.restore = QPushButton()
        self.restore.clicked.connect(self.restore_backup)
        for b in [self.install, self.local, self.restore]:
            actions.addWidget(b)
        layout.addLayout(actions)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        layout.addWidget(self.bar)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2500)
        layout.addWidget(self.log, 1)
        self.launch = QLabel()
        self.launch.setWordWrap(True)
        layout.addWidget(self.launch)
        launchrow = QHBoxLayout()
        launchvalue = QLineEdit(core.LAUNCH_OPTIONS)
        launchvalue.setReadOnly(True)
        launchrow.addWidget(launchvalue, 1)
        self.copy = QPushButton()
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(core.LAUNCH_OPTIONS))
        launchrow.addWidget(self.copy)
        layout.addLayout(launchrow)
        self.logs = QPushButton()
        self.logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.logdir))))
        layout.addWidget(self.logs)
        self.controls = [self.install, self.local, self.restore, self.browse, self.detect, self.path]
        self.translate(self.lang)
        self.status.setText(self.t('ready'))
        if not self.path.text():
            QTimer.singleShot(0, lambda: self.detect_game(False))

    def t(self, key):
        return TEXT[key][self.lang]

    def translate(self, index):
        self.lang = index
        self.settings.setValue('language', index)
        self.setWindowTitle(self.t('title'))
        self.heading.setText(self.t('title'))
        for key in ['subtitle', 'directory', 'browse', 'detect', 'install', 'local', 'restore', 'launch', 'copy', 'logs']:
            getattr(self, key).setText(self.t(key))
        self.show_version()

    def show_version(self):
        p = Path(self.path.text()) / 'BepInEx/plugins/BazaarPlusPlus.version'
        try:
            text = p.read_text().strip()[:80]
        except OSError:
            text = self.t('unknown')
        self.version.setText(self.t('installed') + text)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, self.t('directory'), self.path.text() or str(Path.home()))
        if path:
            self.path.setText(path)

    def detect_game(self, manual=True):
        if self.worker and self.worker.isRunning():
            return
        for c in self.controls:
            c.setEnabled(False)
        self.status.setText(self.t('scanning'))
        self.bar.setRange(0, 0)
        self.worker = Detector()
        self.worker.message.connect(lambda zh, en: self.progress(-1, zh, en))
        self.worker.result.connect(lambda games: self.detected(games, manual))
        self.worker.error.connect(self.detect_failed)
        self.worker.finished.connect(self.thread_finished)
        self.worker.start()

    def detect_failed(self, detail):
        self.bar.setRange(0, 100)
        self.progress(0, '检测失败，请查看日志', 'Detection failed; see the log')
        self.progress(-1, detail, detail)
        QMessageBox.warning(self, self.t('failed'), self.t('notfound'))

    def detected(self, games, manual):
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if games else 0)
        if len(games) == 1:
            self.path.setText(str(games[0]))
            self.progress(100, '已找到游戏：' + str(games[0]), 'Game found: ' + str(games[0]))
        elif games:
            choice, ok = QInputDialog.getItem(self, self.t('directory'), self.t('multiple'), list(map(str, games)), 0, False)
            if ok:
                self.path.setText(choice)
        else:
            self.status.setText(self.t('none'))
            if manual:
                QMessageBox.information(self, self.t('detect'), self.t('notfound'))

    def import_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, self.t('local'), str(Path.home() / 'Downloads'), 'Windows installer (*.exe)')
        if not path:
            return
        digest, ok = QInputDialog.getText(self, 'SHA256', self.t('hash'))
        if ok:
            digest = digest.strip().lower()
            if digest and not re.fullmatch('[0-9a-f]{64}', digest):
                QMessageBox.warning(self, 'SHA256', self.t('hashbad'))
                return
            self.start(path, digest or None)

    def restore_backup(self):
        if QMessageBox.question(self, self.t('restore'), self.t('restoreask')) == QMessageBox.Yes:
            self.start(restore=True)

    def start(self, exe=None, digest=None, restore=False):
        try:
            game = core.validate_game(self.path.text())
        except Exception as exc:
            QMessageBox.warning(self, self.t('failed'), exc.zh if self.lang == 0 and isinstance(exc, core.InstallError) else str(exc))
            return
        self.settings.setValue('game', str(game))
        for c in self.controls:
            c.setEnabled(False)
        self.bar.setRange(0, 0)
        self.worker = Worker(game, exe, digest, restore)
        self.worker.progress.connect(self.progress)
        self.worker.result.connect(self.finished)
        self.worker.finished.connect(self.thread_finished)
        self.worker.start()

    def progress(self, value, zh, en):
        message = zh if self.lang == 0 else en
        if value >= 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(value)
            self.status.setText(message)
        self.log.appendPlainText(message)
        with (self.logdir / 'installer.log').open('a', encoding='utf-8') as f:
            f.write(message + '\n')

    def finished(self, ok, zh, en):
        self.bar.setRange(0, 100)
        self.progress(100 if ok else 0, zh, en)
        self.show_version()
        (QMessageBox.information if ok else QMessageBox.critical)(self, self.t('done') if ok else self.t('failed'), zh if self.lang == 0 else en)

    def thread_finished(self):
        for c in self.controls:
            c.setEnabled(True)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, self.t('title'), self.t('close'))
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    window.show()
    if '--smoke-test' in sys.argv:
        QTimer.singleShot(300, app.quit)
    if '--screenshot' in sys.argv:
        output = sys.argv[sys.argv.index('--screenshot') + 1]
        QTimer.singleShot(400, lambda: window.grab().save(output))
        QTimer.singleShot(700, app.quit)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
