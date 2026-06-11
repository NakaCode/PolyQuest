"""Redireciona exceções não tratadas para um arquivo de log."""
import sys
import traceback
from pathlib import Path


def setup(log_path: Path):
    def handler(exc_type, exc_value, exc_tb):
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)

    sys.excepthook = handler
