"""REST API ルーター — /api/* エンドポイント。

全ルートは get_current_user (LIFF ID token 検証 + DB lookup) で保護される。
クエリはすべて user_id でスコープ (IDOR防止)。
"""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, field_validator

from auth import TokenVerificationError, verify_id_token
from db import get_db
from repositories.medications import (
    Medication,
    add_user_medication,
    get_medication_by_id,
    list_preset_medications,
    list_user_medications,
    remove_user_medication,
)
from repositories.servings import (
    Serving,
    get_or_create_serving,
    get_serving,
    list_servings,
    mark_taken,
)
from repositories.users import (
    User,
    get_or_create_user,
    get_settings,
    update_settings,
)

router = APIRouter()
_bearer = HTTPBearer()


# ---------- Auth dependency ----------

async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> User:
    """LIFF ID token を検証し、DB からユーザーを取得 (存在しなければ作成)。"""
    try:
        claims = verify_id_token(creds.credentials)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return get_or_create_user(conn, claims["sub"])


# ---------- Pydantic response models ----------

class UserResponse(BaseModel):
    id: int
    line_user_id: str
    display_name: str | None
    role: str


class SettingsResponse(BaseModel):
    morning_time: str
    evening_time: str
    evening_enabled: bool
    timezone: str
    reminder_mode: str
    reminder_interval_hours: int
    reminder_times: str


