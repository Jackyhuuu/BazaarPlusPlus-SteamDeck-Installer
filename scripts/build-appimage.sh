#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  echo 'AppImage build requires Linux x86_64. Use the GitHub Actions AppImage workflow.' >&2
  exit 2
fi
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
mkdir -p vendor build/tools dist
fetch() {
  local url="$1" output="$2" digest="$3"
  curl --fail --location --retry 3 --connect-timeout 20 --max-time 300 "$url" -o "$output"
  echo "$digest  $output" | sha256sum --check --status
}
fetch https://www.7-zip.org/a/7z2600-linux-x64.tar.xz build/tools/7zip.tar.xz c74dc4a48492cde43f5fec10d53fb2a66f520e4a62a69d630c44cb22c477edc6
tar -xf build/tools/7zip.tar.xz -C vendor
fetch https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage build/tools/appimagetool 95cbe7cce9717fce90c484e34052ee7c7f1d7635b33c12525b4776826a7d29b6
fetch https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 build/tools/runtime 617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46
chmod +x vendor/7zz build/tools/appimagetool build/tools/runtime
fetch https://bppinstaller.bazaarplusplus.com/5.7.0/windows-x86_64/installer/BazaarPlusPlus_5.7.0_x64-setup.exe build/test-official.exe 91c2386aea38118d1f9a12ef0b7ff95ad9ff816878e742319d23fa81b2f1f25c
BPP_7ZZ="$PWD/vendor/7zz" BPP_TEST_EXE="$PWD/build/test-official.exe" \
  BPP_TEST_SHA256=91c2386aea38118d1f9a12ef0b7ff95ad9ff816878e742319d23fa81b2f1f25c \
  .venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python launcher.py --smoke-test
.venv/bin/pyinstaller --noconfirm --clean --onedir --windowed --name bpp-deck \
  --add-data 'deck_installer/payload-inventory.json:deck_installer' \
  --add-binary 'vendor/7zz:vendor' launcher.py
mkdir -p AppDir/usr/bin AppDir/usr/share/licenses
cp -a dist/bpp-deck/. AppDir/usr/bin/
cp assets/bpp-deck.desktop AppDir/
cp assets/bpp-deck.svg AppDir/
cp LICENSE UPSTREAM-LICENSE THIRD-PARTY.md AppDir/usr/share/licenses/
cp assets/licenses/*.txt AppDir/usr/share/licenses/
cp -a vendor/License.txt vendor/readme.txt AppDir/usr/share/licenses/ 2>/dev/null || true
cp assets/AppRun AppDir/AppRun
chmod +x AppDir/AppRun
QT_QPA_PLATFORM=offscreen AppDir/AppRun --smoke-test
QT_QPA_PLATFORM=xcb xvfb-run -a AppDir/AppRun --smoke-test
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 build/tools/appimagetool \
  --runtime-file build/tools/runtime AppDir dist/BazaarPlusPlus-SteamDeck-x86_64.AppImage
python3 scripts/verify-appimage.py dist/BazaarPlusPlus-SteamDeck-x86_64.AppImage
QT_QPA_PLATFORM=offscreen APPIMAGE_EXTRACT_AND_RUN=1 dist/BazaarPlusPlus-SteamDeck-x86_64.AppImage --smoke-test
QT_QPA_PLATFORM=xcb APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a dist/BazaarPlusPlus-SteamDeck-x86_64.AppImage --smoke-test
(cd dist && sha256sum BazaarPlusPlus-SteamDeck-x86_64.AppImage > SHA256SUMS)
