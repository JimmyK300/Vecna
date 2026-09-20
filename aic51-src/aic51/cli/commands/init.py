import shutil

import aic51.resources as resources

from .command import BaseCommand

class InitCommand(BaseCommand):
    def __init__(self, *args, **kwargs):
        super(InitCommand, self).__init__(*args, **kwargs)

    def add_args(self, subparser):
        parser = subparser.add_parser("init", help="Initialize AIC51 working directory")

        parser.set_defaults(func=self)

    def __call__(self, *args, **kwargs):
        from aic51.packages.logger import logger

        layout_dir = resources.LAYOUT_FILE_PATH
        config_path = self._work_dir / "config.yaml"
        if config_path.exists():
            logger.warning(f"config.yaml already exists in {self._work_dir}, updating layout...")
        shutil.copytree(layout_dir, self._work_dir, dirs_exist_ok=True)
        logger.info(f"Initialized AIC51 working directory at: {self._work_dir}")
