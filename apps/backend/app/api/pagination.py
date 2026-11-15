"""Paginated lists (SA-5: ?page=, ?size=)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel


class PageParams(BaseModel):
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageParams:
    return PageParams(page=page, size=size)


PageDep = Annotated[PageParams, Depends(page_params)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int

    @classmethod
    def of[S: BaseModel](
        cls, schema: type[S], rows: Sequence[object], total: int, params: PageParams
    ) -> "Page[S]":
        items = [schema.model_validate(row) for row in rows]
        return Page[schema](items=items, total=total, page=params.page, size=params.size)
