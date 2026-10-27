import ast
import re
from pathlib import Path

from PyInstaller.building.utils import format_binaries_and_datas

from poptools.paths import package_root


def test_release_bundles_images_referenced_by_qml():
    root = Path(__file__).resolve().parents[1]
    package = package_root()
    spec = ast.parse((root / "packaging/poptools.spec").read_text(encoding="utf-8"))
    data_assignment = next(node for node in spec.body if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == "common_datas"
                                   for target in node.targets))
    scope = {"ROOT": root, "PACKAGE": package}
    exec(compile(ast.Module(body=[data_assignment], type_ignores=[]), "poptools.spec", "exec"),
         scope)
    bundled = {Path(destination).as_posix(): Path(source)
               for destination, source in format_binaries_and_datas(scope["common_datas"])}
    referenced = set()
    for qml in (package / "ui/qml").rglob("*.qml"):
        for reference in re.findall(r'''["'](\.\./[^"']*/resources/icons/[^"']+)["']''',
                                    qml.read_text(encoding="utf-8")):
            asset = (qml.parent / reference).resolve()
            destination = (Path("poptools") / asset.relative_to(package)).as_posix()
            assert destination in bundled, f"{qml.name}: missing bundled image {reference}"
            assert bundled[destination].is_file()
            referenced.add(asset.name)
    assert "decade-camera.svg" in referenced
