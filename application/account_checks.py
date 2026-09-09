from __future__ import annotations

from application.tasks import create_account_check_all_task, create_account_check_task
from services.task_runtime import task_runtime
from infrastructure.accounts_repository import AccountsRepository


class AccountChecksService:
    def __init__(self, repository: AccountsRepository | None = None):
        self.repository = repository or AccountsRepository()

    def check_all_async(self, platform: str = "") -> dict:
        task = create_account_check_all_task(platform or "")
        task_runtime.wake_up()
        return task

    def check_one_async(self, account_id: int) -> dict | None:
        if not self.repository.get(account_id):
            return None
        task = create_account_check_task(account_id)
        task_runtime.wake_up()
        return task
