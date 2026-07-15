from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def ensure_parent(path: PathLike) -> Path:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    return file_path


def relative_to_root(path: PathLike) -> str:
    return str(Path(path).resolve())


def output_url(path: PathLike, output_root: PathLike = "output") -> str | None:
    file_path = Path(path).resolve()
    root_path = Path(output_root).resolve()
    try:
        relative = file_path.relative_to(root_path)
    except ValueError:
        return None
    return "/output/" + relative.as_posix()
