"""
Reference number generators using PostgreSQL sequences.

All functions accept an open AsyncSession and return formatted reference strings:
  INC-4413           seq_inc_number
  RES-2026-0523      seq_res_number
  RFN-20260528-0001  seq_rfn_number
  DSP-20260528-0001  seq_dsp_number
  FRAUD-202605-0001  seq_fraud_number

TXN numbers are gateway-assigned — no sequence.
"""
from datetime import datetime, timezone

from sqlalchemy import text


async def next_inc_number(db) -> str:
    result = await db.execute(text("SELECT nextval('seq_inc_number')"))
    n = result.scalar()
    return f"INC-{n:04d}"


async def next_res_number(db) -> str:
    result = await db.execute(text("SELECT nextval('seq_res_number')"))
    n = result.scalar()
    year = datetime.now(timezone.utc).year
    return f"RES-{year}-{n:04d}"


async def next_rfn_number(db) -> str:
    result = await db.execute(text("SELECT nextval('seq_rfn_number')"))
    n = result.scalar()
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"RFN-{date_str}-{n:04d}"


async def next_dsp_number(db) -> str:
    result = await db.execute(text("SELECT nextval('seq_dsp_number')"))
    n = result.scalar()
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"DSP-{date_str}-{n:04d}"


async def next_fraud_number(db) -> str:
    result = await db.execute(text("SELECT nextval('seq_fraud_number')"))
    n = result.scalar()
    month_str = datetime.now(timezone.utc).strftime("%Y%m")
    return f"FRAUD-{month_str}-{n:04d}"
