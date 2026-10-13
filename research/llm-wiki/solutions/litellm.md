# LiteLLM — MCP 서버 범위가 넓어지지 않는 인가 처리

확인일: 2026-10-13 · 확인 수준: 고정 커밋 Python 코드 검토 · 라이선스: 분석·발췌한 범위 MIT, `enterprise/`는 별도 상용 라이선스.

[검토 커밋](https://github.com/BerriAI/litellm/tree/f8e456d105af921213267d0ef801ca08b8fdbc0b): `f8e456d105af921213267d0ef801ca08b8fdbc0b`. [pyproject.toml:1–3](https://github.com/BerriAI/litellm/blob/f8e456d105af921213267d0ef801ca08b8fdbc0b/pyproject.toml#L1-L3)의 버전은 1.102.0이다. 기존 분석의 1.89.4 및 1.104.0 결과를 이 버전의 결과로 합치지 않는다.

## 코드로 확인한 사실

[server.py:1521–1574](https://github.com/BerriAI/litellm/blob/f8e456d105af921213267d0ef801ca08b8fdbc0b/litellm/proxy/_experimental/mcp_server/server.py#L1521-L1574)는 호출자가 MCP 서버 이름을 명시했는데 alias·access group이 하나도 일치하지 않으면 빈 목록을 반환한다. 범위를 지정하지 않은 경우만 전체 허용 서버 목록을 반환한다. `/mcp/<unknown>/` 같은 입력이 넓은 허용 범위로 떨어지는 문제를 비교 실험에 사용할 수 있다.

[mcp_server_manager.py:3175–3202](https://github.com/BerriAI/litellm/blob/f8e456d105af921213267d0ef801ca08b8fdbc0b/litellm/proxy/_experimental/mcp_server/mcp_server_manager.py#L3175-L3202)는 명시적으로 범위가 지정된 자격과 사용자 세션을 구분하고, 세션의 resource scope를 상한으로 취급한다. [3210–3255](https://github.com/BerriAI/litellm/blob/f8e456d105af921213267d0ef801ca08b8fdbc0b/litellm/proxy/_experimental/mcp_server/mcp_server_manager.py#L3210-L3255)는 `no_mcp_servers`와 명시 서버 범위를 확인한 뒤 submitted server 합집합을 제한한다.

## 채택 판단

우리 Gateway의 서버별 URL·등록 주체·공급자 자격 binding에서 이름 미일치·빈 범위·미등록 별칭을 회귀 입력으로 추가할 가치가 있다. 이름 조회 실패가 aggregate endpoint로 흘러가 허용 범위가 넓어지면 실패다. 현재 우리 구현에 기능이 빠졌다고 단정하지 않고 `main.py`·`mcp_facade.py`·registry validation과 대조한다.

LLM 모델 호출·예산 통제와 MCP 도구의 부수효과 통제는 구분한다. LiteLLM이 이미 MCP 인가도 제공하므로 “LLM 프록시는 MCP를 통제하지 못한다”라는 일반화를 쓰지 않는다. 새로운 dashboard·BYOM 흐름 전체를 복제하지 않는다.

## 확보 증거와 한계

[서버 범위 발췌](evidence/litellm/litellm__proxy___experimental__mcp_server__server.py.excerpt.txt), [권한 resolver 발췌](evidence/litellm/litellm__proxy___experimental__mcp_server__mcp_server_manager.py.excerpt.txt), [버전 발췌](evidence/litellm/pyproject.toml.excerpt.txt), [라이선스](evidence/litellm/LICENSE.txt), [해시 목록](evidence/manifest.json).

권한 resolver의 전체 호출 경로·오류 fallback·가드레일·부하·토큰 회수는 실행하지 않았다. Enterprise 코드나 UI 라이선스를 MIT로 확대 해석하지 않는다. 이 분석은 현재 배포된 LiteLLM의 버전·설정을 확인한 결과가 아니다.
