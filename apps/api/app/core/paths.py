from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def storage_dir() -> Path:
    return repo_root() / "storage"


def normalized_data_dir() -> Path:
    return repo_root() / "data" / "normalized"


def raw_data_dir() -> Path:
    return repo_root() / "data" / "raw"


def artifacts_backtests_dir() -> Path:
    p = repo_root() / "artifacts" / "backtests"
    p.mkdir(parents=True, exist_ok=True)
    return p
