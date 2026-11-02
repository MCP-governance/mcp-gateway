"""Password change, password reset and sign-in name change on a real schema.

Run through termination_dispatch_lab.sh (or with DATABASE_URL pointing at a disposable PostgreSQL). The handlers
are the console's own; only the caller identity is given, so the permission rules, the bcrypt update, the
session revocation and the rename SQL all run on PostgreSQL."""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import agent_service as service
from app import db
from termination_lab_support import Checks, apply_schema, run, signing_keys

CHECKS = Checks("account password and sign-in name management (PostgreSQL)")
ROOT = {"roles": ["admin"], "principal": "root", "user_id": "root", "email": "root"}
ADMIN1 = {"roles": ["admin"], "principal": "admin1", "user_id": "admin1", "email": "admin1"}
EMPLOYEE = {"roles": ["employee"], "principal": "emp-lee", "user_id": "lee", "email": "lee"}


async def account(token, user_id, email, role, password):
    await db.execute(
        """INSERT INTO principals(token, user_id, email, display_name, role, status, password_hash)
           VALUES (%s,%s,%s,%s,%s,'active',crypt(%s, gen_salt('bf', 4)))
           ON CONFLICT (token) DO UPDATE SET user_id=EXCLUDED.user_id, email=EXCLUDED.email, role=EXCLUDED.role,
             status='active', password_hash=EXCLUDED.password_hash""",
        (token, user_id, email, user_id, role, password))


async def signs_in(name, password):
    try:
        await service.password_principal(name, password, f"check-{uuid.uuid4()}")
        return True
    except HTTPException:
        return False


async def status_of(coroutine):
    try:
        await coroutine
        return 200
    except HTTPException as exc:
        return exc.status_code


def as_user(user):
    return patch.object(service, "current_identity", AsyncMock(return_value=user))


async def reset_rules():
    with as_user(ROOT):
        code = await status_of(service.reset_account_password("admin1", service.PasswordReset(new_password="root-set-pass1"), "Bearer x"))
    CHECKS.ok("root resets an administrator's password", code == 200 and await signs_in("admin1", "root-set-pass1"))
    row = await db.fetch_one("SELECT password_changed_by FROM principals WHERE token='admin1'")
    CHECKS.ok("the reset records who set the password", row["password_changed_by"] == "root")
    with as_user(ROOT):
        short = await status_of(service.reset_account_password("admin1", service.PasswordReset(new_password="ten-chars1"), "Bearer x"))
    CHECKS.ok("an administrator's password needs 12 characters, as on the server command", short == 422)
    with as_user(ADMIN1):
        other_admin = await status_of(service.reset_account_password("admin2", service.PasswordReset(new_password="not-allowed1"), "Bearer x"))
        employee = await status_of(service.reset_account_password("lee", service.PasswordReset(new_password="admin-set-pass1"), "Bearer x"))
        own = await status_of(service.reset_account_password("admin1", service.PasswordReset(new_password="self-reset-1"), "Bearer x"))
    CHECKS.ok("an administrator other than root cannot reset another administrator", other_admin == 403)
    CHECKS.ok("an administrator resets an employee's password", employee == 200 and await signs_in("lee", "admin-set-pass1"))
    CHECKS.ok("nobody resets their own password from the account list", own == 409)
    with as_user(EMPLOYEE):
        code = await status_of(service.reset_account_password("admin1", service.PasswordReset(new_password="employee-try1"), "Bearer x"))
    CHECKS.ok("an employee cannot reset passwords", code == 403)


async def reset_ends_sessions():
    session = uuid.uuid4()
    await db.execute("INSERT INTO console_sessions(jti, user_id, expires_at) VALUES (%s,'lee',now()+interval '1 hour')", (session,))
    with as_user(ROOT):
        await service.reset_account_password("lee", service.PasswordReset(new_password="second-reset-1"), "Bearer x")
    left = await db.fetch_one("SELECT count(*) AS n FROM console_sessions WHERE user_id='lee'")
    CHECKS.ok("a reset signs the account out of the console", left["n"] == 0)


