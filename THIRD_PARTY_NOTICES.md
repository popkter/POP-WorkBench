# Third-party notices

## PyAV / FFmpeg and Qt audio

视频预览 uses PyAV 16.1.0 to access FFmpeg for video decoding, frame previews,
and audio resampling. PySide6 QtMultimedia is used for the system audio sink;
the application does not use QMediaPlayer or an additional player engine.

- PyAV source: https://github.com/PyAV-Org/PyAV/tree/v16.1.0
- PyAV license: BSD-3-Clause; the package license metadata is bundled.
- FFmpeg source: https://ffmpeg.org/download.html
- PyAV binary build sources: https://github.com/PyAV-Org/pyav-ffmpeg
- FFmpeg and codec dependencies retain their own licenses. The Windows PyAV
  wheel used for development reports LGPL version 3 or later through
  `avcodec_license()`. Binary contents and build options are platform-specific.
- PySide6 source and license notices: https://doc.qt.io/qtforpython-6/licenses.html

The lockfile records the selected PyAV and PySide6 wheel versions. Distributors
must retain the applicable FFmpeg/codec source and license obligations for the
specific binary builds they distribute.

## libvterm 0.3.3

泡泡工具箱 embeds libvterm as the terminal emulation state machine used by
the native Qt Quick developer console.

- Source: https://www.leonerd.org.uk/code/libvterm/
- Vendored revision: 0.3.3
- License: MIT License
- Copyright: Paul Evans and libvterm contributors

The complete license is distributed in `native/third_party/libvterm/LICENSE`.

## Requests

泡泡工具箱 uses the Requests HTTP library for the Jira and Feishu preset,
together with its runtime dependencies urllib3, certifi, charset-normalizer,
and idna.

- Source: https://github.com/psf/requests
- License: Apache License 2.0
- Copyright: Kenneth Reitz and Requests contributors

These packages are installed as Python dependencies and retain their upstream
license metadata.

## Material Symbols Rounded

泡泡工具箱 includes the Material Symbols Rounded variable font from Google's
`material-design-icons` project.

- Source: https://github.com/google/material-design-icons
- License: Apache License 2.0
- Copyright: Google LLC

The font is used only as the application's icon library.

## scrcpy 4.0

泡泡工具箱 packages the official scrcpy 4.0 distribution for the target
platform: Windows x64, macOS Apple Silicon, or macOS Intel. Each package
includes the matching Android Debug Bridge executable and runtime files.

- Source: https://github.com/Genymobile/scrcpy
- Release: https://github.com/Genymobile/scrcpy/releases/tag/v4.0
- License: Apache License 2.0
- Copyright: Genymobile and scrcpy contributors

The full scrcpy license is distributed beside the selected official archive
and copied into the runtime directory on first launch. FFmpeg, SDL, libusb,
and Android platform-tools components retain their respective upstream
licenses and notices. Package names and SHA-256 values are recorded in the
platform-specific `scrcpy-manifest*.json` files.

## CPython 3.13.14

泡泡工具箱 provisions a private CPython 3.13.14 runtime for user-authored
Python scripts. Windows uses the official x64 NuGet runtime; macOS uses the
matching Apple Silicon or Intel `python-build-standalone` archive.

- Source: https://www.python.org/
- Release: https://www.python.org/downloads/release/python-31314/
- License: Python Software Foundation License Version 2
- Copyright: Python Software Foundation

The complete CPython license is distributed as `PYTHON-LICENSE.txt` beside the
runtime package. Package sources and SHA-256 values are recorded in
`python-runtime*.json`.

## PowerShell 7.6.6

The Windows full edition includes the official PowerShell 7.6.6 x64 ZIP
runtime. The clean edition can download it on demand. Bundled packages are
verified against the SHA-256 value in `powershell-plugin.json`; application-managed
updates use official release checksums. The runtime retains its upstream
LICENSE.txt and ThirdPartyNotices.txt files.

- Source: https://github.com/PowerShell/PowerShell
- Release: https://github.com/PowerShell/PowerShell/releases/tag/v7.6.6
- License: MIT License
- Copyright: Microsoft Corporation and PowerShell contributors
