"""Compact native desktop UI. Installation logic lives in core; tasks stay off the UI thread."""
from pathlib import Path
import json
import os
import re
import sys

from PySide6.QtCore import QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QProgressBar,
    QPlainTextEdit, QFileDialog, QMessageBox, QInputDialog, QFrame, QScrollArea)
from deck_installer import core, __version__
from deck_installer.tasks import TEXT, Detector, Worker, Checker

TEXT.update({
    'title': ('巴扎加加', 'BazaarPlusPlus'),
    'subtitle': ('Steam Deck 安装与更新', 'Install and update on Steam Deck'),
    'directory': ('游戏位置', 'Game location'),
    'browse': ('选择目录', 'Browse'),
    'detect': ('自动查找', 'Find game'),
    'current_label': ('已安装版本', 'Installed version'),
    'latest_label': ('官方最新版本', 'Latest official version'),
    'unknown': ('尚未安装', 'Not installed'),
    'checking': ('正在检查…', 'Checking…'),
    'unchecked': ('待检查', 'Not checked'),
    'checkfailed': ('暂时无法获取', 'Unavailable'),
    'check': ('检查更新', 'Check for updates'),
    'available': ('有新版本可更新', 'An update is available'),
    'uptodate': ('已是最新版本', 'You are up to date'),
    'newer': ('已安装版本高于官方清单', 'Installed version is newer than the release'),
    'getmod': ('安装巴扎加加', 'Install BazaarPlusPlus'),
    'more': ('更多选项', 'More options'),
    'details': ('查看日志', 'Show log'),
    'hide_details': ('收起日志', 'Hide log'),
    'local': ('本地 EXE 安装', 'Install local EXE'),
    'restore': ('恢复备份', 'Restore backup'),
    'launch_short': ('首次加载 Mod 时，复制以下启动选项到 Steam 游戏属性。',
                     'For the first launch, copy these options into the Steam game properties.'),
    'ready': ('选择游戏位置，然后安装或检查更新。', 'Choose your game location, then install or check for updates.'),
    'secure': ('官方来源 · SHA256 校验 · 自动备份', 'Official source · SHA256 verified · Automatic backup'),
    'installer_check': ('安装器更新', 'Installer update'),
    'installer_new': ('发现新版安装器：', 'New installer available: '),
    'installer_open': ('打开下载页面，获取新版 AppImage？', 'Open the download page for the new AppImage?'),
    'installer_current': ('当前已是最新可用的安装器。', 'You have the latest available installer.'),
    'network_error': ('无法连接官方服务。请重试，或使用本地 EXE 安装。',
                      'Cannot connect to the official service. Retry or install a local EXE.'),
    'operation_error': ('操作未完成，已展开详细日志。', 'The operation did not finish. See the expanded log.'),
    'downgrade': ('当前安装版本高于官方清单。继续会安装较旧版本，是否继续？',
                  'Your installed version is newer than the official release. Continue with a downgrade?'),
    'copy': ('复制', 'Copy'),
})

