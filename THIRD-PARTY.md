# Third-party software

This is an independent community installer, not an official BazaarPlusPlus release.
No game or mod binaries are included in the source repository or installer.

- `deck_installer/payload-inventory.json` is from [BazaarPlusPlus](https://github.com/BazaarPlusPlus/BazaarPlusPlus/blob/master/release/payload.json), fetched 2026-10-27. MIT license in UPSTREAM-LICENSE. It defines the accepted Windows payload paths; unsupported future layouts fail without installing.
- AppImage bundles [7-Zip 26.00](https://www.7-zip.org/), including its License.txt and readme.txt. 7-Zip uses LGPL and BSD code, with the unRAR restriction described in its license. It only extracts the embedded ZIP; Windows programs are never executed. Source: https://www.7-zip.org/download.html
- AppImage bundles [PySide6 6.8.3 / Qt](https://doc.qt.io/qtforpython-6/licenses.html). Qt/PySide are distributed as dynamically linked libraries under their applicable LGPL/GPL/commercial terms. LGPLv3 and GPLv3 texts are included in usr/share/licenses; extracted AppImage libraries can be replaced for LGPL relinking. Source: https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/
- [PyInstaller](https://pyinstaller.org/) uses GPL with a bootloader exception allowing distribution of this MIT-licensed application.
- [AppImage appimagetool](https://github.com/AppImage/appimagetool) and [type2-runtime](https://github.com/AppImage/type2-runtime) are fetched from official releases. The build checks the fixed SHA256 values recorded in scripts/build-appimage.sh. Continuous release assets can move: a mismatch fails the build and requires an explicit checksum update after review.

For bundled package license details, extract the AppImage and inspect usr/bin/_internal and usr/share/licenses. For the official mod payload license and notices, refer to upstream. Downloaded mod files remain upstream's work.
