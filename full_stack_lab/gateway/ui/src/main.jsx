import React, { useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const decisionMeta = {
  Allow: { icon: '✓', label: '허용', tone: 'allow' },
  Alert: { icon: '!', label: '허용 + 경보', tone: 'alert' },
  Approval: { icon: '⌛', label: '승인 대기', tone: 'approval' },
  Restrict: { icon: '↘', label: '제한 후 실행', tone: 'restrict' },
  Block: { icon: '×', label: '차단', tone: 'block' },
}

const scenarios = [
  { name: '공개 문서 허용', user: 'cust-demo', message: '공개 공지를 읽어줘' },
  { name: '중요 열람 경보', user: 'emp-demo', message: '중요 계약 초안을 읽어줘' },
  { name: '외부 전송 제한', user: 'admin-demo', message: '공개 공지를 외부로 보내줘' },
  { name: '중요 전송 승인', user: 'admin-demo', message: '중요 계약을 외부로 전송해줘' },
  { name: '권한 부족 차단', user: 'cust-demo', message: '중요 계약을 읽어줘' },
]

async function api(path, options) {
  const response = await fetch(path, options)
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

function App() {
  const [health, setHealth] = useState(null)
  const [state, setState] = useState(null)
  const [matrix, setMatrix] = useState(null)
  const [user, setUser] = useState('cust-demo')
  const [message, setMessage] = useState('공개 공지를 읽어줘')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [nextHealth, nextState, nextMatrix] = await Promise.all([
        api('/api/health'), api('/api/state'), api('/api/policy/matrix'),
      ])
      setHealth(nextHealth)
      setState(nextState)
      setMatrix(nextMatrix)
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

  const run = async (event) => {
    event?.preventDefault()
    setBusy(true)
    setError('')
    try {
      const response = await api('/api/mock-model', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_token: user, message }),
      })
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
      const response = await api(`/api/approvals/${id}/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer_token: 'admin-demo' }),
      })
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
    try { await api('/api/catalog/refresh', { method: 'POST' }); await load() }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const importReports = async () => {
    setBusy(true)
    try { await api('/api/supply-chain/import', { method: 'POST' }); await load() }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  const current = result?.result
  const activeUser = state?.principals?.find(item => item.token === (current?.user_token || user))
  const cells = useMemo(() => {
    const index = {}
    for (const cell of matrix?.cells || []) index[`${cell.role}.${cell.data_class}.${cell.action}`] = cell
    return index
  }, [matrix])

  return <>
    <header className="hero">
      <div className="topbar">
        <a className="brand" href="#top" aria-label="대시보드 맨 위로">
          <span className="brand-mark">M</span>
          <span><b>MCP Governance</b><small>Security Gateway Lab</small></span>
        </a>
        <nav aria-label="주요 화면">
          <a href="#practice">실습</a><a href="#policy">333 정책</a><a href="#supply">공급망</a><a href="#audit">감사</a>
        </nav>
      </div>
      <div className="hero-copy" id="top">
        <div>
          <p className="eyebrow">MENTOR-FRIENDLY DEMONSTRATION</p>
          <h1>MCP 실행 전에<br /><em>누가·무엇을·왜</em><br />확인합니다.</h1>
          <p className="lede">모델의 판단을 믿는 대신 Registry 계약과 OPA/Rego 정책으로 MCP 호출을 결정하고, 실제 실행 여부를 별도 증적으로 대조하는 로컬 실습입니다.</p>
        </div>
        <div className="hero-summary" aria-label="현재 핵심 상태">
          <div><span>정책 결과</span><strong>5종</strong><small>Allow · Alert · Approval · Restrict · Block</small></div>
          <div><span>권한 조합</span><strong>27칸</strong><small>3 역할 × 3 등급 × r/w/x</small></div>
          <div><span>데이터</span><strong>100% 합성</strong><small>실제 계정·기밀·LLM API 없음</small></div>
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
        <div className="flow" aria-label="MCP 보안 Gateway 처리 흐름">
          <div className="flow-node"><span>01</span><b>합성 사용자</b><small>업무 요청 · 역할</small></div><i>→</i>
          <div className="flow-node primary"><span>02</span><b>Security Gateway</b><small>신원 · 계약 · 입력 검증</small></div><i>→</i>
          <div className="flow-node"><span>03</span><b>OPA / Rego</b><small>333 정책 결정</small></div><i>→</i>
          <div className="flow-node"><span>04</span><b>MCP Server</b><small>HTTP · stdio · SSE</small></div><i>→</i>
          <div className="flow-node"><span>05</span><b>증적</b><small>PostgreSQL · Trace · Effect</small></div>
        </div>
        <div className="health-grid">
          {[
            ['Gateway', health?.components?.gateway], ['OPA 정책', health?.components?.opa],
            ['PostgreSQL', health?.components?.postgresql], ['합성 MCP', health?.components?.mock_http_mcp],
            ['Jaeger', health?.components?.jaeger], ['GitHub MCP', health?.components?.github_mcp, true],
          ].map(([label, ok, optional]) => <div className="health-item" key={label}><StatusDot ok={ok} pending={optional && !ok} /><span><b>{label}</b><small>{optional && !ok ? '인증 대기 · 의도적 비활성' : ok ? '연결됨' : '확인 중'}</small></span></div>)}
        </div>
      </section>

      <section className="section" id="practice" aria-labelledby="practice-title">
        <div className="section-heading">
          <div><p className="kicker">직접 실습</p><h2 id="practice-title">다섯 판정을 시험하세요</h2></div>
          <span className="note-pill">LLM 대신 결정론적 모의 모델</span>
        </div>
        <div className="practice-grid">
          <form className="panel simulator" onSubmit={run}>
            <div className="step-label"><b>1</b><span>요청자 선택</span></div>
            <div className="role-options">
              {(state?.principals || []).map(item => <label className={user === item.token ? 'selected' : ''} key={item.token}>
                <input type="radio" name="user" value={item.token} checked={user === item.token} onChange={e => setUser(e.target.value)} />
                <span className={`avatar ${item.role}`}>{item.role === 'customer' ? '고' : item.role === 'employee' ? '직' : '관'}</span>
                <span><b>{item.display_name}</b><small>{item.role} · 합성 계정</small></span>
              </label>)}
            </div>
            <div className="step-label"><b>2</b><span>업무 요청 입력</span></div>
            <label className="sr-only" htmlFor="message">업무 요청</label>
            <textarea id="message" value={message} onChange={e => setMessage(e.target.value)} rows="4" maxLength="500" />
            <div className="scenario-list" aria-label="빠른 실습 시나리오">
              {scenarios.map(scenario => <button type="button" key={scenario.name} onClick={() => { setUser(scenario.user); setMessage(scenario.message) }}>{scenario.name}</button>)}
            </div>
            <button className="primary-button" disabled={busy || !message.trim()}>{busy ? '정책 확인 중…' : '정책을 거쳐 MCP 호출하기'} <span>→</span></button>
            <p className="form-help">입력 문장은 규칙으로 Tool Call JSON으로 변환됩니다. 외부 LLM API는 호출하지 않습니다.</p>
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
              {current.decision === 'Approval' && current.approval_id && <div className="approval-callout"><span>승인 요청이 생성되었습니다.</span><button disabled={busy} onClick={() => approve(current.approval_id)}>관리자로 승인 후 재검증</button></div>}
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
        <ul><li><b>증명:</b> Gateway를 통과한 호출의 계약·정책 판정과 upstream 실행 여부</li><li><b>구조적 통제:</b> MCP 서버는 내부 Docker 네트워크에 두고 호스트에는 Gateway만 공개</li><li><b>아직 아님:</b> 조직 전체 우회 경로 차단, 실사용자 인증, 실제 GitHub 권한 위임, 운영 HA</li></ul>
      </section>
    </main>
    <footer><span>MCP Governance Security Gateway · Synthetic Lab</span><span>데모 데이터만 사용 · 기본 DENY · 인증 연계 전</span></footer>
  </>
}

createRoot(document.getElementById('root')).render(<App />)
