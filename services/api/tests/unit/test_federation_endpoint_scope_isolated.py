"""Isolated federation endpoint authorization regression tests.

These execute endpoint function bodies without FastAPI startup, PostgreSQL,
MRI data, PyTorch, or dependency injection. They are not HTTP integration tests.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, status


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "app/api/v1/federation.py"
)


class FakeUpdateRepository:
    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.calls = []

    def list_update_artifacts(self, *, hospital_id=None):
        self.calls.append(hospital_id)

        if hospital_id is None:
            return list(self.artifacts)

        return [
            artifact
            for artifact in self.artifacts
            if artifact.hospital_id == hospital_id
        ]


def load_endpoint_function(name, repository):
    """Execute the real endpoint body with explicit synthetic dependencies."""

    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    ]

    assert len(matches) == 1

    original = matches[0]

    args = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=item.arg) for item in original.args.args],
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[],
    )

    function = ast.FunctionDef(
        name=original.name,
        args=args,
        body=original.body,
        decorator_list=[],
        returns=None,
        type_comment=None,
        type_params=[],
    )

    module = ast.fix_missing_locations(
        ast.Module(body=[function], type_ignores=[])
    )

    namespace = {
        "SqlAlchemyFederationRepository": lambda session: repository,
        "update_artifact_response": lambda item: item,
        "HTTPException": HTTPException,
        "status": status,
    }

    exec(compile(module, str(SOURCE), "exec"), namespace)

    return namespace[name]


@pytest.mark.parametrize("selected", [0, 1])
def test_hospital_admin_sees_only_own_updates(selected):
    hospital_ids = [uuid4(), uuid4()]

    artifacts = [
        SimpleNamespace(hospital_id=hospital_id)
        for hospital_id in hospital_ids
    ]

    repository = FakeUpdateRepository(artifacts)

    endpoint = load_endpoint_function(
        "list_model_update_artifacts",
        repository,
    )

    principal = SimpleNamespace(
        email="admin@example.test",
        hospital_id=hospital_ids[selected],
    )

    settings = SimpleNamespace(
        federation_operator_emails=frozenset(
            {"operator@example.test"}
        )
    )

    result = endpoint(principal, object(), settings)

    assert result == [artifacts[selected]]
    assert repository.calls == [hospital_ids[selected]]


def test_operator_can_view_global_update_metadata():
    artifacts = [
        SimpleNamespace(hospital_id=uuid4()),
        SimpleNamespace(hospital_id=uuid4()),
    ]

    repository = FakeUpdateRepository(artifacts)

    endpoint = load_endpoint_function(
        "list_model_update_artifacts",
        repository,
    )

    principal = SimpleNamespace(
        email="operator@example.test",
        hospital_id=uuid4(),
    )

    settings = SimpleNamespace(
        federation_operator_emails=frozenset(
            {"operator@example.test"}
        )
    )

    result = endpoint(principal, object(), settings)

    assert result == artifacts
    assert repository.calls == [None]


def test_missing_hospital_id_is_rejected_before_query():
    repository = FakeUpdateRepository(
        [SimpleNamespace(hospital_id=uuid4())]
    )

    endpoint = load_endpoint_function(
        "list_model_update_artifacts",
        repository,
    )

    principal = SimpleNamespace(
        email="admin@example.test",
        hospital_id=None,
    )

    settings = SimpleNamespace(
        federation_operator_emails=frozenset(
            {"operator@example.test"}
        )
    )

    with pytest.raises(HTTPException) as captured:
        endpoint(principal, object(), settings)

    assert captured.value.status_code == 403
    assert repository.calls == []


def test_summary_requires_an_early_hospital_identity_guard():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "federation_summary"
    ]

    assert len(functions) == 1

    body = functions[0].body

    # Skip the function docstring.
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    assert body

    first_statement = body[0]

    assert isinstance(first_statement, ast.If)

    assert (
        "principal.hospital_id is None"
        in ast.unparse(first_statement.test)
    )

    assert any(
        isinstance(node, ast.Raise)
        for node in ast.walk(first_statement)
    )