STYLE = '''
QWidget { background: #0d1422; color: #eaf0fb; font-size: 13px; }
QScrollArea, QScrollArea > QWidget > QWidget { border: none; }
QFrame#card { background: #162135; border: 1px solid #25334b; border-radius: 15px; }
QFrame#card QLabel, QFrame#card QWidget { background: transparent; }
QLabel#title { font-size: 27px; font-weight: 700; color: #f4f7ff; }
QLabel#muted { color: #97a9c4; }
QLabel#number { font-size: 27px; font-weight: 600; color: #f4f7ff; }
QLabel#accent { color: #70dec6; }
QLabel#badge { background: #1e3440; color: #8ce8d4; border-radius: 7px; padding: 5px 10px; font-size: 11px; }
QPushButton { background: #21304a; border: 1px solid #30425e; border-radius: 9px; padding: 9px 14px; min-height: 21px; color: #dfe8f8; }
QPushButton:hover { background: #2b3f5d; border-color: #57718f; }
QPushButton:pressed { background: #16243b; }
QPushButton:disabled { color: #64738a; background: #172237; border-color: #25334b; }
QPushButton#primary { background: #72dfc7; color: #102a2b; border: none; font-size: 15px; font-weight: 700; padding: 13px 20px; }
QPushButton#primary:hover { background: #96ead8; }
QPushButton#primary:disabled { background: #314e52; color: #83a8aa; }
QPushButton#quiet { background: transparent; border: none; color: #a4b7d3; padding: 5px 7px; }
QPushButton#quiet:hover { color: #80e3cd; background: #162135; }
QLineEdit, QPlainTextEdit { background: #101a2c; border: 1px solid #30415c; border-radius: 8px; padding: 10px; color: #e7eef9; selection-background-color: #347d77; }
QLineEdit:focus { border-color: #72dfc7; }
QComboBox { background: #162135; border: 1px solid #30415c; border-radius: 8px; padding: 7px 12px; min-width: 78px; }
QComboBox QAbstractItemView { background: #162135; selection-background-color: #2b3f5d; }
QProgressBar { border: none; background: #233149; border-radius: 3px; min-height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #72dfc7; border-radius: 3px; }
QScrollBar:vertical { background: #111b2c; width: 8px; }
QScrollBar::handle:vertical { background: #344860; border-radius: 4px; min-height: 24px; }
QToolTip { background: #21304a; color: #eaf0fb; border: 1px solid #405473; padding: 6px; }
'''


def label(name=None, wrap=False):
    item = QLabel()
    if name:
        item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(callback, name=None):
    item = QPushButton()
    if name:
        item.setObjectName(name)
    item.clicked.connect(callback)
    return item


