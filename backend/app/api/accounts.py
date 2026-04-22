"""SNS 계정 관리 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.base import get_db
from app.models.sns_account import SNSAccount
from app.models.user import User
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    market: str  # kr, us, jp
    platform: str  # instagram, youtube, linkedin, x, ...
    account_name: str
    account_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None


class AccountResponse(BaseModel):
    id: int
    market: str
    platform: str
    account_name: str
    account_id: str | None
    is_active: bool


@router.get("", response_model=list[AccountResponse])
async def list_accounts(
    market: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자의 SNS 계정 목록"""
    query = select(SNSAccount).where(SNSAccount.user_id == current_user.id)
    if market:
        query = query.where(SNSAccount.market == market)
    result = await db.execute(query.order_by(SNSAccount.market, SNSAccount.platform))
    accounts = result.scalars().all()
    return [
        AccountResponse(
            id=a.id,
            market=a.market,
            platform=a.platform,
            account_name=a.account_name,
            account_id=a.account_id,
            is_active=a.is_active,
        )
        for a in accounts
    ]


@router.post("", response_model=AccountResponse, status_code=201)
async def connect_account(
    req: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SNS 계정 연결"""
    account = SNSAccount(
        user_id=current_user.id,
        market=req.market,
        platform=req.platform,
        account_name=req.account_name,
        account_id=req.account_id,
        access_token=req.access_token,
        refresh_token=req.refresh_token,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse(
        id=account.id,
        market=account.market,
        platform=account.platform,
        account_name=account.account_name,
        account_id=account.account_id,
        is_active=account.is_active,
    )


@router.delete("/{account_id}", status_code=204)
async def disconnect_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SNS 계정 연결 해제"""
    result = await db.execute(
        select(SNSAccount).where(
            SNSAccount.id == account_id,
            SNSAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")

    await db.delete(account)
    await db.commit()
