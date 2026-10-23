"""Fail-closed separation of AutoHarness-owned Pi and known Claude storage paths."""
import os
from pathlib import Path


def resolve_storage_path(path):
    try:
        return Path(path).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"AutoHarness Pi isolation: cannot resolve {path}: {exc}") from exc


def _overlap(left, right):
    return left.is_relative_to(right) or right.is_relative_to(left)


def _aliases(root, shared_files):
    """Inspect metadata only; follow aliases and record multiply linked files."""
    result = {resolve_storage_path(root)}
    pending = [(Path(root), frozenset())]
    visited = set()
    while pending:
        path, ancestors = pending.pop()
        try:
            stat = path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if identity in ancestors:
                raise ValueError(f"AutoHarness Pi isolation: cyclic directory alias at {path}")
            if identity in visited:
                continue
            visited.add(identity)
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            result.add(resolve_storage_path(entry.path))
                        if entry.is_file(follow_symlinks=True):
                            linked = entry.stat(follow_symlinks=True)
                            if linked.st_nlink > 1:
                                shared_files.add((linked.st_dev, linked.st_ino))
                        if entry.is_dir(follow_symlinks=True):
                            pending.append((Path(entry.path), ancestors | {identity}))
                    except FileNotFoundError:
                        continue  # atomic cleanup must not skip the remaining directory entries
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError(f"AutoHarness Pi isolation: cannot inspect {path}: {exc}") from exc
    return result


def assert_isolated(roots, cwd, project_owner):
    if set(roots) != {"project", "global"}:
        raise ValueError("AutoHarness Pi isolation: explicit project and global roots are both required")
    cwd = resolve_storage_path(cwd)
    claude = {Path.home() / ".claude", Path(project_owner) / ".claude"}
    for parent in (cwd, *cwd.parents):
        candidate = parent / ".claude"
        if candidate.exists() or candidate.is_symlink():
            claude.add(candidate)
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        claude.add(Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser())
    forbidden = {resolve_storage_path(path) for path in claude}
    claude_files = set()
    for root in claude:
        for area in ("skills", "autoharness"):
            forbidden.update(_aliases(root / area, claude_files))
    managed = []
    for level, root in roots.items():
        for area in ("skills", "autoharness"):
            shared_files = set()
            aliases = _aliases(Path(root) / area, shared_files)
            if shared_files & claude_files:
                raise ValueError(f"AutoHarness Pi isolation: {level}/{area} shares hardlinked files with Claude storage")
            for path in aliases:
                for other in forbidden:
                    if _overlap(path, other):
                        raise ValueError(f"AutoHarness Pi isolation: {level}/{area} path {path} overlaps Claude storage {other}")
            managed.append((f"{level}/{area}", aliases, shared_files))
    for index, (name, aliases, files) in enumerate(managed):
        for other_name, other_aliases, other_files in managed[index + 1:]:
            if files & other_files or any(_overlap(left, right) for left in aliases for right in other_aliases):
                raise ValueError(f"AutoHarness Pi isolation: managed areas {name} and {other_name} overlap")
