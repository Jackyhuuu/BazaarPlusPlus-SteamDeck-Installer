# BazaarPlusPlus Steam Deck Installer

独立社区项目，为 Steam Deck / Linux x86_64 提供原生 Qt 图形安装窗口，将**官方 Windows 版 Mod** 安装到通过 Proton 运行的《The Bazaar》。支持中文 / English，不打开浏览器界面。

1.0.0 是第一个正式版。保留中英文简洁界面、明确的 Mod 版本与更新按钮、安装器更新检查，以及内置 CA 根证书修复。新增主页面「1280×800 启动优化」入口：打开后复制完整配置，在 Steam 游戏属性中粘贴一次；此后每次启动请求 1280×800 无边框全屏。可取消勾选恢复普通 Mod 加载参数。该预设并非已证实的 800×600 根因修复，仍需设备验证；安装器不会直接写入 Steam 配置、游戏画面配置或系统显示设置。

## 下载与使用

发布下载：[Releases](https://github.com/Jackyhuuu/BazaarPlusPlus-SteamDeck-Installer/releases)。开发构建：[AppImage Actions](https://github.com/Jackyhuuu/BazaarPlusPlus-SteamDeck-Installer/actions/workflows/appimage.yml)，成功运行的 Artifacts 中包含 AppImage 和 SHA256SUMS；GitHub 下载 Actions 产物需要登录。带 v 标签的成功构建会发布对应正式版；main 构建首次发布 v1.0.0，之后不会覆盖已发布的同名版本。可直接下载单个 AppImage。

1. Steam Deck 进入桌面模式，下载 `BazaarPlusPlus-SteamDeck-x86_64.AppImage`。
2. 文件属性 → 权限 → 允许作为程序执行，然后双击打开。
3. 关闭游戏，确认自动检测的目录，点击「一键安装 / 更新」。也可导入官方 Windows EXE。
4. 点击「1280×800 启动优化」，复制程序生成的完整启动配置，粘贴到 Steam 游戏属性的启动选项中一次。已有自定义选项时需合并。若想保留原分辨率行为，取消「以 1280×800 无边框全屏启动游戏」勾选，再复制普通 Mod 参数。

**不直接修改桌面显示设置、Steam 配置、Proton 配置或存档。** 分辨率预设只有粘贴到 Steam 启动选项后才生效。用户已在 Steam Deck 上确认前版可正常下载、重新安装和进入游戏；新加入的分辨率预设效果仍待实测。此项目使用 Windows Mod，Windows 专有功能（例如 Media Foundation 回放录制）在 Proton 下的可用性仍需实测。

## 功能与边界

- 自动查找 Steam、Flatpak Steam、libraryfolders.vdf 中的外置库及常见 SD 卡目录；支持手选目录。
- 官方平台 manifest → 公共 manifest → 旧域名 manifest，强制验证 Windows EXE 的 SHA256 和文件大小。不允许任意域名或 HTTP 重定向。
- 当前线上 5.7.0 使用旧域名；新 CDN manifest 在 2026-10-27 检查时返回 404，会自动回退。
- 内置 7zz，仅取出 `BepInExSource/BepInEx.zip`，不执行 EXE。ZIP 路径、符号链接、重复文件及总大小检查，安装前验证完整 payload。
- 本地 EXE：留空 SHA256 时联网与官方当前版本核对；旧版/离线需填入可信来源的 SHA256。自行提供的校验值不代表官方认证。
- 覆盖前备份，逐文件原子替换，失败回滚，中断事务在下次安装前恢复；可在窗口中恢复最近备份。
- 更新只删除本安装器此前记录、且新版未提供的文件。保留用户配置、其他 Mod 和数据目录。未知新 payload 布局会拒绝安装，需要更新允许清单。
- 备份位于游戏目录 `.bazaarplusplus-deck/backups/`，不自动删除；日志位于 `~/.local/state/bazaarplusplus-deck/installer.log`（遵循 XDG_STATE_HOME）。
- 检测到 Linux 游戏进程会停止安装。请在每次安装/恢复前退出游戏。

## 开发与构建

Linux x86_64（推荐 Ubuntu 22.04）安装 Python 3.11 和工作流列出的系统依赖后，执行 `bash scripts/build-appimage.sh`。构建内含 Python、Qt、7zz，无需 Steam Deck 额外安装这些依赖。该命令在 macOS/ARM 上会明确失败，绝不生成改扩展名的文件。

GitHub Actions 自动运行单元测试、真实官方 5.7.0 EXE 安装/更新/恢复集成测试、Qt 无屏启动、PyInstaller 打包、AppDir 启动、ELF/AppImage 架构检查和最终 AppImage 启动检查。AppDir 与最终 AppImage 还会通过 Xvfb 的 X11 显示服务器进行图形启动测试。任何失败均阻止发布。产物位于 `dist/BazaarPlusPlus-SteamDeck-x86_64.AppImage`。

本地开发：`python3 -m venv .venv`，安装 requirements.txt 后运行 `python launcher.py`。源码测试：`python -m unittest discover -s tests -v`。真实官方 EXE 集成测试由 BPP_TEST_EXE、BPP_TEST_SHA256、BPP_7ZZ 环境变量启用，测试仅写入临时模拟游戏目录。

## 验证记录

2026-10-27：通过真实官方 `BazaarPlusPlus_5.7.0_x64-setup.exe` 集成测试，SHA256 为 `91c2386aea38118d1f9a12ef0b7ff95ad9ff816878e742319d23fa81b2f1f25c`；提取并验证 37 个 payload 文件。23 项测试涵盖安装、更新、恢复、失败回滚、断电恢复、游戏库检测、证书、更新状态和分辨率配置生成。用户已确认前版在 Steam Deck 上可下载、重装和进入游戏；新增 1280×800 预设仍待实机确认。

MIT License。上游及打包依赖说明见 THIRD-PARTY.md。

## English

Native Chinese/English Qt GUI for installing the official Windows BazaarPlusPlus mod into The Bazaar under Proton. Download the AppImage from Releases, enable execution, open it in Desktop Mode and select Install / Update. Python, Qt and 7zz are bundled. Official manifest size and SHA256 verification are mandatory. Local EXEs require either the current official hash online or a trusted hash entered by the user. Backups, rollback, progress, logs and Steam library discovery are included. Display settings, save data, Steam options and Proton settings are not edited. Steam Deck game compatibility needs hardware validation; passing CI is not a claim that every mod feature works under Proton.

The 1.0.0 stable release adds an optional 1280×800 borderless launch preset. Open the resolution entry, copy the generated line and paste it into Steam Launch Options once, merging any custom options. This prepares Unity launch arguments and is not a verified diagnosis of the 800×600 reset. System display settings and Steam configuration files are never edited automatically.
