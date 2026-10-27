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


class Checker(QThread):
    result = Signal(str, object)
    error = Signal(str, str)
    message = Signal(int, str, str)

    def __init__(self, kind, version='', build=0):
        super().__init__()
        self.kind, self.version, self.build = kind, version, build

    def run(self):
        try:
            result = (core.latest(self.message.emit) if self.kind == 'mod' else
                      core.latest_installer(self.version, self.build))
            self.result.emit(self.kind, result)
        except Exception:
            self.error.emit(self.kind, traceback.format_exc())


