#!/usr/bin/env python3
"""Korean PII and credential coverage of the Gateway's output masking, measured on synthetic samples.

Run inside the gateway image next to the two Presidio services of the stack (disposable copies are fine):

    docker run --rm --network <net> -e PRESIDIO_ANALYZER_URL=http://<analyzer>:3000 \
      -e PRESIDIO_ANONYMIZER_URL=http://<anonymizer>:3000 -v "$PWD/gateway/app:/app/app:ro" \
      -v "$PWD/tests:/tests:ro" -w /app <gateway-image> python /tests/korean_pii_eval.py [--json out.json]

Every identifier here is synthetic and cannot belong to a person: resident numbers carry birth years
2097-2099 (or the 1800s marker), phone numbers use the unassigned 0000 block, account, passport and licence
numbers are random digits behind a label, cards are the payment providers' published test numbers. They are
generated, never collected, and they are not a public corpus. The checksum-valid forms are built with the
public checksum algorithms (resident number, business registration number, Luhn).

For each positive sample the check is on the masked output: the value, or any run of six digits taken from it,
must be gone. For each negative sample (order numbers, dates, versions, addresses, hashes) nothing may be masked.
It reports the Presidio masking path (privacy.mask_text with the ad-hoc recognizers) and, for credentials, the
native Gitleaks library (secret_scan.labels), plus the outbound DLP labels (classify.dlp_scan).
Exit 1 when the analyzer or anonymizer cannot be reached (a masking path that cannot run is a failure).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
import string
import sys
import time
from collections import defaultdict

sys.path.append("/app")
from app import classify, privacy, secret_scan  # noqa: E402

RNG = random.Random(15)
DIGITS = string.digits


def digits(n: int) -> str:
    return "".join(RNG.choice(DIGITS) for _ in range(n))


def rrn(year: str, gender: str, valid: bool = True) -> str:
    body = f"{year}{RNG.randint(1, 12):02d}{RNG.randint(1, 28):02d}{gender}{digits(5)}"
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    check = (11 - sum(int(d) * w for d, w in zip(body, weights)) % 11) % 10
    return body + str(check if valid else (check + 1) % 10)


def brn() -> str:
    body = digits(9)
    weights = [1, 3, 7, 1, 3, 7, 1, 3, 5]
    total = sum(int(d) * w for d, w in zip(body, weights)) + int(body[8]) * 5 // 10
    return body + str((10 - total % 10) % 10)


def luhn_ok(number: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(number)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def secret(n: int, alphabet: str = string.ascii_letters + string.digits) -> str:
    return "".join(RNG.choice(alphabet) for _ in range(n))


def hyphen(number: str, cuts: tuple[int, ...]) -> str:
    parts, last = [], 0
    for cut in cuts:
        parts.append(number[last:cut])
        last = cut
    return "-".join(parts + [number[last:]])


# context templates: {v} is the value; "attached" ones glue Korean particles to it, as the language does
CONTEXTS = {
    "korean-spaced": "{label}: {v}",
    "korean-particle": "{label}는 {v}입니다. 확인 부탁드립니다.",
    "korean-attached": "{label}는{v}이며 정확합니다.",
    "korean-parenthesis": "홍길동({label} {v}) 고객님의 요청을 접수했습니다.",
    "json": '{{"name": "홍길동", "{key}": "{v}", "status": "active"}}',
    "log": "2026-10-15 09:12:03 INFO 조회 완료 {key}={v} result=ok",
    "english": "Customer {english}: {v}. Please confirm.",
    "mixed": "Contact 담당자 {v} 로 문의 바랍니다.",
}


# A number with no shape of its own (business registration, account, passport) or a password is masked behind its
# label only, so the free-standing "mixed" sentence is not a case for those; "label word then value" is.
LABELLED = [name for name in CONTEXTS if name != "mixed"]
LABELLED_STRICT = [name for name in LABELLED if name != "korean-parenthesis"]


def positives() -> list[dict]:
    out = []

    def add(category: str, label: str, key: str, english: str, values: list[str], expected: set[str], contexts=None):
        for value in values:
            for name in contexts or CONTEXTS:
                text = CONTEXTS[name].format(label=label, key=key, english=english, v=value)
                out.append({"category": category, "context": name, "text": text, "value": value, "expect": sorted(expected)})

    fake_years = ["97", "98", "99"]
    resident = [hyphen(rrn(year, gender), (6,)) for year in fake_years for gender in ("3", "4")]
    add("resident-number", "주민등록번호", "rrn", "resident number", resident, {"KR_RRN"})
    add("resident-number-nohyphen", "주민번호", "rrn", "resident number", [rrn(year, "3") for year in fake_years], {"KR_RRN"})
    add("foreigner-registration-number", "외국인등록번호", "alien_no", "alien registration number",
        [hyphen(rrn("98", g), (6,)) for g in ("5", "6", "7", "8")], {"KR_RRN"})
    add("resident-number-invalid-checksum", "주민번호", "rrn", "resident number",
        [hyphen(rrn("98", "3", valid=False), (6,))], {"KR_RRN"}, ["korean-spaced", "korean-attached", "json"])

    mobiles = ["010-0000-" + digits(4), "010" + "0000" + digits(4), "010 0000 " + digits(4), "010.0000." + digits(4),
               "+82 10-0000-" + digits(4), "+82-10-0000-" + digits(4), "82 10 0000 " + digits(4), "(010) 0000-" + digits(4),
               "011-000-" + digits(4), "010-0000-" + digits(4)]
    add("mobile-number", "연락처", "phone", "phone", mobiles, {"KR_PHONE"})
    landlines = ["02-0000-" + digits(4), "02-000-" + digits(4), "031-000-" + digits(4), "051-0000-" + digits(4),
                 "070-0000-" + digits(4), "+82-2-0000-" + digits(4), "02)0000-" + digits(4)]
    add("landline-number", "전화번호", "tel", "phone", landlines, {"KR_PHONE"})

    add("business-registration-number", "사업자등록번호", "biz_no", "business registration number",
        [hyphen(brn(), (3, 5)) for _ in range(3)] + [brn()], {"KR_BRN"}, LABELLED)
    banks = ["국민은행", "신한은행", "우리은행", "하나은행", "농협", "카카오뱅크"]
    accounts = [hyphen(digits(12), (6, 8)), hyphen(digits(12), (3, 6)), hyphen(digits(13), (4, 7)), hyphen(digits(14), (3, 7, 11))]
    add("bank-account", "계좌번호", "account", "bank account", accounts, {"KR_ACCOUNT"}, LABELLED)
    for bank, number in zip(banks, accounts * 2):
        for name in ("korean-spaced", "korean-particle"):
            out.append({"category": "bank-account-bank-name", "context": name, "value": number, "expect": ["KR_ACCOUNT"],
                        "text": CONTEXTS[name].format(label=bank + " 계좌", key="account", english="account", v=number)})
    passports = ["M" + digits(8), "M" + digits(3) + "A" + digits(4), "S" + digits(8), "M" + digits(3) + "B" + digits(4)]
    add("passport-number", "여권번호", "passport_no", "passport number", passports, {"KR_PASSPORT"}, LABELLED)
    add("driver-license-number", "운전면허번호", "license_no", "driver license number",
        [f"{RNG.randint(11, 28)}-{RNG.randint(10, 99)}-{digits(6)}-{digits(2)}" for _ in range(3)], {"KR_DRIVER_LICENSE"})
    cards = [c for c in ("4242424242424242", "4111111111111111", "5555555555554444", "378282246310005") if luhn_ok(c)]
    add("card-number", "카드번호", "card", "card number", [hyphen(c, (4, 8, 12)) if len(c) == 16 else c for c in cards], {"CREDIT_CARD", "CARD_NUMBER"},
        ["korean-spaced", "korean-particle", "json", "english"])
    emails = ["gildong.hong@example.co.kr", "kim_cs+test@bob.local", "park@sub.example.com"]
    add("email", "이메일", "email", "email", emails, {"EMAIL_ADDRESS"})
    out += [{"category": "email-attached", "context": "attached", "value": e, "expect": ["EMAIL_ADDRESS"], "text": f"담당자메일{e}로 보내 주세요."} for e in emails]

    passwords = [secret(10) + "!", "Pw" + secret(9), "hunter2" + secret(6), secret(8, string.ascii_lowercase + string.digits)]
    add("password-korean-label", "비밀번호", "password", "password", passwords, {"CREDENTIAL"}, LABELLED_STRICT)
    for label in ("패스워드", "암호", "비번"):
        out += [{"category": "password-korean-label", "context": label, "value": passwords[0], "expect": ["CREDENTIAL"],
                 "text": f"{label}: {passwords[0]}"}]
    out += [{"category": "password-english-label", "context": c, "value": passwords[1], "expect": ["CREDENTIAL"],
             "text": c.format(v=passwords[1])} for c in ("password: {v}", "PASSWORD={v}", "password = {v} (임시)", "DB_PASSWORD={v}",
                                                         "MYSQL_ROOT_PASSWORD: {v}", "passwd={v}", "비밀번호 password={v}입니다", "pwd: {v}")]
    keys = ["sk-" + secret(40, string.ascii_letters + string.digits + "_-"), "AKIA" + secret(16, string.ascii_uppercase + string.digits),
            "ghp_" + secret(36), "xoxb-" + digits(12) + "-" + digits(13) + "-" + secret(24), "AIza" + secret(35, string.ascii_letters + string.digits + "-_"),
            "sk_live_" + secret(24)]
    for key in keys:
        for name in ("korean-spaced", "korean-particle", "korean-attached", "json", "log"):
            out.append({"category": "vendor-token", "context": name, "value": key, "expect": ["SECRET_TOKEN"],
                        "text": CONTEXTS[name].format(label="API 키", key="api_key", english="API key", v=key)})
    generic = secret(32)
    out += [{"category": "api-key-assignment", "context": c, "value": generic, "expect": ["CREDENTIAL", "SECRET_TOKEN"], "text": c.format(v=generic)}
            for c in ("api_key: {v}", "API_KEY={v}", "STRIPE_API_KEY={v}", "client_secret = {v}", "access_token: {v}", "인증키: {v}",
                      "API 키: {v}", "시크릿 키는 {v} 입니다", "토큰: {v}")]
    return out


NEGATIVES = [
    "주문번호 20261015-0001234 건이 출고되었습니다.", "송장번호 123456789012 배송 중입니다.", "주문번호: 2610151234567",
    "회의는 2026-10-15 오후 2시입니다.", "2026.10.15 09:30 접수", "버전 v2026.10.15 배포 완료", "version 1.2.3 released",
    "서버 192.168.10.25 포트 8080 에서 응답합니다.", "커밋 9f1c2b7e4d5a6b8c0d1e2f3a4b5c6d7e8f9a0b1c 병합",
    "UUID 3f2504e0-4f89-11d3-9a0c-0305e82c3301 발급", "금액 1,234,567원 입금 확인", "우편번호 06236", "ISBN 978-89-6848-123-4",
    "SKU-010-1234-5678 재고 12개", "모델명 SM-G991N 256GB", "사원번호 20240123 홍길동 대리", "문서번호 2026-자원-0412호",
    "총 13자리 숫자 1234567890123 는 일련번호입니다.", "ID 99123 접수번호 A12345678 확인", "회원번호 M12345678 로 조회",
    "시험 점수 80-90-100 구간", "경도 127.0276, 위도 37.4979", "RGB 255-255-255", "Build #4096 passed in 12.5s",
    "전화 연결 시간 02:30:15", "SSH 키 지문 SHA256:abcDEF1234567890abcDEF1234567890abcDEF12345", "비밀번호는 90일마다 변경해야 합니다.",
    "비밀번호를 입력하세요", "password policy requires 12 characters", "토큰 만료 시간은 30분입니다.", "API 키 발급 절차를 안내합니다.",
    "token: ", "secret: true", "계좌 개설일 2026-10-15 확인", "account created 2026-10-15 by admin", "날짜 02-12-2026 접수",
    "비밀번호는 영문과숫자를조합해야 합니다.", "계좌번호를 알려 주시면 환불해 드립니다.", "여권번호는 필수 입력 항목입니다.", "사업자등록번호 확인 방법 안내",
    "주민등록번호 수집은 법령에 근거한 경우에만 가능합니다.", "연락처를 남겨 주세요 (예: 010-xxxx-xxxx)",
    "이메일 주소 형식은 name@domain 입니다.", "CPU 사용률 82% 메모리 6.1GB", "합계 3-5-12000 분류코드", "도로명 주소: 서울특별시 강남구 테헤란로 123",
]


TIMES: list[float] = []


async def mask(text: str) -> tuple[str, list[str], str]:
    started = time.perf_counter()
    try:
        masked, kinds = await privacy.mask_text(text)
        return masked, kinds, ""
    except privacy.InspectionUnavailable as exc:
        return text, [], str(exc)
    finally:
        TIMES.append((time.perf_counter() - started) * 1000)


# 100 KB of text built to make a backtracking pattern slow: long identifiers, digit runs, repeated labels.
STRESS = {
    "digits": "1" * 100_000, "phone-prefix": "010-" * 25_000, "snake-case": "a_b_" * 25_000, "label-repeat": "비밀번호는 " * 12_000,
    "account-label": "계좌 1" * 20_000, "dashes": "-" * 100_000, "hangul": "가나다라마바사 " * 14_000, "mixed-ids": "ID-0123456789-abc " * 6_000,
    "password-words": "password " * 11_000, "plus82": "+82 " * 25_000, "at-signs": "a@" * 50_000, "equals": "key=" * 25_000,
}


def leaked(value: str, masked: str) -> bool:
    if value in masked:
        return True
    runs = re.findall(r"\d{6,}", value)
    return any(run in masked for run in runs) or (not runs and len(value) >= 8 and value[:8] in masked)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    parser.add_argument("--misses", type=int, default=0, help="print up to N unmasked samples per category")
    args = parser.parse_args()
    samples = positives()
    result: dict = defaultdict(lambda: {"n": 0, "masked": 0, "entity": 0, "dlp": 0, "gitleaks": 0, "misses": []})
    unavailable = 0
    for sample in samples:
        masked, kinds, error = await mask(sample["text"])
        unavailable += bool(error)
        cell = result[sample["category"]]
        cell["n"] += 1
        ok = not leaked(sample["value"], masked) and not error
        cell["masked"] += ok
        cell["entity"] += bool(set(kinds) & set(sample["expect"]))
        cell["dlp"] += bool(classify.dlp_scan(sample["text"]))
        try:
            cell["gitleaks"] += bool(await secret_scan.labels(sample["text"]))
        except privacy.InspectionUnavailable:
            unavailable += 1
        if not ok and len(cell["misses"]) < 6:
            cell["misses"].append({"context": sample["context"], "text": sample["text"][:100], "masked": masked[:100]})
    negatives = {"n": len(NEGATIVES), "masked": [], "dlp": [], "gitleaks": []}
    for text in NEGATIVES:
        masked, kinds, error = await mask(text)
        unavailable += bool(error)
        if masked != text:
            negatives["masked"].append({"text": text, "kinds": kinds})
        if classify.dlp_scan(text):
            negatives["dlp"].append({"text": text, "labels": classify.dlp_scan(text)})
        if await secret_scan.labels(text):
            negatives["gitleaks"].append(text)
    stress = {}
    for name, text in STRESS.items():
        started = time.perf_counter()
        _, _, error = await mask(text)
        stress[name] = {"seconds": round(time.perf_counter() - started, 2), "error": error[:60]}
        unavailable += bool(error)
    print(f"{'category':36}{'n':>4}{'masked':>8}{'entity':>8}{'dlp':>6}{'gitleaks':>9}")
    for name, cell in result.items():
        print(f"{name:36}{cell['n']:4}{cell['masked']:8}{cell['entity']:8}{cell['dlp']:6}{cell['gitleaks']:9}")
    if args.misses:
        for name, cell in result.items():
            for miss in cell["misses"][:args.misses]:
                print(f"   miss {name} [{miss['context']}] {miss['text']!r} -> {miss['masked']!r}")
    print(f"negatives {negatives['n']}: masked {len(negatives['masked'])}, dlp {len(negatives['dlp'])}, gitleaks {len(negatives['gitleaks'])}")
    for item in negatives["masked"]:
        print("   masked:", item)
    for item in negatives["dlp"]:
        print("   dlp:", item)
    print("mask_text per sample (ms): median", round(statistics.median(TIMES), 1), "p95", round(sorted(TIMES)[int(len(TIMES) * .95)], 1))
    print("100 KB stress (s):", {k: v["seconds"] if not v["error"] else "UNAVAILABLE" for k, v in stress.items()})
    print("inspection unavailable:", unavailable)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as stream:
            json.dump({"positives": result, "negatives": negatives, "stress": stress, "unavailable": unavailable}, stream, ensure_ascii=False, indent=1)
    return 1 if unavailable else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