async def rename_rules():
    with as_user(ROOT):
        code = await status_of(service.rename_account("admin2", service.AccountRename(user_id="kim"), "Bearer x"))
    row = await db.fetch_one("SELECT user_id, email, display_name FROM principals WHERE token='admin2'")
    CHECKS.ok("root renames an administrator; the principal stays and a default display name follows",
              code == 200 and row == {"user_id": "kim", "email": "kim", "display_name": "kim"})
    CHECKS.ok("the new name signs in and the old one does not",
              await signs_in("kim", "admin2-pass1") and not await signs_in("admin2", "admin2-pass1"))
    with as_user(ROOT):
        taken = await status_of(service.rename_account("admin1", service.AccountRename(user_id="lee"), "Bearer x"))
        bad = await status_of(service.rename_account("admin1", service.AccountRename(user_id="Bad Name"), "Bearer x"))
        same = await status_of(service.rename_account("admin1", service.AccountRename(user_id="admin1"), "Bearer x"))
        own = await status_of(service.rename_account("root", service.AccountRename(user_id="boss"), "Bearer x"))
        mailed = await status_of(service.rename_account("park", service.AccountRename(user_id="park2"), "Bearer x"))
    CHECKS.ok("a name in use is refused", taken == 409)
    CHECKS.ok("a name the sign-in rules do not allow is refused", bad == 422)
    CHECKS.ok("the same name is refused", same == 422)
    CHECKS.ok("root does not rename itself", own == 409)
    row = await db.fetch_one("SELECT user_id, email, display_name FROM principals WHERE token='emp-park'")
    CHECKS.ok("an account with a real address and name keeps both", mailed == 200 and row == {"user_id": "park2", "email": "park@corp.example", "display_name": "박지민"})
    with as_user(ADMIN1):
        code = await status_of(service.rename_account("kim", service.AccountRename(user_id="kim2"), "Bearer x"))
    CHECKS.ok("an administrator other than root cannot rename another administrator", code == 403)


async def own_password():
    current, other = uuid.uuid4(), uuid.uuid4()
    for jti in (current, other):
        await db.execute("INSERT INTO console_sessions(jti, user_id, expires_at) VALUES (%s,'root',now()+interval '1 hour')", (jti,))
    with as_user(ROOT), patch.object(service, "authenticate", return_value=(None, {"jti": str(current)})):
        wrong = await status_of(service.change_own_password(service.PasswordChange(current_password="nope", new_password="root-new-pass1"), "Bearer x"))
        unchanged = await status_of(service.change_own_password(service.PasswordChange(current_password="root-pass1", new_password="root-pass1"), "Bearer x"))
        changed = await status_of(service.change_own_password(service.PasswordChange(current_password="root-pass1", new_password="root-new-pass1"), "Bearer x"))
    CHECKS.ok("a wrong current password is refused", wrong == 403)
    CHECKS.ok("the same password is refused", unchanged == 422)
    CHECKS.ok("root changes its own password", changed == 200 and await signs_in("root", "root-new-pass1") and not await signs_in("root", "root-pass1"))
    left = {r["jti"] for r in await db.fetch_all("SELECT jti FROM console_sessions WHERE user_id='root'")}
    CHECKS.ok("this session stays and the other console session ends", left == {current})


async def restart_keeps_renamed_defaults():
    # The field defaults are inserted at every start by token; a renamed default must not come back as a new account.
    with patch.dict(os.environ, {"MCP_FIELD_MODE": "1"}):
        await service.bootstrap_field_accounts()
    rows = await db.fetch_all("SELECT token, user_id FROM principals WHERE token IN ('admin2','admin1')")
    CHECKS.ok("a restart does not recreate the renamed default", {r["token"]: r["user_id"] for r in rows}.get("admin2") == "kim"
              and not await db.fetch_one("SELECT 1 FROM principals WHERE user_id='admin2'"))


async def main():
    signing_keys()
    os.environ["AUTH_PROVIDER"] = "local"
    await apply_schema()
    for token, user_id, email, role, password in (
            ("root", "root", "root", "admin", "root-pass1"), ("admin1", "admin1", "admin1", "admin", "admin1-pass1"),
            ("admin2", "admin2", "admin2", "admin", "admin2-pass1"), ("emp-lee", "lee", "lee", "employee", "lee-pass1"),
            ("emp-park", "park", "park@corp.example", "employee", "park-pass1")):
        await account(token, user_id, email, role, password)
    await db.execute("UPDATE principals SET display_name='박지민' WHERE token='emp-park'")
    for case in (reset_rules, reset_ends_sessions, rename_rules, own_password, restart_keeps_renamed_defaults):
        await CHECKS.case(case.__name__, case())
    return CHECKS.finish()


if __name__ == "__main__":
    run(main)