class Window(QMainWindow):
    def __init__(self, startup=True):
        super().__init__()
        config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'bazaarplusplus-deck/settings.ini'
        config.parent.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(config), QSettings.IniFormat)
        self.lang = int(self.settings.value('language', 0))
        self.worker = None
        self.release = None
        self.installed_version = ''
        self.release_state = 'unchecked'
        self.pending_check = startup
        self.build_number = 0
        try:
            self.build_number = json.loads(Path(__file__).with_name('build-info.json').read_text())['build']
        except (OSError, ValueError, KeyError):
            pass
        self.logdir = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'bazaarplusplus-deck'
        self.logdir.mkdir(parents=True, exist_ok=True)
        self.resize(900, 660)
        self.setMinimumSize(730, 560)
        self.setStyleSheet(STYLE)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(15)

        header = QHBoxLayout()
        branding = QVBoxLayout()
        self.heading = label('title')
        self.subtitle = label('muted', True)
        branding.addWidget(self.heading)
        branding.addWidget(self.subtitle)
        header.addLayout(branding, 1)
        badge = QLabel('STEAM DECK')
        badge.setObjectName('badge')
        badge.setFixedHeight(28)
        header.addWidget(badge)
        self.language = QComboBox()
        self.language.addItems(['中文', 'English'])
        self.language.setCurrentIndex(self.lang)
        self.language.currentIndexChanged.connect(self.translate)
        header.addWidget(self.language)
        layout.addLayout(header)

        card, content = self.card()
        versionrow = QHBoxLayout()
        left = QVBoxLayout()
        self.current_label = label('muted')
        self.current_number = label('number')
        left.addWidget(self.current_label)
        left.addWidget(self.current_number)
        right = QVBoxLayout()
        self.latest_label = label('muted')
        self.latest_number = label('number')
        right.addWidget(self.latest_label)
        right.addWidget(self.latest_number)
        versionrow.addLayout(left, 1)
        versionrow.addLayout(right, 1)
        content.addLayout(versionrow)
        self.version = label('accent', True)
        content.addWidget(self.version)
        layout.addWidget(card)

        card, content = self.card()
        locationrow = QHBoxLayout()
        self.directory = label('muted')
        locationrow.addWidget(self.directory, 1)
        self.detect = button(lambda: self.detect_game(True), 'quiet')
        locationrow.addWidget(self.detect)
        content.addLayout(locationrow)
        row = QHBoxLayout()
        self.path = QLineEdit(str(self.settings.value('game', '')))
        self.path.textChanged.connect(self.show_version)
        row.addWidget(self.path, 1)
        self.browse = button(self.choose_folder)
        row.addWidget(self.browse)
        content.addLayout(row)
        layout.addWidget(card)

        actions = QHBoxLayout()
        self.install = button(lambda: self.start(), 'primary')
        self.check = button(self.check_versions)
        actions.addWidget(self.install, 1)
        actions.addWidget(self.check)
        layout.addLayout(actions)
        self.secure = label('muted')
        layout.addWidget(self.secure)
        self.status = label('muted', True)
        self.status.setMinimumHeight(32)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        layout.addWidget(self.bar)

        extras = QHBoxLayout()
        self.more = button(self.toggle_more, 'quiet')
        self.details = button(self.toggle_log, 'quiet')
        extras.addWidget(self.more)
        extras.addWidget(self.details)
        extras.addStretch()
        layout.addLayout(extras)
        self.advanced, advanced = self.card()
        localrow = QHBoxLayout()
        self.local = button(self.import_exe)
        self.restore = button(self.restore_backup)
        localrow.addWidget(self.local)
        localrow.addWidget(self.restore)
        advanced.addLayout(localrow)
        self.launch = label('muted', True)
        advanced.addWidget(self.launch)
        launchrow = QHBoxLayout()
        value = QLineEdit(core.LAUNCH_OPTIONS)
        value.setReadOnly(True)
        launchrow.addWidget(value, 1)
        self.copy = button(lambda: QApplication.clipboard().setText(core.LAUNCH_OPTIONS))
        launchrow.addWidget(self.copy)
        advanced.addLayout(launchrow)
        self.advanced.hide()
        layout.addWidget(self.advanced)
        self.logbox = QWidget()
        logs = QVBoxLayout(self.logbox)
        logs.setContentsMargins(0, 0, 0, 0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2500)
        self.log.setFixedHeight(145)
        logs.addWidget(self.log)
        self.logs = button(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.logdir))), 'quiet')
        logs.addWidget(self.logs)
        self.logbox.hide()
        layout.addWidget(self.logbox)
        layout.addStretch(1)
        footer = QHBoxLayout()
        self.appversion = label('muted')
        suffix = f' · build {self.build_number}' if self.build_number else ''
        self.appversion.setText('INSTALLER  ' + __version__ + suffix)
        footer.addWidget(self.appversion, 1)
        self.installer_check = button(self.check_installer, 'quiet')
        footer.addWidget(self.installer_check)
        layout.addLayout(footer)
        self.controls = [self.install, self.local, self.restore, self.browse, self.detect, self.path, self.check, self.installer_check]
        self.translate(self.lang)
        self.status.setText(self.t('ready'))
        if startup:
            QTimer.singleShot(0, self.startup)

    def card(self):
        card = QFrame()
        card.setObjectName('card')
        content = QVBoxLayout(card)
        content.setContentsMargins(19, 16, 19, 16)
        content.setSpacing(9)
        return card, content

    def t(self, key):
        return TEXT[key][self.lang]

    def translate(self, index):
        self.lang = index
        self.settings.setValue('language', index)
        self.setWindowTitle(self.t('title') + ' · Steam Deck')
        for key in ['subtitle', 'directory', 'browse', 'detect', 'local', 'restore', 'copy', 'logs', 'current_label', 'latest_label', 'check', 'secure', 'installer_check']:
            getattr(self, key).setText(self.t(key))
        self.heading.setText(self.t('title'))
        self.more.setText(('▾ ' if self.advanced.isVisible() else '▸ ') + self.t('more'))
        self.details.setText(self.t('hide_details' if self.logbox.isVisible() else 'details'))
        self.launch.setText(self.t('launch_short'))
        self.show_version()

    def show_version(self):
        try:
            self.installed_version = (Path(self.path.text()) / 'BepInEx/plugins/BazaarPlusPlus.version').read_text().strip()[:80]
        except (OSError, UnicodeError):
            self.installed_version = ''
        self.current_number.setText(self.installed_version.removesuffix('.prod') if self.installed_version else self.t('unknown'))
        self.latest_number.setText(self.release['version'] if self.release else self.t(self.release_state))
        current = core.version_key(self.installed_version)
        latest = core.version_key(self.release['version']) if self.release else None
        if latest:
            state = 'getmod' if not current else 'available' if current < latest else 'uptodate' if current == latest else 'newer'
            self.version.setText(self.t(state))
            if not current:
                action = self.t('getmod')
            elif current < latest:
                action = ('更新至 ' if self.lang == 0 else 'Update to ') + self.release['version']
            else:
                action = ('重新安装 ' if self.lang == 0 else 'Reinstall ') + self.release['version']
        else:
            self.version.setText(self.t('secure') if self.release_state != 'checkfailed' else self.t('network_error'))
            action = self.t('install')
        self.install.setText(action)

    def startup(self):
        if not self.path.text():
            self.detect_game(False)
        else:
            self.pending_check = False
            self.check_versions()

    def busy(self):
        return self.worker and self.worker.isRunning()

    def begin(self, worker, status):
        if self.busy():
            return False
        self.worker = worker
        for control in self.controls:
            control.setEnabled(False)
        self.status.setText(status)
        self.bar.show()
        self.bar.setRange(0, 0)
        worker.finished.connect(self.thread_finished)
        return True

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, self.t('directory'), self.path.text() or str(Path.home()))
        if path:
            self.path.setText(path)
            self.settings.setValue('game', path)

    def check_versions(self):
        if self.busy():
            return
        self.release_state = 'checking'
        self.show_version()
        worker = Checker('mod')
        self.begin(worker, self.t('checking'))
        worker.message.connect(lambda n, zh, en: self.progress(-1, zh, en))
        worker.result.connect(self.checked)
        worker.error.connect(self.check_failed)
        worker.start()

    def check_installer(self):
        if self.busy():
            return
        worker = Checker('installer', __version__, self.build_number)
        self.begin(worker, self.t('checking'))
        worker.result.connect(self.checked)
        worker.error.connect(self.check_failed)
        worker.start()

    def checked(self, kind, data):
        self.bar.hide()
        if kind == 'mod':
            self.release = data
            self.release_state = 'unchecked'
            self.show_version()
            self.status.setText(self.version.text())
            self.progress(-1, '官方最新版本：' + data['version'], 'Latest official version: ' + data['version'])
        elif data['newer']:
            self.status.setText(self.t('installer_new') + data['tag'])
            if QMessageBox.question(self, self.t('installer_check'), self.t('installer_new') + data['tag'] + '\n\n' + self.t('installer_open')) == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(data['url']))
        else:
            self.status.setText(self.t('installer_current'))
            QMessageBox.information(self, self.t('installer_check'), self.t('installer_current'))

    def check_failed(self, kind, detail):
        self.bar.hide()
        self.progress(-1, detail, detail)
        if kind == 'mod':
            self.release = None
            self.release_state = 'checkfailed'
            self.show_version()
        self.status.setText(self.t('network_error'))
        self.details.setToolTip(detail)

    def detect_game(self, manual=True):
        if self.busy():
            return
        worker = Detector()
        self.begin(worker, self.t('scanning'))
        worker.message.connect(lambda zh, en: self.progress(-1, zh, en))
        worker.result.connect(lambda games: self.detected(games, manual))
        worker.error.connect(self.detect_failed)
        worker.start()

    def detect_failed(self, detail):
        self.bar.hide()
        self.progress(-1, detail, detail)
        self.status.setText(self.t('none'))
        self.show_log()
        QMessageBox.warning(self, self.t('failed'), self.t('notfound'))

    def detected(self, games, manual):
        self.bar.hide()
        if len(games) == 1:
            self.path.setText(str(games[0]))
            self.settings.setValue('game', str(games[0]))
            self.progress(-1, '找到游戏：' + str(games[0]), 'Game found: ' + str(games[0]))
            self.status.setText('游戏位置已就绪' if self.lang == 0 else 'Game location is ready')
        elif games:
            choice, ok = QInputDialog.getItem(self, self.t('directory'), self.t('multiple'), list(map(str, games)), 0, False)
            if ok:
                self.path.setText(choice)
                self.settings.setValue('game', choice)
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
        if self.busy():
            return
        try:
            game = core.validate_game(self.path.text())
        except Exception as exc:
            QMessageBox.warning(self, self.t('failed'), exc.zh if self.lang == 0 and isinstance(exc, core.InstallError) else str(exc))
            return
        if not exe and not restore and self.release and core.version_key(self.installed_version):
            if core.version_key(self.installed_version) > core.version_key(self.release['version']):
                if QMessageBox.question(self, self.t('check'), self.t('downgrade')) != QMessageBox.Yes:
                    return
        self.settings.setValue('game', str(game))
        worker = Worker(game, exe, digest, restore)
        self.begin(worker, self.t('checking') if not restore else self.t('restore'))
        worker.progress.connect(self.progress)
        worker.result.connect(self.finished)
        worker.start()

    def progress(self, value, zh, en):
        message = zh if self.lang == 0 else en
        if value >= 0:
            self.bar.show()
            self.bar.setRange(0, 100)
            self.bar.setValue(value)
            # Keep paths and tracebacks in the detail panel, not in the main layout.
            self.status.setText(message.splitlines()[0][:140])
        self.log.appendPlainText(message)
        with (self.logdir / 'installer.log').open('a', encoding='utf-8') as f:
            f.write(message + '\n')

    def finished(self, ok, zh, en):
        self.bar.setRange(0, 100)
        self.bar.setValue(100 if ok else 0)
        self.progress(-1, zh, en)
        self.show_version()
        if ok:
            self.status.setText((zh if self.lang == 0 else en).splitlines()[0][:100])
            QMessageBox.information(self, self.t('done'), self.status.text())
        else:
            self.status.setText(self.t('operation_error'))
            self.show_log()
            box = QMessageBox(QMessageBox.Critical, self.t('failed'), self.t('operation_error'), parent=self)
            box.setDetailedText(zh if self.lang == 0 else en)
            box.exec()

    def thread_finished(self):
        for control in self.controls:
            control.setEnabled(True)
        if self.pending_check:
            self.pending_check = False
            QTimer.singleShot(0, self.check_versions)

    def toggle_more(self):
        self.advanced.setVisible(not self.advanced.isVisible())
        self.more.setText(('▾ ' if self.advanced.isVisible() else '▸ ') + self.t('more'))

    def show_log(self):
        self.logbox.show()
        self.details.setText(self.t('hide_details'))

    def toggle_log(self):
        self.logbox.setVisible(not self.logbox.isVisible())
        self.details.setText(self.t('hide_details' if self.logbox.isVisible() else 'details'))

    def closeEvent(self, event):
        if self.busy():
            QMessageBox.information(self, self.t('title'), self.t('close'))
            event.ignore()
        else:
            event.accept()


def main():
    if '--network-test' in sys.argv:
        import tempfile
        release = core.latest()
        with tempfile.TemporaryDirectory() as tmp:
            core.download(release, Path(tmp) / 'official.exe', lambda *args: None)
        print('Bundled CA: official manifest, EXE download and SHA256 verified:', release['version'])
        return 0
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont('Noto Sans', 10))
    automatic = not any(arg in sys.argv for arg in ['--smoke-test', '--screenshot'])
    window = Window(startup=automatic)
    window.show()
    if '--smoke-test' in sys.argv:
        QTimer.singleShot(300, app.quit)
    if '--screenshot' in sys.argv:
        output = sys.argv[sys.argv.index('--screenshot') + 1]
        if '--demo' in sys.argv:
            window.release = {'version': '5.7.0'}
            window.show_version()
        QTimer.singleShot(400, lambda: window.grab().save(output))
        QTimer.singleShot(700, app.quit)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
