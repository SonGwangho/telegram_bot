"""Windows 작업 스케줄러에 서비스 재시작을 요청한다."""

import logging
import os
from pathlib import Path
import subprocess
import sys


logger = logging.getLogger(__name__)
RESTART_TASK_NAME = "TelegramBot-Restart"


class ServiceRestartError(RuntimeError):
    """서비스 재시작 작업을 요청할 수 없다."""


def ensure_restart_task() -> None:
    """배포 계정 또는 봇 서비스 계정으로 재시작 작업을 자동 등록·갱신한다."""
    if sys.platform != "win32":
        return

    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise ServiceRestartError("Windows 시스템 경로를 확인할 수 없어요.")
    executable = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    installer = Path(__file__).resolve().parent / "scripts" / "install-telegrambot-restart-task.ps1"
    try:
        result = subprocess.run(
            [
                str(executable), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden", "-File", str(installer), "-IfNeeded",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.exception("Could not configure the service restart task automatically.")
        raise ServiceRestartError("재시작 작업 자동 설정에 실패했어요. 서버 로그를 확인해 주세요.") from error
    if result.returncode != 0:
        logger.warning(
            "Automatic restart task setup failed: exit code %s; output=%r",
            result.returncode, result.stdout,
        )
        raise ServiceRestartError(
            "재시작 작업 자동 설정에 실패했어요. 서비스 또는 배포 계정의 Windows 작업 등록 권한을 확인해 주세요."
        )


def request_service_restart() -> None:
    """서비스와 독립적으로 등록된 작업만 실행하며, 직접 서비스를 중지하지 않는다."""
    if sys.platform != "win32":
        raise ServiceRestartError("서비스 재시작은 Windows 서버에서만 사용할 수 있어요.")

    ensure_restart_task()
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise ServiceRestartError("Windows 시스템 경로를 확인할 수 없어요.")

    executable = Path(system_root) / "System32" / "schtasks.exe"
    try:
        result = subprocess.run(
            [str(executable), "/Run", "/TN", RESTART_TASK_NAME],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        logger.warning("Service restart task request timed out.")
        raise ServiceRestartError(
            "재시작 작업 요청 시간이 초과됐어요. 서버에서 작업 실행 여부를 확인해 주세요."
        ) from error
    except OSError as error:
        logger.exception("Could not execute the service restart task request.")
        raise ServiceRestartError("재시작 작업을 실행할 수 없어요. 서버 설정을 확인해 주세요.") from error

    if result.returncode != 0:
        logger.warning("Service restart task request failed: exit code %s", result.returncode)
        raise ServiceRestartError(
            "재시작 작업 요청에 실패했어요. 서버의 작업 등록 상태와 실행 권한을 확인해 주세요."
        )