class SettingsPatchRequest(BaseModel):
    model_config = {"extra": "forbid"}

    morning_time: str | None = None
    evening_time: str | None = None
    evening_enabled: bool | None = None
    timezone: str | None = None
    reminder_mode: str | None = None
    reminder_interval_hours: int | None = None
    reminder_times: str | None = None

    @field_validator("morning_time", "evening_time", mode="before")
    @classmethod
    def validate_time_format(cls, v: str | None) -> str | None:
        import re
        if v is not None and not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"Invalid time format {v!r}: expected HH:MM")
        return v

    @field_validator("reminder_mode")
    @classmethod
    def validate_reminder_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in ("off", "interval", "fixed"):
            raise ValueError(f"reminder_mode must be off/interval/fixed, got {v!r}")
        return v

    @field_validator("reminder_interval_hours")
    @classmethod
    def validate_interval_hours(cls, v: int | None) -> int | None:
        if v is not None and (v < 0 or v > 24):
            raise ValueError(f"reminder_interval_hours must be 0..24, got {v}")
        return v

    @field_validator("reminder_times")
    @classmethod
    def validate_reminder_times(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        import re
        for t in v.split(","):
            t = t.strip()
            if not re.match(r"^\d{2}:\d{2}$", t):
                raise ValueError(f"Invalid reminder_times entry {t!r}")
        return v


class MedicationResponse(BaseModel):
    id: int
    name: str
    kind: str
    is_preset: bool


class UserMedRequest(BaseModel):
    medication_id: int
    slot: str

    @field_validator("slot")
    @classmethod
    def validate_slot(cls, v: str) -> str:
        if v not in ("morning", "evening"):
            raise ValueError(f"Invalid slot {v!r}: must be 'morning' or 'evening'")
        return v


class UserMedResponse(BaseModel):
    id: int
    medication_id: int
    slot: str


class ServingResponse(BaseModel):
    id: int
    scheduled_date: str
    slot: str
    taken_at: str | None
    pushed_at: str | None


class TodaySlotResponse(BaseModel):
    serving: ServingResponse
    medications: list[str]  # 薬名のリスト


class TodayResponse(BaseModel):
    morning: TodaySlotResponse | None
    evening: TodaySlotResponse | None


# ---------- Helpers ----------

def _serving_to_resp(s: Serving) -> ServingResponse:
    return ServingResponse(
        id=s.id,
        scheduled_date=s.scheduled_date,
        slot=s.slot,
        taken_at=s.taken_at,
        pushed_at=s.pushed_at,
    )


# ---------- Routes ----------

@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse(
        id=user.id,
        line_user_id=user.line_user_id,
        display_name=user.display_name,
        role=user.role,
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_user_settings(
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> SettingsResponse:
    s = get_settings(conn, user.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Settings not found")
    return SettingsResponse(
        morning_time=s.morning_time,
        evening_time=s.evening_time,
        evening_enabled=s.evening_enabled,
        timezone=s.timezone,
        reminder_mode=s.reminder_mode,
        reminder_interval_hours=s.reminder_interval_hours,
        reminder_times=s.reminder_times,
    )


@router.patch("/settings", response_model=SettingsResponse)
async def patch_user_settings(
    body: SettingsPatchRequest,
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> SettingsResponse:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        update_settings(conn, user.id, updates)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    s = get_settings(conn, user.id)
    return SettingsResponse(
        morning_time=s.morning_time,
        evening_time=s.evening_time,
        evening_enabled=s.evening_enabled,
        timezone=s.timezone,
        reminder_mode=s.reminder_mode,
        reminder_interval_hours=s.reminder_interval_hours,
        reminder_times=s.reminder_times,
    )


@router.get("/medications", response_model=list[MedicationResponse])
async def list_medications(
    _user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> list[MedicationResponse]:
    return [
        MedicationResponse(id=m.id, name=m.name, kind=m.kind, is_preset=m.is_preset)
        for m in list_preset_medications(conn)
    ]


@router.get("/user-medications", response_model=list[UserMedResponse])
async def list_user_meds(
    slot: Annotated[str, Query(description="morning or evening")],
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> list[UserMedResponse]:
    if slot not in ("morning", "evening"):
        raise HTTPException(status_code=422, detail="slot must be morning or evening")
    meds = list_user_medications(conn, user_id=user.id, slot=slot)
    return [UserMedResponse(id=m.id, medication_id=m.medication_id, slot=m.slot) for m in meds]


@router.post("/user-medications", response_model=UserMedResponse, status_code=201)
async def add_user_med(
    body: UserMedRequest,
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> UserMedResponse:
    if get_medication_by_id(conn, body.medication_id) is None:
        raise HTTPException(status_code=404, detail="Medication not found")
    add_user_medication(conn, user_id=user.id, medication_id=body.medication_id, slot=body.slot)
    meds = list_user_medications(conn, user_id=user.id, slot=body.slot)
    um = next(m for m in meds if m.medication_id == body.medication_id)
    return UserMedResponse(id=um.id, medication_id=um.medication_id, slot=um.slot)


@router.delete("/user-medications/{medication_id}", status_code=204)
async def remove_user_med(
    medication_id: int,
    slot: Annotated[str, Query()],
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> None:
    remove_user_medication(conn, user_id=user.id, medication_id=medication_id, slot=slot)


@router.get("/today", response_model=TodayResponse)
async def today(
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> TodayResponse:
    """今日の服薬予定。薬が登録されていないスロットは null を返す。"""
    today_str = date.today().isoformat()

    def _slot_response(slot: str) -> TodaySlotResponse | None:
        user_meds = list_user_medications(conn, user_id=user.id, slot=slot)
        if not user_meds:
            return None
        # 薬名を取得
        med_names: list[str] = []
        for um in user_meds:
            med = get_medication_by_id(conn, um.medication_id)
            if med is not None:
                med_names.append(med.name)
        serving = get_or_create_serving(conn, user_id=user.id, date=today_str, slot=slot)
        return TodaySlotResponse(
            serving=_serving_to_resp(serving),
            medications=med_names,
        )

    return TodayResponse(
        morning=_slot_response("morning"),
        evening=_slot_response("evening"),
    )


@router.post("/servings/{serving_id}/take", response_model=ServingResponse)
async def take_serving(
    serving_id: int,
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ServingResponse:
    s = get_serving(conn, serving_id=serving_id, user_id=user.id)
    if s is None:
        raise HTTPException(status_code=404, detail="Serving not found")
    taken = mark_taken(conn, user_id=user.id, serving_id=serving_id)
    if not taken:
        raise HTTPException(status_code=409, detail="Already taken")
    s = get_serving(conn, serving_id=serving_id, user_id=user.id)
    return _serving_to_resp(s)


@router.get("/servings", response_model=list[ServingResponse])
async def list_user_servings(
    from_date: Annotated[str, Query(alias="from_date")],
    to_date: Annotated[str, Query(alias="to_date")],
    user: Annotated[User, Depends(get_current_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> list[ServingResponse]:
    servings = list_servings(conn, user_id=user.id, from_date=from_date, to_date=to_date)
    return [_serving_to_resp(s) for s in servings]
