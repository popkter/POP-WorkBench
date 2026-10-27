"""Pop’s Workbench desktop application (legacy poptools module)."""

try:
    from poptools._build_version import __build_version__  # type: ignore[import-untyped]

    __version__ = __build_version__
except ImportError:
    # Development environments use the package metadata; release builds get
    # the generated _build_version.py file above.
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("pops-workbench")
    except PackageNotFoundError:
        # Existing editable environments may still use the previous metadata.
        try:
            __version__ = version("poptools")
        except PackageNotFoundError:
            __version__ = "0.0.0"
