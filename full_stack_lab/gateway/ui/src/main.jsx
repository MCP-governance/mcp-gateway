import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const decisionMeta = {
  Allow: { icon: '✓', label: '허용', tone: 'allow' },
  Alert: { icon: '!', label: '허용 + 경보', tone: 'alert' },
  Approval: { icon: '⌛', label: '승인 대기', tone: 'approval' },
  Restrict: { icon: '↘', label: '제한 후 실행', tone: 'restrict' },
  Block: { icon: '×', label: '차단', tone: 'block' },
}

// The dashboard no longer holds a list of principal tokens. It signs in as a
// synthetic account and sends that account's token, exactly like every other client.
const accounts = [
  { email: 'customer@bob.local', role: 'customer', name: '고객 김민수', mark: '고' },
  { email: 'miso@bob.local', role: 'employee', name: '김미소', mark: '직' },
  { email: 'admin@bob.local', role: 'admin', name: '관리자 박지훈', mark: '관' },
]

const scenarios = [
  { name: '공개 문서 허용', email: 'customer@bob.local', message: '공개 공지를 읽어줘' },
  { name: '중요 열람 경보', email: 'miso@bob.local', message: '중요 계약 초안을 읽어줘' },
  { name: '외부 전송 제한', email: 'admin@bob.local', message: '공개 공지를 외부로 보내줘' },
  { name: '중요 전송 승인', email: 'admin@bob.local', message: '중요 계약을 외부로 전송해줘' },
  { name: '권한 부족 차단', email: 'customer@bob.local', message: '중요 계약을 읽어줘' },
]

