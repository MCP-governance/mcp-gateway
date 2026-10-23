"""Feed the existing worker from approved standing tasks; never run an inference poll."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from agent_policy import reserve_blocked
from console import EventLog
from worker import Hub, ROOT as HUB_ROOT, service_lock, stamp

LOOP = HUB_ROOT.parent
ROOT = LOOP.parent
STANDING = LOOP / 'standing'
STATE = STANDING / '.state.json'
PROVIDERS = ('codex', 'antigravity')
BUSY = {'queued', 'running', 'waiting_quota', 'waiting_service', 'waiting_budget', 'lead_handoff', 'orphan_running'}
PLANNER_EVERY = 3 * 3600


def emit(task, body, author='System', state='completed'):
    EventLog().append(author, 'message', task, state, body, recipient='All')


def save(state):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    temporary.replace(STATE)


def parse_text(text):
    head, separator, body = text.partition('\n---\n')
    meta = dict(re.findall(r'^(cwd|mode|task):\s*(.+)$', head, re.M))
    cwd = Path(meta.get('cwd', '')).resolve()
    if not separator or not body.strip() or cwd.parent != ROOT.resolve() or not (cwd.name=='mcp-gateway-wbs' or cwd.name.startswith('mcp-gw-')) or not cwd.is_dir():
        raise ValueError('승인된 작업 클론과 지시서 본문이 필요합니다')
    if meta.get('mode', 'read-only') not in {'read-only', 'workspace-write'}:
        raise ValueError('허용하지 않는 실행 모드')
    return meta, body


def submit(hub, provider, path, meta, body):
    key = hashlib.sha256((provider + str(path) + json.dumps(meta, sort_keys=True) + body).encode()).hexdigest()[:20]
    prompt = STANDING / '.prompts' / (key + '.md')
    prompt.parent.mkdir(exist_ok=True)
    prompt.write_text(body, encoding='utf-8')
    return hub.add(provider, path.stem, meta['cwd'], prompt, task_id=meta.get('task', path.stem),
                   mode=meta.get('mode', 'read-only'), until=time.time() + 86400, job_id='auto-' + key)


def harvest(state, jobs):
    for provider in PROVIDERS:
        job_id = state.get('planner_job_' + provider)
        job = next((job for job in jobs if job['id'] == job_id), None)
        if not job or job['state'] != 'completed' or not job.get('result'):
            continue
        result = Path(job['result']).resolve()
        if not result.is_relative_to((HUB_ROOT / 'runtime/results').resolve()):
            raise ValueError('Invalid planner result path')
        blocks = re.findall(r'^=== TASK (\S+) ===\n(.*?)^=== END ===', result.read_text(encoding='utf-8'), re.M | re.S)
        count = 0
        for slug, block in blocks[:3]:
            try:
                parse_text(block)
            except ValueError:
                continue
            slug = re.sub(r'[^A-Za-z0-9_.-]', '-', slug)[:50]
            target = STANDING / provider / f'{job_id}-{slug}.md'
            target.parent.mkdir(exist_ok=True)
            target.write_text(block, encoding='utf-8')
            count += 1
        state.pop('planner_job_' + provider)
        save(state)
        emit('AUTO-DISPATCH', f'{provider} 업무 발굴 결과: 다음 작업 {count}건. 원문: {result}')


def report_usage(state, info, jobs, reserve, now):
    provider = info['name']
    quota = json.loads(info['quota']) if isinstance(info.get('quota'), str) else info.get('quota') or {}
    left = quota.get('remaining_percent')
    blocked = info.get('until_at', 0) > now or reserve_blocked(quota, reserve, now)
    level = 'rest' if blocked else 'low' if left is not None and left <= max(20, reserve) else 'active'
    key = 'usage_report_' + provider
    if state.get(key) == level:
        return blocked
    previous = state.get(key)
    state[key] = level
    if level == 'active' and previous not in {'rest', 'low'}:
        return blocked
    recent = next((j for j in jobs if j['provider'] == provider and j['state'] == 'completed'), None)
    reset = max(info.get('until_at', 0), quota.get('reset_at') or 0)
    action = {'rest': '예비량 보호를 위해 새 작업을 쉬고 대기열·세션을 보존합니다. 실행 중 작업은 강제 종료하지 않습니다.',
              'low': '소진 전 사전 보고: 작은 작업을 마무리하고 결과·다음 행동을 저장합니다.',
              'active': '사용량 회복 확인: 보존한 대기열부터 재개합니다.'}[level]
    age = now - (quota.get('observed_at') or 0)
    emit('AUTO-DISPATCH', f'{provider} 잔여 {left if left is not None else "미확인"}%'
         f'{" (오래된 관측)" if age > 300 else ""} · {action}\n'
         f'다음 확인: {stamp(reset) if reset > now else "사용량 재조회 후 판단"}\n'
         f'최근 완료: {recent["title"] if recent else "없음"} · 근거: {recent.get("result") if recent else "없음"}')
    return blocked


def dispatch(hub, state):
    from handoffs import tick
    tick(hub)
    status = hub.snapshot()
    harvest(state, status['jobs'])
    now = time.time()
    for provider in PROVIDERS:
        # Idle accounts need the same bounded official refresh as queued accounts.
        hub.refresh_usage(provider)
    status = hub.snapshot()
    reserve = hub.policy['reserve_percent']
    for info in status['providers']:
        blocked = report_usage(state, info, status['jobs'], reserve, now)
        provider = info['name']
        if provider not in PROVIDERS or blocked or any(j['provider'] == provider and j['state'] in BUSY for j in status['jobs']):
            continue
        queue = sorted((STANDING / provider).glob('*.md'))
        planner = not queue
        if planner:
            if now - state.get('planner_at_' + provider, 0) < PLANNER_EVERY or not (STANDING / '_planner.md').exists():
                continue
            path = STANDING / '_planner.md'
        else:
            path = queue[0]
        try:
            meta, body = parse_text(path.read_text(encoding='utf-8'))
        except (ValueError,OSError) as exc:
            key='invalid:'+str(path)
            if state.get(key)!=str(exc):
                state[key]=str(exc)
                save(state)
                emit('AUTO-DISPATCH',f'지시서 확인 필요: {path} · {exc}. 원문은 보존하며 다른 제공자·응답 인계는 계속합니다.',state='blocked')
            continue
        if any(j['cwd'] == str(Path(meta['cwd']).resolve()) and j['state'] in {'needs_attention', 'orphan_running'} and j['mode'] != 'read-only' for j in status['jobs']):
            continue
        if planner:
            meta['task'] = f'AUTO-PLAN-{provider}-{int(now // PLANNER_EVERY)}'
        job = submit(hub, provider, path, meta, body)
        if planner:
            state['planner_at_' + provider], state['planner_job_' + provider] = now, job
        else:
            (STANDING / 'done').mkdir(exist_ok=True)
            path.replace(STANDING / 'done' / (provider + '-' + path.name))
        save(state)
        emit('AUTO-DISPATCH', f'{provider} 유휴 슬롯에 {path.stem} 선제 배정 · 작업 {job}. '
             'Opus 지시를 기다리지 않고 승인된 백로그를 진행합니다. 결과는 리더 검토 대상으로 남깁니다.')
    save(state)


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT / 'mcp-gateway-wbs'), *args], capture_output=True,
                          text=True, encoding='utf-8', timeout=60,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def restart_when_idle(hub):
    # Hold the admission transaction until the old worker stops, closing the claim/stop race.
    with hub.db() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM meta WHERE key='reload_worker_pending'").fetchone():
            return
        if db.execute("SELECT 1 FROM jobs WHERE state IN ('running','orphan_running')").fetchone():
            return
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                                 "Stop-ScheduledTask -TaskName Local-Agent-Hub -ErrorAction Stop; Start-ScheduledTask -TaskName Local-Agent-Hub -ErrorAction Stop"],
                                capture_output=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError('실행기 유휴 재시작 실패; 다음 확인에서 재시도')
        held=db.execute("SELECT value FROM meta WHERE key='reload_provider_holds'").fetchone()
        for provider,info in json.loads(held[0]).items() if held else []:
            db.execute("UPDATE providers SET until_at=?,reason=? WHERE name=? AND reason='실행기 유휴 반영 대기'",(info['until_at'],info['reason'],provider))
        db.execute("DELETE FROM meta WHERE key='reload_provider_holds'")
        resume = db.execute("SELECT value FROM meta WHERE key='resume_after_reload'").fetchone()
        for job_id in json.loads(resume[0]) if resume else []:
            job = db.execute("SELECT provider FROM jobs WHERE id=? AND state='paused' AND attempts=0 AND pid IS NULL",(job_id,)).fetchone()
            if job:
                configured = hub.config['providers'][job['provider']]
                db.execute("UPDATE jobs SET state='queued',next_at=?,model=?,effort=?,updated=? WHERE id=?",
                           (time.time(),configured['model'],configured['effort'],time.time(),job_id))
                hub.event(db,job_id,'queued','리더 수신함의 명시적 재개 요청: 실행기 반영 후 현재 요청 모델로 재개')
        db.execute("DELETE FROM meta WHERE key='resume_after_reload'")
        db.execute("DELETE FROM meta WHERE key='reload_worker_pending'")
    emit('AUTO-DISPATCH', '진행 중 CLI가 없는 것을 확인하고 실행기를 재시작했습니다. 최신 인계 전달 규칙을 다음 작업부터 적용합니다.')


def main():
    STANDING.mkdir(exist_ok=True)
    with service_lock(STANDING):
        state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
        hub = Hub()
        restart_when_idle(hub)
        dispatch(hub, state)
        if git('fetch', '-q', 'origin', 'main').returncode:
            return
        last = state.get('main_cursor')
        log = git('log', '--reverse', '--format=%h%x09%s%x09%b%x1e', f'{last}..origin/main' if last else 'origin/main~5..origin/main')
        if log.returncode:
            return
        for entry in filter(None, (e.strip() for e in log.stdout.split('\x1e'))):
            sha, subject, body = (entry.split('\t', 2) + ['', ''])[:3]
            author = 'Codex' if 'Codex' in body else 'Gemini' if 'Gemini' in body else 'Claude'
            emit('MAIN', f'main {sha} · {subject}', author)
        head = git('rev-parse', 'origin/main')
        if head.returncode == 0:
            state['main_cursor'] = head.stdout.strip()
        save(state)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        from worker import redact
        with (HUB_ROOT / 'runtime/service-errors.log').open('a', encoding='utf-8') as log:
            log.write(stamp() + ' dispatcher ' + redact(str(exc))[:300] + '\n')
        raise
