"""도구 범위의 외부 전송 등급 기본값과 PAC-12 차단 사유.

PAC-12는 목적지·등급 짝이 정확히 맞아야 통과한다. 「내부」 서버를 「공개」로 심사하면 승인한 목적지로 가는
호출이 모두 막혔고(10-27 MarkItDown 실측), 차단 사유는 정책 번호뿐이었다.
"""
from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "gateway/app"


def functions(path: Path, names: set[str]) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
            or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in names)]
    scope: dict = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), scope)
    return scope


spec = importlib.util.spec_from_file_location("intake_proposal", APP / "intake_proposal.py")
intake_proposal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake_proposal)
gap = functions(APP / "pac.py", {"GRADE_LABELS", "transfer_gap"})["transfer_gap"]


def pac_input(grade="nonimportant", pairs=(("docs.example", "public"),), verified=True, destination="docs.example"):
    return {"request": {"transfer": {"enabled": True, "destination_id": destination}},
            "facts": {"transfer": {"verified": verified, "final_destination_id": destination, "data_grade": grade},
                      "approval": {"transfer_pairs": [{"destination_id": d, "grade": g} for d, g in pairs]}}}


class ProposalGrade(unittest.TestCase):
    tools = [{"name": "convert", "input_schema": {"properties": {"uri": {"type": "string"}}}}]

    def grade(self, data_class):
        row = {"purpose": "문서 변환", "display_name": "변환기", "intake_kind": "repository", "data_class": data_class}
        return intake_proposal.tool_reviews(row, self.tools, {"convert"})["convert"]["grade"]

    def test_transfer_grade_follows_request_data_grade(self):
        self.assertEqual(self.grade("nonimportant"), "nonimportant")
        self.assertEqual(self.grade("public"), "public")

    def test_important_and_missing_stay_public(self):
        # ToolReview admits only public·nonimportant; 「중요」 never leaves (GRADES_UP_TO has no entry).
        self.assertEqual(self.grade("important"), "public")
        self.assertEqual(self.grade(None), "public")


class Pac12Reason(unittest.TestCase):
    def test_grade_mismatch_names_the_grade_to_approve(self):
        text = gap(pac_input())
        self.assertIn("「내부」의 외부 전송이 승인되지 않았습니다", text)
        self.assertIn("외부 전송 등급을 「내부」로 승인", text)

    def test_reason_never_lists_approved_destinations(self):
        text = gap(pac_input(pairs=(("approved-secret.example", "public"),), destination="other.example"))
        self.assertNotIn("approved-secret.example", text)

    def test_each_gap_kind(self):
        self.assertIn("하나로 확인할 수 없습니다", gap(pac_input(destination="")))
        self.assertIn("승인되지 않았습니다", gap(pac_input(pairs=())))
        self.assertIn("허용 목록이 이 도구의 승인 목적지보다 넓어", gap(pac_input(verified=False)))
        # 10-27 실측: 원격 제공자(AWS Knowledge)는 실행기 출구 프록시가 없어 최종 목적지를 확인할 수 없다(D-132).
        self.assertIn("최종 접속 목적지를 게이트웨이가 확인할 수 없어", gap(pac_input(verified=False), runtime=False))
        self.assertIn("「중요」 등급 데이터는 외부로 보낼 수 없습니다", gap(pac_input(grade="important")))

    def test_no_reason_when_transfer_is_off_or_pair_matches(self):
        off = pac_input()
        off["request"]["transfer"]["enabled"] = False
        self.assertEqual(gap(off), "")
        self.assertEqual(gap(pac_input(pairs=(("docs.example", "public"), ("docs.example", "nonimportant")))), "")


class Wiring(unittest.TestCase):
    def test_core_appends_pac12_reason_and_console_defaults_grade(self):
        core = (APP / "core.py").read_text(encoding="utf-8")
        self.assertIn('result["policy_id"] == "PAC-12"', core)
        self.assertIn('pac.transfer_gap(policy_input["pac"], bool((registry.server(cls.server)', core)
        console = (APP / "agent_static/console.js").read_text(encoding="utf-8")
        self.assertIn('dataClass === "nonimportant" ? "nonimportant" : "public"', console)
        self.assertIn("scopeFields(pending, registration.data_class)", console)


if __name__ == "__main__":
    unittest.main()
