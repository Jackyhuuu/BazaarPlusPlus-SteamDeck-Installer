"""Install the official Windows mod payload for use under Steam Proton.

No Windows executable is executed. No display, Steam or Proton settings are edited.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit
import uuid
import zipfile
import certifi
import xml.etree.ElementTree as ET

MANIFESTS = (
    'https://cdn.bazaarplusplus.com/installer/latest/windows-x86_64.json',
    'https://cdn.bazaarplusplus.com/installer/latest.json',
    'https://bppinstaller.bazaarplusplus.com/latest.json',
)
HOSTS = {'cdn.bazaarplusplus.com', 'bppinstaller.bazaarplusplus.com'}
MAX_EXE = 512 * 1024 * 1024
MAX_PAYLOAD = 512 * 1024 * 1024
STATE = '.bazaarplusplus-deck'
RECEIPT = STATE + '/receipt.json'
LAUNCH_OPTIONS = 'WINEDLLOVERRIDES="winhttp=n,b" %command%'


class InstallError(Exception):
    def __init__(self, zh, en):
        super().__init__(en)
        self.zh, self.en = zh, en


def safe_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password
            or p.port not in (None, 443) or p.fragment or p.query):
        raise InstallError('官方清单包含不允许的下载地址', 'Unapproved release URL')
    return url


class ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_release(url, timeout=30):
    safe_url(url)
    return urllib.request.build_opener(ReleaseRedirect(),
        urllib.request.HTTPSHandler(context=tls_context())).open(
        urllib.request.Request(url, headers={'User-Agent': 'BPP-SteamDeck/0.2'}), timeout=timeout)


def tls_context():
    # The build machine's OpenSSL CA path does not exist on SteamOS. Always
    # carry Mozilla's root bundle; never disable certificate/hostname checks.
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        context.load_default_certs()
    except (OSError, ssl.SSLError):
        pass
    return context


def version_key(version):
    match = re.match(r'^v?(\d+)\.(\d+)\.(\d+)', version or '')
    return tuple(map(int, match.groups())) if match else None


def installer_release(data, current_version, current_build=0):
    releases = []
    for item in data:
        if item.get('draft'):
            continue
        tag = item.get('tag_name', '')
        match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)(?:-preview\.(\d+))?', tag)
        if not match:
            continue
        url = item.get('html_url', '')
        if url != 'https://github.com/Jackyhuuu/BazaarPlusPlus-SteamDeck-Installer/releases/tag/' + tag:
            continue
        parts = tuple(map(int, match.groups()[:3]))
        build = int(match.group(4)) if match.group(4) else 10**9
        releases.append((parts + (build,), tag, url))
    if not releases:
        raise ValueError('No published installer release')
    key, tag, url = max(releases)
    return {'tag': tag, 'url': url,
            'newer': key > (version_key(current_version) or (0, 0, 0)) + (current_build,)}


def latest_installer(current_version, current_build=0):
    # Atom is public and does not consume GitHub's small anonymous API quota.
    url = 'https://github.com/Jackyhuuu/BazaarPlusPlus-SteamDeck-Installer/releases.atom'
    req = urllib.request.Request(url, headers={'User-Agent': 'BPP-SteamDeck/0.2'})
    with urllib.request.build_opener(ReleaseRedirect(), urllib.request.HTTPSHandler(context=tls_context())).open(req, timeout=15) as r:
        raw = r.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Release response exceeds limit')
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    data = []
    for entry in ET.fromstring(raw).findall('a:entry', ns):
        link = entry.find('a:link', ns)
        if link is not None:
            address = link.get('href', '')
            data.append({'tag_name': address.rsplit('/', 1)[-1], 'html_url': address})
    return installer_release(data, current_version, current_build)


def parse_manifest(data):
    try:
        version = data['version']
        item = data['downloads']['windows-x86_64']
        if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-.][\w.-]+)?', version):
            raise ValueError('version')
        if not re.fullmatch(r'[a-fA-F0-9]{64}', item['sha256']):
            raise ValueError('sha256')
        if type(item['size']) is not int or not 0 < item['size'] <= MAX_EXE:
            raise ValueError('size')
        safe_url(item['url'])
        if not urlsplit(item['url']).path.lower().endswith('.exe'):
            raise ValueError('exe')
        return dict(version=version, url=item['url'], sha256=item['sha256'].lower(), size=item['size'])
    except (KeyError, TypeError, ValueError) as exc:
        raise InstallError('官方发布清单格式不支持或缺少 SHA256', 'Unsupported release manifest or missing SHA256') from exc


def latest(emit=lambda *args: None):
    failures = []
    for url in MANIFESTS:
        try:
            with open_release(url, timeout=8) as r:
                raw = r.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Manifest too large')
            return parse_manifest(json.loads(raw))
        except Exception as exc:
            failures.append(f'{url}: {exc}')
            emit(0, '清单地址不可用，尝试备用地址', 'Manifest unavailable; trying fallback')
    raise InstallError('无法获取官方清单，请检查网络。\n' + '\n'.join(failures),
                       'Cannot fetch official manifest.\n' + '\n'.join(failures))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(path, release):
    if Path(path).stat().st_size != release['size'] or sha256(path) != release['sha256']:
        raise InstallError('安装包大小或 SHA256 不匹配，已停止安装', 'Installer size or SHA256 mismatch; installation stopped')


def download(release, dest, emit):
    count = 0
    with open_release(release['url']) as response, Path(dest).open('wb') as out:
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            count += len(chunk)
            if count > release['size']:
                raise InstallError('下载大小超出官方清单', 'Download exceeds manifest size')
            out.write(chunk)
            emit(int(5 + 40 * count / release['size']), '下载官方安装包', 'Downloading official installer')
    verify(dest, release)


def discover(home=None, media=None, report=lambda zh, en: None):
    """Read Steam libraries/manifests, then probe bounded nested game locations.

    A broken/unmounted library must not abort detection of the remaining libraries.
    report is safe to connect to a worker-thread signal; never touches the GUI.
    """
    home = Path(home or Path.home())
    roots = [home / '.local/share/Steam', home / '.steam/steam', home / '.steam/root',
             home / '.steam/debian-installation',
             home / '.var/app/com.valvesoftware.Steam/.local/share/Steam']
    if home == Path.home():
        roots.append(Path(os.environ.get('XDG_DATA_HOME', home / '.local/share')) / 'Steam')

    def children(path):
        try:
            return sorted(path.iterdir())
        except OSError as exc:
            report('无法读取：' + str(path) + ' (' + str(exc) + ')',
                   'Cannot read: ' + str(path) + ' (' + str(exc) + ')')
            return []

    def text(path):
        try:
            return path.read_text(errors='replace')
        except OSError:
            return ''

    # Steam Deck SD cards can have a SteamLibrary subdirectory below the mount.
    mounts = [Path(media)] if media else [Path('/run/media'), Path('/media'), Path('/mnt')]
    for base in mounts:
        if not base.is_dir():
            continue
        queue = [(base, 0)]
        visited = 0
        while queue and visited < 2000:
            p, depth = queue.pop(0)
            visited += 1
            if (p / 'steamapps').is_dir():
                roots.append(p)
                continue
            if depth < 3:
                queue.extend((q, depth + 1) for q in children(p)
                             if q.is_dir() and not q.is_symlink() and not q.name.startswith('.'))

    seen = set()
    found = set()
    for root in roots:  # Follow newly found VDF library roots too.
        root = root.expanduser().resolve()
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        if len(seen) > 100:
            break
        report('扫描 Steam 库：' + str(root), 'Scanning Steam library: ' + str(root))
        for config in ['steamapps/libraryfolders.vdf', 'config/libraryfolders.vdf']:
            vdf = text(root / config)
            paths = re.findall(r'"path"\s*"([^"]+)"', vdf, re.IGNORECASE)
            # Older Steam versions use numeric key/string pairs instead of objects.
            paths += re.findall(r'"\d+"\s*"(/[^"\n]+)"', vdf)
            roots.extend(Path(p.replace('\\\\', '\\')) for p in paths)
        common = root / 'steamapps/common'
        candidates = []
        for manifest in (root / 'steamapps').glob('appmanifest_*.acf'):
            contents = text(manifest)
            if 'bazaar' not in contents.casefold():
                continue
            match = re.search(r'"installdir"\s*"([^"]+)"', contents, re.IGNORECASE)
            if match:
                installed = common / match.group(1)
                if installed.resolve().is_relative_to(common.resolve()):
                    candidates.append((installed, 3))
                    report('Steam 清单记录：' + str(installed), 'Steam manifest location: ' + str(installed))
        if common.is_dir():
            candidates.extend((p, 3 if 'bazaar' in p.name.casefold() else 0)
                              for p in children(common) if p.is_dir())
        probed = set()
        while candidates:
            p, depth = candidates.pop(0)
            if p in probed:
                continue
            probed.add(p)
            if (p / 'TheBazaar.exe').is_file() and (p / 'TheBazaar_Data').is_dir():
                found.add(p.resolve())
                report('找到游戏：' + str(p), 'Found game: ' + str(p))
            elif depth and p.is_dir():
                candidates.extend((q, depth - 1) for q in children(p)
                                  if q.is_dir() and not q.is_symlink())
    report('扫描完成，找到 ' + str(len(found)) + ' 个游戏目录',
           'Scan complete: ' + str(len(found)) + ' game folder(s) found')
    return sorted(found)


def validate_game(game):
    game = Path(game).expanduser().resolve()
    if not (game / 'TheBazaar.exe').is_file() or not (game / 'TheBazaar_Data').is_dir():
        raise InstallError('请选择包含 TheBazaar.exe 和 TheBazaar_Data 的游戏目录',
                           'Choose the game folder containing TheBazaar.exe and TheBazaar_Data')
    for proc in Path('/proc').glob('[0-9]*/comm'):
        try:
            if proc.read_text().strip().lower().startswith('thebazaar'):
                raise InstallError('请先关闭游戏再安装或恢复', 'Close The Bazaar before installing or restoring')
        except (OSError, UnicodeError):
            pass
    return game


def sevenzip():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    for p in [base / 'vendor/7zz', base / '7zz']:
        if p.is_file():
            return str(p)
    tool = os.environ.get('BPP_7ZZ') or shutil.which('7zz')
    if not tool:
        raise InstallError('缺少内置解包工具，安装器打包不完整', 'Bundled 7zz is missing; the application is incomplete')
    return tool


def extract_exe(exe, dest):
    """Ask 7zz for a single known stream; never extract arbitrary NSIS paths."""
    with Path(exe).open('rb') as f:
        if f.read(2) != b'MZ':
            raise InstallError('所选文件不是 Windows EXE', 'Selected file is not a Windows EXE')
    # Older Tauri releases use the same BepInExSource resource location.
    with Path(dest).open('wb') as out, tempfile.TemporaryFile() as err:
        p = subprocess.Popen([sevenzip(), 'x', '-so', str(Path(exe).resolve()),
                              'BepInExSource/BepInEx.zip'], stdout=out, stderr=err)
        try:
            p.wait(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            raise InstallError('解包超时', 'Extraction timed out')
        if p.returncode or not 0 < Path(dest).stat().st_size <= MAX_PAYLOAD:
            raise InstallError('EXE 内未找到有效的 BepInExSource/BepInEx.zip',
                               'No valid BepInExSource/BepInEx.zip found in EXE')


def relative(name):
    if '\\' in name or ':' in name or '\0' in name:
        raise ValueError('Unsafe path: ' + name)
    parts = name.split('/')
    if not name or any(p in ('', '.', '..') for p in parts):
        raise ValueError('Unsafe path: ' + name)
    return PurePosixPath(name)


def target(root, name):
    relative(name)
    p = root
    for part in name.split('/'):
        p = p / part
        if p.is_symlink():
            raise ValueError('Symbolic link target: ' + str(p))
    return p


def allowed(name):
    inventory = json.loads(Path(__file__).with_name('payload-inventory.json').read_text())
    names = {x['path'] for x in inventory['files'] if x['host'] == 'bepinex'
             and 'windows' in x.get('platforms', ['windows']) and x['producer'] != 'runtime'}
    return (name in names or
            (name.startswith('BepInEx/core/') and len(name.split('/')) == 3
             and name.endswith(('.dll', '.xml'))))


def stage_payload(archive, stage):
    names, seen = [], set()
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_PAYLOAD or len(z.infolist()) > 5000:
            raise ValueError('Payload exceeds size or file-count limit')
        for info in z.infolist():
            name = info.filename.rstrip('/')
            relative(name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Payload contains a symbolic link')
            if info.is_dir():
                continue
            if name.lower() in seen:
                raise ValueError('Duplicate payload path: ' + name)
            seen.add(name.lower())
            if not allowed(name):
                raise ValueError('Unsupported payload entry: ' + name)
            dest = target(stage, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, dest.open('wb') as out:
                shutil.copyfileobj(src, out)
            names.append(name)
    required = ['winhttp.dll', 'doorstop_config.ini', 'BepInEx/core/BepInEx.dll',
                'BepInEx/core/BepInEx.Preloader.dll', 'BepInEx/plugins/BazaarPlusPlus.dll',
                'BepInEx/plugins/BazaarPlusPlus.version']
    if not all(n in names for n in required):
        raise ValueError('Incomplete Windows mod payload')
    return names


def atomic_copy(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.bpp-', dir=dest.parent)
    try:
        with os.fdopen(fd, 'wb') as out, Path(src).open('rb') as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, dest)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(dest, data):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.bpp-json-', dir=dest.parent)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(name, dest)


@contextlib.contextmanager
def game_lock(game):
    directory = target(game, STATE)
    directory.mkdir(exist_ok=True)
    with target(game, STATE + '/lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InstallError('另一个安装任务正在运行', 'Another installation is running') from exc
        yield


def restore_snapshot(game, backup):
    journal = json.loads((backup / 'transaction.json').read_text())
    for name in journal['files']:
        if name != RECEIPT and not allowed(name):
            raise ValueError('Unsafe backup entry')
        dest = target(game, name)
        saved = target(backup / 'files', name)
        if saved.is_file():
            atomic_copy(saved, dest)
        elif name in journal['absent'] and dest.is_file():
            dest.unlink()
    journal['status'] = 'restored'
    write_json(backup / 'transaction.json', journal)


def recover_pending(game):
    root = target(game, STATE + '/backups')
    for p in sorted(root.glob('*/transaction.json')):
        if json.loads(p.read_text())['status'] == 'pending':
            restore_snapshot(game, p.parent)


def install_payload(game, stage, names, version, digest, emit=lambda *args: None):
    game = validate_game(game)
    with game_lock(game):
        recover_pending(game)
        receipt = target(game, RECEIPT)
        previous = json.loads(receipt.read_text()) if receipt.exists() else {'files': []}
        stale = set(previous['files']) - set(names)
        if any(not allowed(n) for n in stale):
            raise ValueError('Unsafe previous receipt')
        files = sorted(set(names) | stale | {RECEIPT})
        # Validate every destination before creating the backup or touching game files.
        for name in files:
            p = target(game, name)
            if p.exists() and not p.is_file():
                raise ValueError('Expected regular file: ' + name)
        required_bytes = sum((stage / n).stat().st_size for n in names)
        required_bytes += sum(target(game, n).stat().st_size for n in files if target(game, n).exists())
        if shutil.disk_usage(game).free < required_bytes + 32 * 1024 * 1024:
            raise InstallError('磁盘空间不足，无法安全备份和安装', 'Insufficient disk space for backup and installation')
        backup = target(game, STATE + '/backups/' + uuid.uuid4().hex)
        backup.mkdir(parents=True)
        absent = []
        for name in files:
            src = target(game, name)
            if src.exists():
                atomic_copy(src, target(backup / 'files', name))
            else:
                absent.append(name)
        journal = dict(status='pending', files=files, absent=absent, version=version)
        write_json(backup / 'transaction.json', journal)
        try:
            for i, name in enumerate(names):
                atomic_copy(stage / name, target(game, name))
                emit(65 + int(30 * (i + 1) / len(names)), '安装 ' + name, 'Installing ' + name)
            for name in stale:
                target(game, name).unlink(missing_ok=True)
            write_json(receipt, dict(version=version, sha256=digest, files=names))
            journal['status'] = 'complete'
            write_json(backup / 'transaction.json', journal)
        except BaseException:
            restore_snapshot(game, backup)
            raise
        return backup


def restore_latest(game):
    game = validate_game(game)
    with game_lock(game):
        root = target(game, STATE + '/backups')
        candidates = [p for p in root.glob('*/transaction.json')
                      if json.loads(p.read_text())['status'] in ('pending', 'complete')]
        if not candidates:
            raise InstallError('没有可恢复的备份', 'No backup available')
        backup = max(candidates, key=lambda p: p.stat().st_mtime).parent
        restore_snapshot(game, backup)
        return backup


def run_install(game, local_exe=None, expected_hash=None, emit=lambda *args: None):
    validate_game(game)
    with tempfile.TemporaryDirectory(prefix='bpp-deck-') as tmp:
        tmp = Path(tmp)
        if local_exe:
            exe = Path(local_exe)
            if not 0 < exe.stat().st_size <= MAX_EXE:
                raise ValueError('Invalid EXE size')
            digest = sha256(exe)
            if not expected_hash or digest != expected_hash.lower():
                raise InstallError('本地 EXE 的 SHA256 不匹配', 'Local EXE SHA256 mismatch')
            version = None
        else:
            release = latest(emit)
            version = release['version']
            exe = tmp / 'official.exe'
            download(release, exe, emit)
            digest = release['sha256']
        emit(50, 'SHA256 已验证，正在解包', 'SHA256 verified; extracting payload')
        archive = tmp / 'payload.zip'
        extract_exe(exe, archive)
        stage = tmp / 'stage'
        stage.mkdir()
        names = stage_payload(archive, stage)
        payload_version = (stage / 'BepInEx/plugins/BazaarPlusPlus.version').read_text().strip()
        if version and payload_version not in (version, version + '.prod'):
            raise ValueError('Payload version differs from release manifest')
        backup = install_payload(game, stage, names, payload_version, digest, emit)
        emit(100, '安装完成，备份：' + str(backup), 'Installed. Backup: ' + str(backup))
        return payload_version
