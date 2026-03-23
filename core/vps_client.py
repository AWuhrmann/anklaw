import json
import logging
import os
from typing import List, Optional

import paramiko

from .models import Card, CardStatus, CardType

logger = logging.getLogger(__name__)


class VPSClientError(Exception):
    pass


class VPSClient:
    """
    SSH client that communicates with the VPS queue.
    Calls vps_queue.py on the remote machine to read/update the card queue.
    """

    def __init__(
        self,
        host: str,
        user: str,
        ssh_key_path: str,
        port: int,
        script_path: str,
        db_path: str,
    ):
        self.host = host
        self.user = user
        self.ssh_key_path = os.path.expanduser(ssh_key_path)
        self.port = port
        self.script_path = script_path
        self.db_path = db_path
        self._ssh: Optional[paramiko.SSHClient] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self):
        self._ssh = paramiko.SSHClient()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self._ssh.connect(
                self.host,
                port=self.port,
                username=self.user,
                key_filename=self.ssh_key_path,
                timeout=15,
            )
            logger.debug(f"SSH connected to {self.user}@{self.host}:{self.port}")
        except Exception as e:
            raise VPSClientError(f"SSH connection failed to {self.host}: {e}") from e

    def disconnect(self):
        if self._ssh:
            self._ssh.close()
            self._ssh = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    def is_available(self) -> bool:
        try:
            self.connect()
            self.disconnect()
            return True
        except VPSClientError:
            return False

    # ------------------------------------------------------------------
    # Queue operations (delegate to vps_queue.py on the remote)
    # ------------------------------------------------------------------

    def get_pending_cards(self) -> List[Card]:
        raw = self._run_queue_cmd("--list-pending")
        if not raw.strip():
            return []
        data = json.loads(raw)
        return [_dict_to_card(d) for d in data]

    def mark_imported(self, card_ids: List[int]):
        if not card_ids:
            return
        ids_str = ",".join(map(str, card_ids))
        self._run_queue_cmd(f"--mark-imported {ids_str}")

    def mark_failed(self, card_ids: List[int], error: str = "import_failed"):
        if not card_ids:
            return
        ids_str = ",".join(map(str, card_ids))
        # Shell-escape the error string
        safe_error = error.replace("'", "\\'")
        self._run_queue_cmd(f"--mark-failed {ids_str} --error '{safe_error}'")

    def retry_failed(self) -> int:
        raw = self._run_queue_cmd("--retry-failed")
        return json.loads(raw).get("reset", 0)

    def get_stats(self) -> dict:
        raw = self._run_queue_cmd("--stats")
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_queue_cmd(self, args: str) -> str:
        python = f"{self.script_path}/venv/bin/python"
        cmd = f"cd {self.script_path} && {python} vps_queue.py --db {self.db_path} {args}"
        return self._run(cmd)

    def _run(self, cmd: str) -> str:
        if self._ssh is None:
            raise VPSClientError("Not connected. Use VPSClient as a context manager.")
        _, stdout, stderr = self._ssh.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if exit_code != 0:
            raise VPSClientError(
                f"Remote command failed (exit {exit_code}).\n"
                f"Command: {cmd}\n"
                f"Stderr:  {err}"
            )
        return out


def _dict_to_card(d: dict) -> Card:
    return Card(
        id=d["id"],
        front=d["front"],
        back=d["back"],
        tags=d.get("tags", []),
        deck_name=d["deck_name"],
        card_type=CardType(d.get("card_type", "Basic")),
        batch_id=d.get("batch_id"),
        status=CardStatus(d.get("status", "pending")),
    )
