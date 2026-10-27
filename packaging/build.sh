#!/bin/bash
set -euo pipefail

SKIP_TESTS=0
FULL_TESTS=0
VERSION_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-tests) SKIP_TESTS=1 ;;
        --full-tests) FULL_TESTS=1 ;;
        --version)
            [[ $# -ge 2 ]] || { echo "--version requires a value" >&2; exit 2; }
            VERSION_OVERRIDE="$2"
            shift
            ;;
        -h|--help)
            echo "Usage: packaging/build.sh [--skip-tests] [--full-tests] [--version YYYY-MM-DD_x.x.x]"
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

[[ "$(uname -s)" == "Darwin" ]] || { echo "This build script requires macOS." >&2; exit 1; }

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${POPTOOLS_BUILD_VENV:-$PROJECT_ROOT/.venv}"
VENV_PYTHON="$VENV_DIR/bin/python"
[[ -x "$VENV_PYTHON" ]] || {
    echo "Project venv is missing: $VENV_PYTHON" >&2
    echo "Create it with: uv venv --python 3.11 .venv" >&2
    exit 1
}
PYTHON_SERIES="$($VENV_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
[[ "$PYTHON_SERIES" == "3.11" ]] || {
    echo "macOS builds require a Python 3.11 venv; found $PYTHON_SERIES." >&2
    exit 1
}

case "$(uname -m)" in
    arm64) ARCHITECTURE="arm64" ;;
    x86_64) ARCHITECTURE="x64" ;;
    *) echo "Unsupported macOS architecture: $(uname -m)" >&2; exit 1 ;;
esac

VENDOR_DIR="$PROJECT_ROOT/src/poptools/resources/vendor"
PYTHON_VENDOR_DIR="$VENDOR_DIR/python"
SCRCPY_MANIFEST="$VENDOR_DIR/scrcpy-manifest-macos-$ARCHITECTURE.json"
PYTHON_MANIFEST="$PYTHON_VENDOR_DIR/python-runtime-macos-$ARCHITECTURE.json"

download_manifest_package() {
    manifest="$1"
    package_key="$2"
    output_dir="$3"
    package_file="$($VENV_PYTHON -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "$manifest" "$package_key")"
    package_url="$($VENV_PYTHON -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["url"])' "$manifest")"
    expected_hash="$($VENV_PYTHON -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["sha256"])' "$manifest")"
    destination="$output_dir/$package_file"
    if [[ ! -f "$destination" ]]; then
        mkdir -p "$output_dir"
        echo "Downloading $package_file..."
        curl --fail --location --retry 3 --connect-timeout 20 --max-time 600 \
            --output "$destination" "$package_url"
    fi
    actual_hash="$(shasum -a 256 "$destination" | awk '{print $1}')"
    [[ "$actual_hash" == "$expected_hash" ]] || {
        echo "Checksum mismatch: $destination" >&2
        exit 1
    }
}

download_manifest_package "$SCRCPY_MANIFEST" archive "$VENDOR_DIR"
download_manifest_package "$PYTHON_MANIFEST" file "$PYTHON_VENDOR_DIR"

ACTUAL_PREFIX="$($VENV_PYTHON -c 'import pathlib,sys; print(pathlib.Path(sys.prefix).resolve())')"
EXPECTED_PREFIX="$(cd "$VENV_DIR" && pwd)"
[[ "$ACTUAL_PREFIX" == "$EXPECTED_PREFIX" ]] || {
    echo "Build must use the project .venv. Actual prefix: $ACTUAL_PREFIX" >&2
    exit 1
}

if ! "$VENV_PYTHON" -c 'import PIL, PyInstaller, PySide6, platformdirs, psutil, pydantic, pypinyin, pytest' >/dev/null 2>&1; then
    echo "Installing development dependencies..."
    UV_EXECUTABLE="$(command -v uv || true)"
    [[ -n "$UV_EXECUTABLE" ]] || UV_EXECUTABLE="$VENV_DIR/bin/uv"
    [[ -x "$UV_EXECUTABLE" ]] || UV_EXECUTABLE="$PROJECT_ROOT/.venv/bin/uv"
    if [[ -x "$UV_EXECUTABLE" ]]; then
        "$UV_EXECUTABLE" pip install --python "$VENV_PYTHON" -e "$PROJECT_ROOT[dev]"
    else
        "$VENV_PYTHON" -c 'import pip' >/dev/null 2>&1 || "$VENV_PYTHON" -m ensurepip
        "$VENV_PYTHON" -m pip install -e "$PROJECT_ROOT[dev]"
    fi
