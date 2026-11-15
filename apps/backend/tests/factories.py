"""Rows shared by the catalogue tests."""

import uuid
from typing import Any

from sqlalchemy import Connection, text

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def insert(conn: Connection, table: str, **values: Any) -> uuid.UUID:
    columns = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    return conn.execute(
        text(f"INSERT INTO {table} ({columns}) VALUES ({params}) RETURNING id"), values
    ).scalar_one()


def new_program(conn: Connection, institution: uuid.UUID, code: str, **values: Any) -> uuid.UUID:
    defaults = {"name": f"Formation {code}", "type": "licence", "duration_years": 3}
    return insert(conn, "programs", institution_id=institution, code=code, **defaults | values)
