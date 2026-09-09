from __future__ import annotations

from fastapi import APIRouter, HTTPException

from application.account_checks import AccountChecksService

router = APIRouter(prefix="/accounts", tags=["account-checks"])
service = AccountChecksService()


@router.post("/check-all")
def check_all_accounts(platform: str = ""):
    return service.check_all_async(platform)


@router.post("/{account_id}/check")
def check_account(account_id: int):
    result = service.check_one_async(account_id)
    if not result:
        raise HTTPException(404, "账号不存在")
    return result