async function api(path, options = {}, token) {
  const headers = { ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(path, { ...options, headers })
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`)
  return body
}

function StatusDot({ ok, pending = false }) {
  return <span className={`status-dot ${pending ? 'pending' : ok ? 'ok' : 'bad'}`} aria-hidden="true" />
}

function DecisionBadge({ decision }) {
  const meta = decisionMeta[decision] || decisionMeta.Block
  return <span className={`decision-badge ${meta.tone}`}><b>{meta.icon}</b>{meta.label}</span>
}

const processSteps = [
  ['01', '사용자 요청', '역할 · 업무 문장'],
  ['02', 'Agent 위임', 'JWT · 짧은 위임 증명'],
  ['03', 'Gateway 검증', '신원 · 계약 · 입력'],
  ['04', 'OPA 정책', '333 권한 판정'],
  ['05', '승인 · 제한', '고위험 실행 조건'],
  ['06', 'MCP 실행 · 증적', 'Effect · Trace 기록'],
]

function processStepState(index, current) {
  if (!current) return 'ready'
  if (index < 3) return 'passed'
  if (current.decision === 'Block') return index === 3 ? 'blocked' : 'not-reached'
  if (current.decision === 'Approval') return index < 5 ? 'pending' : 'not-reached'
  if (index === 4 && current.decision === 'Restrict') return 'restricted'
  return 'passed'
}

function ProcessMap({ current }) {
  const labels = {
    ready: '준비',
    passed: '통과',
    blocked: '차단',
    pending: '승인 대기',
    restricted: '제한 실행',
    'not-reached': '미진입',
  }
  const summary = !current
    ? '요청을 실행하면 이 경로에서 멈춘 지점과 실제 MCP 전달 여부를 강조합니다.'
    : current.decision === 'Block'
      ? '"' + current.policy_id + '"에서 차단됐습니다. MCP 서버에는 전달되지 않았습니다.'
      : current.decision === 'Approval'
        ? '승인 재검증 전까지 MCP 실행을 보류합니다.'
        : current.upstream_executed
          ? '정책을 통과했고, 독립 효과 로그에서 MCP 실행을 대조합니다.'
          : '실행 결과를 확인 중입니다.'

  return <div className="process-map">
    <ol className="process-track" aria-label="요청 처리와 차단 지점">
      {processSteps.map(([number, title, detail], index) => {
        const state = processStepState(index, current)
        return <li className={'process-step ' + state} key={title}>
          <div className="process-card">
            <span className="process-number">{number}</span>
            <b>{title}</b>
            <small>{detail}</small>
            <span className="process-state">{labels[state]}</span>
          </div>
          {index < processSteps.length - 1 && <span className="process-connector" aria-hidden="true">→</span>}
        </li>
      })}
    </ol>
    <p className={'process-summary ' + (current?.decision || 'ready')} role="status">{summary}</p>
  </div>
}

function ProjectGuide() {
  return <>
    <header className="guide-header">
      <div className="topbar">
        <a className="brand" href="#top" aria-label="대시보드로 돌아가기">
          <span className="brand-mark">M</span>
          <span><b>MCP Governance</b><small>Security Gateway Lab</small></span>
        </a>
        <nav aria-label="프로젝트 안내 탐색">
          <a href="#top">대시보드</a>
          <a href="#guide" aria-current="page">프로젝트 안내</a>
          <a href="http://localhost:8000" target="_blank" rel="noreferrer">업무 공간 ↗</a>
        </nav>
      </div>
    </header>

    <main className="guide-main" id="guide">
      <section className="guide-hero">
        <p className="kicker">PROJECT GUIDE</p>
        <h1>모델의 제안과 실제 실행을<br />서로 다른 경계로 분리합니다.</h1>
        <p>이 페이지는 실습의 구조와 도입 이유를 설명합니다. 실시간 상태, 정책 시험과 증적 조회는 <a href="#top">대시보드</a>에서 확인합니다.</p>
        <a className="primary-link" href="#top">대시보드로 돌아가기 <span>→</span></a>
      </section>

      <section className="guide-section" aria-labelledby="guide-flow-title">
        <div className="section-heading">
          <div><p className="kicker">CONTROL PATH</p><h2 id="guide-flow-title">누가 실행 권한을 결정하는가</h2><p>Agent와 모델은 요청을 제안하고, Gateway와 OPA/Rego가 실행 여부를 결정합니다.</p></div>
        </div>
        <ol className="guide-path">
          <li><span>01</span><div><b>사용자 · Agent Service</b><small>사용자 JWT와 짧은 Agent 위임 증명을 요청에 결속합니다.</small></div></li>
          <li><span>02</span><div><b>Security Gateway</b><small>actor, agent, 요청 봉투와 승인된 계약을 검증합니다.</small></div></li>
          <li><span>03</span><div><b>OPA / Rego</b><small>역할·자료등급·행위를 정책으로 판정하고 기본값은 거부합니다.</small></div></li>
          <li><span>04</span><div><b>MCP Server · Evidence</b><small>허용된 호출만 전달하고, 실행 효과와 Trace를 별도로 대조합니다.</small></div></li>
        </ol>
      </section>

      <section className="guide-section" aria-labelledby="guide-tools-title">
        <div className="section-heading">
          <div><p className="kicker">WHY THESE TOOLS</p><h2 id="guide-tools-title">도입한 도구가 맡는 일</h2><p>도구마다 책임을 좁혀, 모델 또는 스캐너 결과가 실행 권한을 직접 갖지 않게 했습니다.</p></div>
        </div>
        <div className="tool-guide-grid">
          <article className="tool-guide">
            <p className="tool-label">MODEL PROPOSAL · container_lab</p>
            <h3>LiteLLM</h3>
            <p>서로 다른 모델 endpoint를 OpenAI 호환 호출로 중계해 도구 호출 제안을 한 경로에서 관찰합니다.</p>
            <ul><li>모델은 최대 한 개의 등록된 도구 호출만 제안합니다.</li><li>허용·차단은 LiteLLM이 아니라 Gateway와 OPA/Rego가 결정합니다.</li><li>원문 프롬프트·응답 대신 필요한 증적만 남기는 경계를 유지합니다.</li></ul>
          </article>
          <article className="tool-guide">
            <p className="tool-label">SUPPLY-CHAIN EVIDENCE · full_stack_lab</p>
            <h3>AI-Infra-Guard</h3>
            <p>전체 플랫폼을 이식하지 않고, 고정된 mcp-scan CLI의 SARIF 결과만 공급망 증적으로 연결합니다.</p>
            <ul><li>도구 메타데이터와 스캔 결과를 Registry 승인 상태와 함께 비교합니다.</li><li>기본 모의 모델 모드에는 외부 키가 필요 없고, mcp-scan은 provider 설정이 있을 때만 선택적으로 실행합니다.</li><li>스캔 결과는 실행 권한이 아니라 호출 전 검토에 쓰이는 증적입니다.</li></ul>
          </article>
        </div>
      </section>

      <section className="guide-section guide-boundary" aria-labelledby="guide-boundary-title">
        <div><p className="kicker">EVIDENCE BOUNDARY</p><h2 id="guide-boundary-title">이 실습이 보이는 것과 보이지 않는 것</h2></div>
        <ul>
          <li><b>보임</b><span>로그인, 위임 신원, 정책 판정, 실제 MCP 전달 여부, Trace와 독립 효과 로그</span></li>
          <li><b>별도 검증 필요</b><span>운영 SSO, 키 회전, SPIFFE, 외부 모델 실호출, 고가용성, egress 격리</span></li>
        </ul>
      </section>
    </main>
    <footer><span>MCP Governance Security Gateway · Synthetic Lab</span><span>대시보드와 프로젝트 안내를 분리해 제공합니다.</span></footer>
  </>
}

function App() {
  const [health, setHealth] = useState(null)
  const [state, setState] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [integration, setIntegration] = useState(null)
  const [monitor, setMonitor] = useState(null)
  const [email, setEmail] = useState('customer@bob.local')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('공개 공지를 읽어줘')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [view, setView] = useState(() => window.location.hash === '#guide' ? 'guide' : 'dashboard')

  useEffect(() => {
    const syncView = () => setView(window.location.hash === '#guide' ? 'guide' : 'dashboard')
    window.addEventListener('hashchange', syncView)
    return () => window.removeEventListener('hashchange', syncView)
  }, [])

  useEffect(() => {
    document.title = view === 'guide' ? '프로젝트 안내 | MCP Governance' : 'MCP Governance Dashboard'
  }, [view])

  const load = async () => {
    try {
      const [nextHealth, nextState, nextMatrix, nextIntegration, nextMonitor] = await Promise.all([
        api('/api/health'), api('/api/state'), api('/api/policy/matrix'), api('/api/integration'),
        api('/api/monitor/summary?hours=168'),
      ])
      setHealth(nextHealth)
      setState(nextState)
      setMatrix(nextMatrix)
      setIntegration(nextIntegration)
      setMonitor(nextMonitor)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 8000)
    return () => clearInterval(timer)
  }, [])

  // One short-lived token per synthetic account, minted on demand. An expired token
  // is dropped and re-minted rather than retried, so a stale tab cannot half-work.
  const tokens = useRef({})
  const tokenFor = async (account) => {
    if (!tokens.current[account]) {
      const body = await api('/api/session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: account, password }),
      })
      tokens.current[account] = body.access_token
    }
    return tokens.current[account]
  }
  const withToken = async (account, call) => {
    try {
      return await call(await tokenFor(account))
    } catch (err) {
      if (String(err.message).includes('401') || String(err.message).includes('인증')) tokens.current[account] = null
      throw err
    }
  }

  const run = async (event) => {
    event?.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await withToken(email, token => api('/api/mock-model', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      }, token))
      setResult(response)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const approve = async (id) => {
    setBusy(true)
    try {
      // Approval is an admin action, so it is signed by the admin account, not by
      // whoever happens to have the dashboard open.
      const response = await withToken('admin@bob.local', token => api(`/api/approvals/${id}/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
      }, token))
      setResult({ generator: 'approval-revalidation', generated_call: null, result: response })
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const refreshCatalog = async () => {
    setBusy(true)
    try { await withToken(email, token => api('/api/catalog/refresh', { method: 'POST' }, token)); await load() }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  // A reviewer needs a way to say no with a reason. "Let it expire" looks identical
  // to inattention in the audit log.
  const reject = async (id) => {
    const note = window.prompt('거부 사유를 입력하세요. 증적에 남습니다.')
    if (!note || !note.trim()) return
    setBusy(true)
    try {
      const response = await withToken('admin@bob.local', token => api(`/api/approvals/${id}/reject`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note }),
      }, token))
      setResult({ generator: 'approval-rejected', generated_call: null, result: { ...current, ...response, decision: 'Block', policy_id: 'P-X-APPROVAL-001', reason: `승인이 거부되었습니다: ${response.review_note}` } })
      await load()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  // Turning enforcement on is the decision this panel exists to support, so it is
  // signed by the admin account rather than by whoever has the dashboard open.
  const setEnforcement = async (mode) => {
    setBusy(true)
    try {
      await withToken('admin@bob.local', token => api('/api/enforcement', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      }, token))
      await load()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const importReports = async () => {
    setBusy(true)
    try { await withToken('admin@bob.local', token => api('/api/supply-chain/import', { method: 'POST' }, token)); await load() }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const current = result?.result
  const activeAccount = accounts.find(item => item.email === email)
  const activeUser = state?.principals?.find(item => item.role === (current?.role || activeAccount?.role))
  const cells = useMemo(() => {
    const index = {}
    for (const cell of matrix?.cells || []) index[`${cell.role}.${cell.data_class}.${cell.action}`] = cell
    return index
  }, [matrix])

  if (view === 'guide') return <ProjectGuide />

  return <>
    <header className="hero">
      <div className="topbar">
        <a className="brand" href="#top" aria-label="대시보드 맨 위로">
          <span className="brand-mark">M</span>
          <span><b>MCP Governance</b><small>Security Gateway Lab</small></span>
        </a>
        <nav aria-label="주요 화면">
          <a href="#top" aria-current="page">대시보드</a><a href="#practice">실습</a><a href="#audit">증적</a><a href="#guide">프로젝트 안내</a>
        </nav>
      </div>
      <div className="hero-copy" id="top">
        <div>
          <p className="eyebrow">GOVERNANCE DASHBOARD · LIVE DEMO</p>
          <h1>요청은 어디에서<br /><em>멈추고, 왜</em><br />실행되는가</h1>
          <p className="lede">사용자 요청부터 MCP 실행 증적까지 한 경로로 읽습니다. 차단·승인·제한은 아래 흐름에서 즉시 강조됩니다.</p>
        </div>
        <div className="hero-summary" aria-label="현재 핵심 상태">
          <div><span>정책 결과</span><strong>5종</strong><small>Allow · Alert · Approval · Restrict · Block</small></div>
          <div><span>권한 조합</span><strong>27칸</strong><small>3 역할 × 3 등급 × r/w/x</small></div>
          <div><span>실행 증적</span><strong>Trace + Effect</strong><small>판정과 실제 전달 여부를 대조</small></div>
        </div>
      </div>
    </header>

    <main>
      {error && <div className="error-banner" role="alert"><b>확인 필요</b><span>{error}</span><button onClick={() => setError('')} aria-label="오류 닫기">×</button></div>}

      <section className="section system-section" aria-labelledby="system-title">
        <div className="section-heading">
          <div><p className="kicker">한눈에 보는 구조</p><h2 id="system-title">요청에서 증적까지 한 방향으로 흐릅니다</h2></div>
          <span className={`overall ${health?.status || 'loading'}`}><StatusDot ok={health?.status === 'ok'} pending={!health} />{health ? (health.status === 'ok' ? '핵심 구성요소 정상' : '일부 구성요소 확인 필요') : '상태 확인 중'}</span>
        </div>
        <ProcessMap current={current} />
        <div className="health-grid">
          {[
            ['Gateway', health?.components?.gateway], ['OPA 정책', health?.components?.opa],
            ['PostgreSQL', health?.components?.postgresql], ['합성 MCP', health?.components?.mock_http_mcp],
            ['Jaeger', health?.components?.jaeger], ['GitHub MCP', health?.components?.github_mcp, true],
          ].map(([label, ok, optional]) => <div className="health-item" key={label}><StatusDot ok={ok} pending={optional && !ok} /><span><b>{label}</b><small>{optional && !ok ? '인증 대기 · 의도적 비활성' : ok ? '연결됨' : '확인 중'}</small></span></div>)}
        </div>
      </section>

      <section className="section" aria-labelledby="agent-title">
        <div className="section-heading"><div><p className="kicker">AGENT SERVICE · MISO 통합</p><h2 id="agent-title">로그인부터 실제 실행까지 이어집니다</h2><p>합성 로그인 → 사용자 JWT → 60초 Agent 위임 → 요청 바인딩 → 333 정책 → MCP 실행·감사</p></div><a className="secondary-link" href="http://localhost:8000" target="_blank" rel="noreferrer">사용자 업무 공간 열기 ↗</a></div>
        <div className="audit-summary"><div><span>시나리오 준비</span><b>{integration?.readiness?.status === 'ready' ? '준비됨' : '확인 필요'}</b></div><div><span>사용자 인증</span><b>합성 JWT · 30분</b></div><div><span>Agent 위임</span><b>별도 Assertion · 60초</b></div><div><span>요청 바인딩</span><b>actor · agent · SHA-256</b></div></div>
        <p>실제 API 연결 전에는 모의 모델을 사용합니다. 사용자 JWT만으로 내부 <code>/tool-call</code>을 실행할 수 없으며, 토큰·요청 해시 원문은 화면과 감사 로그에 표시하지 않습니다.</p>
        <details><summary>최근 Agent 요청과 세션 ID</summary><pre>{JSON.stringify(integration?.runs || [], null, 2)}</pre></details>
      </section>

      <section className="section" id="enforcement" aria-labelledby="enforcement-title">
        <div className="section-heading">
          <div>
            <p className="kicker">집행 단계</p>
            <h2 id="enforcement-title">관찰부터 시작하고, 숫자를 보고 켜세요</h2>
          </div>
          <span className="note-pill">{monitor?.enforcement === 'monitor' ? '관찰 모드' : '집행 모드'}</span>
        </div>
        <div className="panel">
          <p>
            {monitor?.enforcement === 'monitor'
              ? '권한 판정은 기록만 하고 실행합니다. Registry·catalog·공급망·정책엔진 장애는 관찰 모드에서도 그대로 차단합니다.'
              : '모든 판정을 그대로 집행합니다. 도입 초기에는 관찰 모드로 영향 범위를 먼저 측정할 수 있습니다.'}
          </p>
          <div className="result-facts">
            <div><span>최근 7일 차단됐을 호출</span><b>{monitor?.would_have_stopped ?? 0}건</b></div>
            <div><span>영향 받는 주체</span><b>{monitor?.affected_principals ?? 0}명</b></div>
          </div>
          {(monitor?.breakdown || []).length > 0 && <div className="audit-table-wrap" style={{ marginTop: 14 }}>
            <table className="audit-table">
              <thead><tr><th>집행 시 판정</th><th>정책</th><th>역할</th><th>도구</th><th>등급</th><th>건수</th></tr></thead>
              <tbody>{monitor.breakdown.slice(0, 8).map((row, index) => <tr key={index}>
                <td>{row.would_decision}</td><td><code>{row.would_policy_id}</code></td>
                <td>{row.role}</td><td>{row.tool_name}</td><td>{row.data_class}</td><td>{row.calls}</td>
              </tr>)}</tbody>
            </table>
          </div>}
          <button type="button" className="primary-button" style={{ marginTop: 16 }} disabled={busy || !password}
                  onClick={() => setEnforcement(monitor?.enforcement === 'monitor' ? 'enforce' : 'monitor')}>
            {monitor?.enforcement === 'monitor' ? '집행 모드로 전환' : '관찰 모드로 전환'} <span>→</span>
          </button>
          {!password && <p className="form-help">전환은 관리자 계정으로 서명합니다. 아래에서 합성 계정 비밀번호를 먼저 입력하세요.</p>}
        </div>
      </section>

      <section className="section" id="practice" aria-labelledby="practice-title">
        <div className="section-heading">
          <div><p className="kicker">멘토용 정책 시뮬레이터</p><h2 id="practice-title">다섯 판정을 시험하세요</h2></div>
          <span className="note-pill">LLM 대신 결정론적 모의 모델</span>
        </div>
        <div className="practice-grid">
          <form className="panel simulator" onSubmit={run}>
            <div className="step-label"><b>1</b><span>요청자 선택</span></div>
            <div className="role-options">
              {accounts.map(item => <label className={email === item.email ? 'selected' : ''} key={item.email}>
                <input type="radio" name="user" value={item.email} checked={email === item.email} onChange={e => setEmail(e.target.value)} />
                <span className={`avatar ${item.role}`}>{item.mark}</span>
                <span><b>{item.name}</b><small>{item.role} · 합성 계정</small></span>
              </label>)}
            </div>
            <div className="step-label"><b>2</b><span>합성 계정 비밀번호</span></div>
            <label className="sr-only" htmlFor="password">합성 계정 비밀번호</label>
            <input id="password" type="password" value={password} autoComplete="off"
                   onChange={e => { setPassword(e.target.value); tokens.current = {} }}
                   placeholder=".env의 MOCK_SSO_PASSWORD (기본 test-password)" />
            <div className="step-label"><b>3</b><span>업무 요청 입력</span></div>
            <label className="sr-only" htmlFor="message">업무 요청</label>
            <textarea id="message" value={message} onChange={e => setMessage(e.target.value)} rows="4" maxLength="500" />
            <div className="scenario-list" aria-label="빠른 실습 시나리오">
              {scenarios.map(scenario => <button type="button" key={scenario.name} onClick={() => { setEmail(scenario.email); setMessage(scenario.message) }}>{scenario.name}</button>)}
            </div>
            <button className="primary-button" disabled={busy || !message.trim() || !password}>{busy ? '정책 확인 중…' : '정책을 거쳐 MCP 호출하기'} <span>→</span></button>
            <p className="form-help">입력 문장은 규칙으로 Tool Call JSON으로 변환됩니다. 외부 LLM API는 호출하지 않습니다. 요청자는 서명된 합성 토큰에서만 오고, 본문으로는 주장할 수 없습니다.</p>
          </form>

          <div className={`panel result-panel ${current ? decisionMeta[current.decision]?.tone : ''}`} aria-live="polite">
            {!current ? <div className="empty-result"><div className="shield">◇</div><h3>판정 결과가 여기에 표시됩니다</h3><p>왼쪽의 빠른 시나리오를 골라 정책 흐름을 시작해 보세요.</p></div> : <>
              <div className="result-top"><div><p>Gateway 최종 판정</p><DecisionBadge decision={current.decision} /></div><code>{current.policy_id}</code></div>
              <h3>{current.reason}</h3>
              <div className="result-facts">
                <div><span>사용자</span><b>{activeUser?.display_name || current.role}</b></div>
                <div><span>생성 Tool Call</span><b>{result.generated_call?.tool_name || current.tool_name}</b></div>
                <div><span>정보 등급 / 행위</span><b>{current.data_class} / {current.action}</b></div>
                <div><span>Upstream 실행</span><b className={current.upstream_executed ? 'yes' : 'no'}>{current.upstream_executed ? '실행됨' : '실행 안 됨'}</b></div>
              </div>
              {current.restrictions && Object.keys(current.restrictions).length > 0 && <div className="restriction"><b>적용 제한</b><span>목적지 {current.restrictions.destination}, 최대 {current.restrictions.max_chars}자</span></div>}
              {current.decision === 'Approval' && current.approval_id && <div className="approval-callout">
                <span>승인 요청이 생성되었습니다.</span>
                <span className="button-row">
                  <button disabled={busy} onClick={() => approve(current.approval_id)}>승인 후 재검증</button>
                  <button disabled={busy} onClick={() => reject(current.approval_id)}>사유와 함께 거부</button>
                </span>
              </div>}
              <div className="evidence-line"><span>독립 효과 로그</span><b>{current.effect_before} → {current.effect_after}</b><small>{current.upstream_executed ? '호출 후 증가 확인' : '차단 시 증가하지 않아야 함'}</small></div>
              <details><summary>개발자용 원본 JSON</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
            </>}
          </div>
        </div>
      </section>

      <section className="section" id="policy" aria-labelledby="policy-title">
        <div className="section-heading">
          <div><p className="kicker">OPA / REGO</p><h2 id="policy-title">확정한 333 권한표</h2><p>r=읽기, w=쓰기, x=외부 전송·고위험 실행. ✓라도 x에는 승인·제한 같은 추가 통제가 붙습니다.</p></div>
          <span className="note-pill">기본 DENY</span>
        </div>
        <div className="matrix-wrap">
          <table className="matrix-table">
            <thead><tr><th rowSpan="2">역할</th>{['public', 'nonimportant', 'important'].map(c => <th colSpan="3" key={c}>{c}</th>)}</tr><tr>{[0,1,2].flatMap(i => ['r','w','x'].map(a => <th key={`${i}-${a}`}>{a}</th>))}</tr></thead>
            <tbody>{['customer','employee','admin'].map(role => <tr key={role}><th>{role}</th>{['public','nonimportant','important'].flatMap(dataClass => ['r','w','x'].map(action => {
              const cell = cells[`${role}.${dataClass}.${action}`]
              const allowed = cell && cell.decision !== 'Block'
              return <td key={`${dataClass}-${action}`} className={allowed ? 'permit' : 'deny'} title={cell ? `${cell.decision}: ${cell.reason}` : '조회 중'}>{allowed ? '✓' : '—'}</td>
            }))}</tr>)}</tbody>
          </table>
        </div>
        <div className="decision-legend">{Object.entries(decisionMeta).map(([key, meta]) => <span key={key}><i className={meta.tone}>{meta.icon}</i><b>{meta.label}</b></span>)}</div>
      </section>

      <section className="section" id="supply" aria-labelledby="supply-title">
        <div className="section-heading">
          <div><p className="kicker">REGISTRY + SUPPLY CHAIN</p><h2 id="supply-title">무엇을 연결했고, 승인본과 같은지 봅니다</h2><p>서버 출처·버전·전송방식·도구 스키마 해시를 등록하고, SBOM·취약점·MCP 전용 SARIF를 증적으로 연결합니다.</p></div>
          <div className="button-row"><button onClick={refreshCatalog} disabled={busy}>계약 다시 비교</button><button onClick={importReports} disabled={busy}>스캔 결과 가져오기</button></div>
        </div>
        <div className="registry-grid">
          {(state?.servers || []).map(server => <article className="registry-card" key={server.id}>
            <div className="registry-title"><span className={`server-icon ${server.id}`}>{server.id === 'github' ? 'GH' : server.id === 'mock-stdio' ? '&gt;_' : 'M'}</span><div><h3>{server.display_name}</h3><p>{server.supplier}</p></div><span className={`server-status ${server.status.toLowerCase()}`}>{server.status}</span></div>
            <dl><div><dt>전송</dt><dd>{server.transport}</dd></div><div><dt>승인 Ref</dt><dd>{server.source_ref}</dd></div><div><dt>도구</dt><dd>{state.tools.filter(tool => tool.server_id === server.id).length}개 등록</dd></div><div><dt>상태 설명</dt><dd>{server.status_reason}</dd></div></dl>
          </article>)}
        </div>
        <div className="supply-panel">
          <div className="supply-copy"><span className="supply-mark">SB</span><div><h3>공급망 증적</h3><p>Syft CycloneDX SBOM + Trivy 취약점/오구성/비밀정보 + AI-Infra-Guard <code>mcp-scan</code> SARIF</p></div></div>
          <div className="scan-results">
            {(state?.supply_chain || []).length === 0 ? <div className="scan-empty"><b>아직 스캔 결과 없음</b><span><code>./demo.sh scan</code> 후 가져오기를 누르세요.</span></div> : state.supply_chain.map(report => <div key={report.id}><b>{report.scanner}</b><span>C {report.critical_count} · H {report.high_count} · M {report.medium_count}</span></div>)}
          </div>
        </div>
        <p className="attribution">AI-Infra-Guard 통합 표기: “This project integrates AI-Infra-Guard, open-sourced by Tencent Zhuque Lab.” 현재 데모는 요청 범위대로 <b>mcp-scan CLI/SARIF 연계만</b> 포함합니다.</p>
      </section>

      <section className="section" id="audit" aria-labelledby="audit-title">
        <div className="section-heading"><div><p className="kicker">EVIDENCE</p><h2 id="audit-title">판정과 실제 실행을 같은 Trace로 추적합니다</h2></div><a className="secondary-link" href="http://localhost:16686" target="_blank" rel="noreferrer">Jaeger 열기 ↗</a></div>
        <div className="audit-summary"><div><span>저장된 최근 판정</span><b>{state?.decisions?.length || 0}</b></div><div><span>독립 upstream 효과</span><b>{state?.upstream_effect_count || 0}</b></div><div><span>승인 대기</span><b>{state?.approvals?.length || 0}</b></div><div><span>활성 정책</span><b>{state?.policy?.id || '확인 중'}</b></div></div>
        <div className="audit-table-wrap"><table className="audit-table"><thead><tr><th>시간</th><th>요청자</th><th>도구</th><th>등급/행위</th><th>판정</th><th>실행</th><th>Trace ID</th></tr></thead><tbody>
          {(state?.decisions || []).map(item => <tr key={item.id}><td>{new Date(item.created_at).toLocaleTimeString('ko-KR')}</td><td>{item.role}</td><td><code>{item.tool_name}</code></td><td>{item.data_class} / {item.action}</td><td><DecisionBadge decision={item.decision} /></td><td>{item.upstream_executed ? '예' : '아니오'}</td><td><code title={item.trace_id}>{item.trace_id.slice(0, 10)}…</code></td></tr>)}
          {(state?.decisions || []).length === 0 && <tr><td colSpan="7" className="empty-cell">실습 요청을 실행하면 판정 증적이 쌓입니다.</td></tr>}
        </tbody></table></div>
      </section>

      <section className="section boundary">
        <div><p className="kicker">정확한 해석</p><h2>이 데모가 증명하는 범위</h2></div>
        <ul><li><b>증명:</b> 로그인·세션·모델 인자 검증과 60초 Agent 위임, Gateway 판정·upstream 실행까지</li><li><b>구조적 통제:</b> MCP 서버는 내부망, Gateway는 actor·agent·정규화한 요청 SHA-256을 함께 검증</li><li><b>아직 아님:</b> 실제 SSO, workload attestation(SPIFFE), 키 회전/JWKS, 외부 모델 실호출, 운영 HA</li></ul>
      </section>
    </main>
    <footer><span>MCP Governance Security Gateway · Synthetic Lab</span><span>데모 데이터만 사용 · 기본 DENY · 인증 연계 전</span></footer>
  </>
}

createRoot(document.getElementById('root')).render(<App />)