fi

"$PROJECT_ROOT/packaging/build-native.sh"

if [[ "$SKIP_TESTS" -eq 0 ]]; then
    TESTS_DIR="$PROJECT_ROOT/tests"
    TEST_FILE=""
    if [[ -d "$TESTS_DIR" ]]; then
        TEST_FILE="$(find "$TESTS_DIR" -type f \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit)"
    fi
    if [[ -z "$TEST_FILE" ]]; then
        echo "No pytest test files found; skipping test stage."
    else
        mkdir -p "$PROJECT_ROOT/build/test-results" "$PROJECT_ROOT/build/pytest-macos"
        TEST_SELECTION=()
        if [[ "$FULL_TESTS" -eq 0 ]]; then
            TEST_SELECTION=(-m 'not gui and not hardware')
            echo "Running build checks (excluding GUI/animation and real-device tests). Use --full-tests for all tests."
        fi
        "$VENV_PYTHON" -m pytest \
            --basetemp="$PROJECT_ROOT/build/pytest-macos/tmp" \
            -o cache_dir="$PROJECT_ROOT/build/pytest-macos/cache" \
            --junitxml="$PROJECT_ROOT/build/test-results/pytest-macos-$ARCHITECTURE.xml" \
            --tb=long -ra "${TEST_SELECTION[@]}"
    fi
fi

BASE_VERSION="$($VENV_PYTHON -c 'import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["project"]["version"])' "$PROJECT_ROOT/pyproject.toml")"
if [[ -n "$VERSION_OVERRIDE" ]]; then
    BUILD_VERSION="${VERSION_OVERRIDE#v}"
    [[ "$BUILD_VERSION" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
        echo "--version must use YYYY-MM-DD_x.x.x" >&2
        exit 1
    }
    "$VENV_PYTHON" -c 'import datetime,sys; datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d")' "${BUILD_VERSION%%_*}"
    [[ "${BUILD_VERSION#*_}" == "$BASE_VERSION" ]] || {
        echo "Build version does not match pyproject.toml version $BASE_VERSION" >&2
        exit 1
    }
else
    BUILD_VERSION="$(date +%Y-%m-%d)_$BASE_VERSION"
fi

VERSION_FILE="$PROJECT_ROOT/src/poptools/_build_version.py"
printf "%s\n%s\n" "# Auto-generated by build.sh — do not commit." "__build_version__ = '$BUILD_VERSION'" > "$VERSION_FILE"
echo "Build version: $BUILD_VERSION"

APP_PATH="$PROJECT_ROOT/dist/泡泡的工作台.app"
ARCHIVE_PATH="$PROJECT_ROOT/dist/泡泡的工作台-macos-$ARCHITECTURE.zip"
CHECKSUM_PATH="$ARCHIVE_PATH.sha256"
rm -rf "$PROJECT_ROOT/dist/泡泡工具箱" "$APP_PATH"
rm -f "$ARCHIVE_PATH" "$CHECKSUM_PATH"

cd "$PROJECT_ROOT"
export PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/build/pyinstaller-config"
mkdir -p "$PYINSTALLER_CONFIG_DIR"
"$VENV_PYTHON" -m PyInstaller --noconfirm --clean packaging/poptools.spec
[[ -d "$APP_PATH" ]] || { echo "Missing application bundle: $APP_PATH" >&2; exit 1; }

# No Developer ID is required during development. PyInstaller may apply the
# ad-hoc signature required for native arm64 Mach-O binaries.
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ARCHIVE_PATH"
ARCHIVE_HASH="$(shasum -a 256 "$ARCHIVE_PATH" | awk '{print $1}')"
printf "%s  %s\n" "$ARCHIVE_HASH" "$(basename "$ARCHIVE_PATH")" > "$CHECKSUM_PATH"

echo "macOS application: $APP_PATH"
echo "OTA archive: $ARCHIVE_PATH"
echo "OTA checksum: $CHECKSUM_PATH"
