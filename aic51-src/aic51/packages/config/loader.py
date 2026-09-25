from pathlib import Path
from typing import Any

from yaml import safe_load

from aic51.packages.logger import logger


class GlobalConfig:
    CONFIG_FILE = "config.yaml"
    __config = None
    __work_dir: Path | None = None

    @classmethod
    def set_work_dir(cls, work_dir: Path | str | None):
        if work_dir is not None:
            cls.__work_dir = Path(work_dir).resolve()
        else:
            cls.__work_dir = None
        cls.reload()

    @classmethod
    def reload(cls):
        cls.__config = None
        return cls.__load_config()

    @classmethod
    def __load_config(cls):
        if cls.__config:
            return cls.__config

        work_dir = cls.__work_dir if cls.__work_dir is not None else Path.cwd()
        config_path = work_dir / cls.CONFIG_FILE
        if not config_path.exists():
            config_path = work_dir / "workspace" / cls.CONFIG_FILE

        if not config_path.exists():
            logger.warning(f'"{cls.CONFIG_FILE}" not found at {work_dir}. Workspace need to be initialized first.')
            return {}

        with open(config_path, "r", encoding="utf-8") as f:
            cls.__config = safe_load(f)

        return cls.__config

    @classmethod
    def get(cls, *args) -> Any:
        try:
            res = cls.__load_config()
            for arg in args:
                res = res[arg]
            return res

        except (KeyError, TypeError):
            return None
