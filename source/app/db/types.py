from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine


class ExactNumeric(TypeDecorator[Decimal]):
    """Exact Decimal storage across PostgreSQL and SQLite.

    PostgreSQL receives a real NUMERIC column.  SQLite NUMERIC affinity may
    coerce decimal text to binary REAL, so SQLite deliberately stores the
    canonical decimal string and converts it back on read.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int = 38, scale: int = 18) -> None:
        self.precision = precision
        self.scale = scale
        super().__init__(precision=precision, scale=scale, asdecimal=True)

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(96))
        return dialect.type_descriptor(
            Numeric(self.precision, self.scale, asdecimal=True)
        )

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Decimal | str | None:
        if value is None:
            return None
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        if dialect.name == "sqlite":
            return format(decimal_value, "f")
        return decimal_value

    def process_result_value(self, value: object, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))
