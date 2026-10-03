"""Installed engines and configured capabilities, without conflating health and scope."""
import asyncio
import importlib.metadata
import shutil

from fastapi import APIRouter, Header

from .oidc import administrator, configured, settings

router = APIRouter()


@router.get("/api/components")
async def components(authorization: str | None = Header(default=None)):
    await administrator(authorization)
    binary = shutil.which("gitleaks")
    scanner_version = None
    if binary:
        process = await asyncio.create_subprocess_exec(binary, "version", stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.DEVNULL)
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), 3)
            if process.returncode == 0:
                scanner_version = stdout.decode().strip()[:50]
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
    sso = settings()
    return {"components": [
        {"name": "Keycloak / OIDC", "version": None,
         "state": "설정·활성" if sso["provider"] == "oidc" and configured() else "설정·전환 대기" if configured() else "미설정",
         "function": "조직 로그인", "scope": "관리자가 연결한 issuer/sub만 사용. 역할·단말 활성화는 조직 관리대장."},
        {"name": "Authlib", "version": importlib.metadata.version("Authlib"), "state": "설치됨",
         "function": "OIDC 프로토콜", "scope": "Code + PKCE, state·nonce·서명·issuer·audience 검증"},
        {"name": "Gitleaks", "version": scanner_version, "state": "Console 이미지 실행 확인" if scanner_version else "실행 미확인",
         "function": "Secret 검사", "scope": "도입 저장소·전송 인자·마스킹 후 응답 검사. 실패 시 검증 실패/차단/응답 보류. 기존 보수적 패턴 병행."},
        {"name": "OPA/Rego", "state": "구성됨", "function": "실행 전 인가", "scope": "Gateway 경유 호출. 실제 연결 상태는 배포 확인."},
        {"name": "Presidio", "state": "구성됨", "function": "개인정보 검사·마스킹", "scope": "요청과 응답. 처리 실패 시 차단/응답 보류."},
        {"name": "Syft · Trivy · Semgrep", "state": "구성됨", "function": "도입 검증", "scope": "격리 워커의 저장소 검사. 실행 여부와 버전은 각 검증 보고서."},
        {"name": "OpenTelemetry · Jaeger", "state": "구성됨", "function": "호출 추적", "scope": "성능·경로 분석. 공식 감사 증거는 PostgreSQL 원장."},
        {"name": "Audit API", "version": "v1", "state": "구현됨", "function": "감사 조회·내보내기·검증",
         "scope": "관리자 전용, 원문/토큰 제외. 내보내기는 조회 페이지이며 전체 원장은 별도 검증."},
    ]}
