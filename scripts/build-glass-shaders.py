"""Rebuild the checked-in Qt 6 shader pack after editing liquidglass.frag."""
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    shader_dir = (Path(__file__).resolve().parents[1]
                  / "src/poptools/ui/qml/components/glass/LiquidGlass/shaders")
    executable = shutil.which("pyside6-qsb")
    if executable is None:
        candidate = Path(sys.executable).parent / (
            "pyside6-qsb.exe" if sys.platform == "win32" else "pyside6-qsb")
        if not candidate.is_file():
            raise SystemExit("Install the project's PySide6 dependencies to obtain pyside6-qsb.")
        executable = str(candidate)
    for shader in (shader_dir / "liquidglass.vert", shader_dir / "liquidglass.frag",
                   shader_dir / "nativeglass.frag"):
        subprocess.run([executable, "--glsl", "300 es,330", "--hlsl", "50", "--msl", "12",
                        "-o", str(shader.with_name(shader.name + ".qsb")), str(shader)], check=True)


if __name__ == "__main__":
    main()
