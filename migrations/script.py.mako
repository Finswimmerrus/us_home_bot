from collections.abc import Sequence
from datetime import datetime
from sqlalchemy import Table, MetaData
from alembic import AutogenContext
from alembic.script import ScriptDirectory


def run_hooks(
    context: AutogenContext,
    operation: str,
    hooks: Sequence,
) -> None:
    pass


def include_object(
    object,
    name,
    type_,
    reflected,
    compare_to,
) -> bool:
    return True


def process_revision_directives(
    context,
    revision,
    directives,
) -> None:
    pass


def _render_ddl(
    autogen_context: AutogenContext,
    operation,
    **kw,
):
    pass


def include_schemas(
    context: AutogenContext,
    object,
    name,
    type_,
    reflected,
    compare_to,
):
    return True


def _exec(
    context,
    step,
    *,
    sql_compiler=None,
    check_first=False,
):
    pass


def include_sqt(
    context: AutogenContext,
    object,
    name,
    type_,
    reflected,
    compare_to,
) -> bool:
    return True


def _object_name(
    context,
    object,
):
    pass


def _format_table(
    context,
    table,
    first,
    last,
):
    pass


def render_ddl(
    autogen_context,
    operation,
    **kw,
):
    pass


def _autogen_context(
    context: AutogenContext,
    **kw,
):
    pass
