from loguru import logger
from fastapi import HTTPException
from pathlib import Path


def safe_join(base: Path, *paths, relative: bool = False) -> Path:
    """
    Safely join paths to prevent path traversal attacks.

    Args:
        base (Path): The base directory.
        *paths (str): Path components to join.
        relative (bool): If True, return the path relative to the base.
                        If False (default), return the absolute path.

    Returns:
        Path: The resolved path (absolute or relative).

    Raises:
        ValueError: If the path tries to escape the base directory.
    """
    base = base.resolve()
    full_path = (base / Path(*paths)).resolve()
    if not full_path.is_relative_to(base):
        logger.error(f"Invalid Path: {full_path}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return full_path.relative_to(base) if relative else full_path