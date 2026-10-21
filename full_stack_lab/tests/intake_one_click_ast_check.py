"""Execute the real approval bodies with Pydantic and DB/HTTP doubles, without importing the app.

This supplements, and never replaces, running intake_one_click_check.py in the gateway image.
It cannot validate framework wiring, PostgreSQL locking, MCP or deployment behavior.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib.util
import json
import re
import sys
import types
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LAB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "gateway"))
from app import high_impact, intake_proposal, provenance, residency, risk_tier, supplier_assurance


class Jsonb:
    def __init__(self, obj, **kwargs):
        self.obj = obj
        json.dumps(obj, default=str)


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code


async def unpatched(*args, **kwargs):
    raise AssertionError("Unexpected dependency call")


def load(name, file, selected, extra):
    tree = ast.parse((LAB / "gateway/app" / file).read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        identifiers = ([node.name] if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else
                       [n.id for n in node.targets if isinstance(n, ast.Name)] if isinstance(node, ast.Assign) else [])
        if not set(identifiers) & set(selected):
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node.decorator_list = []
        nodes.append(node)
    found = {node.name for node in nodes if hasattr(node, "name")}
    if not {n for n in selected if n[0].islower()} <= found | {n.id for node in nodes if isinstance(node, ast.Assign) for n in node.targets if isinstance(n, ast.Name)}:
        raise AssertionError("Requested production symbol is missing")
    module = types.ModuleType(name)
    module.__dict__.update({"json": json, "re": re, "hashlib": hashlib, "UTC": UTC, "datetime": datetime,
        "timedelta": timedelta, "Any": Any, "Literal": Literal, "UUID": UUID,
        "BaseModel": BaseModel, "ConfigDict": ConfigDict, "Field": Field,
        "field_validator": field_validator, "model_validator": model_validator,
        "Jsonb": Jsonb, "HTTPException": HTTPException, "high_impact": high_impact, "intake_proposal": intake_proposal,
        "provenance": provenance, "residency": residency, "risk_tier": risk_tier, "supplier_assurance": supplier_assurance,
        "urlsplit": urlsplit}, **extra)
    module.__dict__["__name__"] = name
    module.__dict__["__package__"] = "app"
    sys.modules[name] = module
    exec(compile(ast.Module(body=nodes, type_ignores=[]), file, "exec"), module.__dict__)
    return module


db = types.SimpleNamespace(fetch_one=unpatched, fetch_all=unpatched, execute=unpatched, transaction=unpatched)
canonical_hash = load("app.intake_hash_ast", "contract.py", ["canonical_hash"], {}).canonical_hash
contract = load("app.intake_contract_ast", "agent_contract.py", ["StrictModel", "ResidencyFields", "ToolReview"], {})
classify = load("app.intake_classify_ast", "classify.py", ["ADDRESS_ARG"], {})
review = load("app.intake_review_ast", "review.py", ["SCANNERS", "DESTINATION", "ARGUMENT", "SERVER", "_ADDRESS_ARG",
    "RISK_ACCEPTANCE_MAX_DAYS", "RISK_ACCEPTANCE_MIN_REASON", "NotIndependent", "require_independent", "intake_gate",
    "normalize_tool_reviews", "scope_terms", "check_inputs", "derived_constraints"],
    {"db": db, "ADDRESS_ARG": classify.ADDRESS_ARG, "record_event": unpatched, "same_person": unpatched,
     "intake_reports": unpatched, "active_acceptance": unpatched, "accept_risk": unpatched})
review.transition = unpatched
service = load("app.intake_service_ast", "agent_service.py", ["ApprovalPreview", "OneClickApproval", "IntakeRegistration",
    "ProvenanceMismatch", "approval_row", "preview_intake_approval", "approve_and_register", "register_mcp_request",
    "EXIT_TERM_KEYS", "exit_term_flags"],
    {"db": db, "review": review, "StrictModel": contract.StrictModel, "ResidencyFields": contract.ResidencyFields,
     "ToolReview": contract.ToolReview, "Depends": lambda value: None, "Header": lambda **kwargs: None,
     "admin_caller": None, "INTAKE_APPROVAL_LOCK": asyncio.Lock(), "current_identity": unpatched, "gateway_proxy": unpatched,
     "publish_internal_repo": unpatched, "core": types.SimpleNamespace(canonical_hash=canonical_hash)})
scope_core = load("app.intake_core_ast", "core.py", ["register_server"], {"db": db, "review": review, "uuid": uuid,
    "registry": types.SimpleNamespace(catalog=lambda: {}), "registration_endpoint": lambda endpoint: endpoint,
    "canonical_hash": canonical_hash})
service.core = scope_core

spec = importlib.util.spec_from_file_location("intake_one_click_cases", LAB / "tests/intake_one_click_check.py")
cases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases)
cases.service, cases.review, cases.HTTPException = service, review, HTTPException
cases.ApprovalFlowCheck.__unittest_skip__ = False

if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(cases.ApprovalFlowCheck))
    raise SystemExit(not result.wasSuccessful())
