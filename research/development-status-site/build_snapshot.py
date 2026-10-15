"""Build a reviewed WBS snapshot; keep product APIs and credentials out of the site."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WIKI = REPO / 'research/llm-wiki'
HERE = Path(__file__).resolve().parent
STAGES = {'implementation': '구현', 'regression': '회귀 검사', 'deployment': '배포',
          'real_device': '실제 환경', 'acceptance_complete': '완료 검수'}
GOALS = ['도입·공급망 검증', '승인·계약 관리', '신원·호출 권한', '데이터·비신뢰 결과 보호',
         '엔드포인트 집행', '감사·로그 전달', '종료·폐기', '가입·설치·하네스 운영', '자원·연결 지표', '개발 협업·근거 관리']

def read(path):
    return json.loads((REPO/path).read_text(encoding='utf-8-sig'))

def digest(path):
    return hashlib.sha256((REPO/path).read_bytes()).hexdigest()

def write_outputs(data):
    out=WIKI/'analysis/development-wbs';out.mkdir(parents=True,exist_ok=True)
    (out/'snapshot.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (HERE/'dist').mkdir(exist_ok=True)
    (HERE/'dist/data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 목표 기능 WBS 검수 현황', '', f"기준 시각: {data['as_of']} / 현장 읽기: {data['audit_as_of']}", '',
        f"단계 가중 진척 **{data['summary']['progress']}%**. 최종 완료 **{data['summary']['complete']}/40**. 구현 완료 {data['summary']['implementation_full']}개, 부분 {data['summary']['implementation_partial']}개, 미구현 {data['summary']['implementation_missing']}개.", '',
        data['rubric']['formula'], '', data['rubric']['complete_rule'], '',
        '0점=미확인, 0.5점=부분/과거/선택 범위 근거, 1점=해당 단계의 정해진 범위 충족. 이 수치는 사용자 요청으로 만든 검수 기준이며 공수 추정/일정/제품 인증 수치가 아니다.', '',
        '| 목표 | 진척 | 최종 완료 |','| --- | ---: | ---: |']
    lines += [f"| {g['id']} {g['title']} | {g['progress']}% | {g['complete']}/4 |" for g in data['goals']]
    lines += ['', '## 원자 작업', '', '| ID | 작업 | 진척 | 구현/회귀/배포/실제환경/검수 |','| --- | --- | ---: | --- |']
    lines += [f"| {r['id']} | {r['title']} | {r['progress']}% | {' / '.join(str(r['stage_scores'][s]) for s in STAGES)} |" for r in data['items']]
    lines += ['', '각 작업의 원본 PAC 번호·코드·함수·완료조건·남은 공백·증거 SHA는 [JSON 정본](snapshot.json)에 있다. 원본 PAC01–24와 런타임 PAC-01–15는 별도 번호 체계다.', '', '## 점수에서 제외한 범위','']+[f'- {e}' for e in data['exclusions']]
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(data['summary'],ensure_ascii=False))
    return data

def build_after_log_fix():
    """Apply only the three reviewed telemetry scores to the preserved snapshot."""
    baseline_path='research/llm-wiki/analysis/development-wbs/snapshot-before-log-fix.json'
    data=read(baseline_path)
    audit=WIKI/'analysis/endpoint-log-fix'
    reviewed=read('research/llm-wiki/analysis/endpoint-log-fix/source-reviewed.json')
    for path, expected in reviewed['source_sha256'].items():
        assert digest(path)==expected, f'reviewed source changed: {path}'
    manifest=read('research/llm-wiki/analysis/endpoint-log-fix/deploy-manifest.json')
    deployment=read('research/llm-wiki/analysis/endpoint-log-fix/deployment.json')
    live=read('research/llm-wiki/analysis/endpoint-log-fix/pj1-live/result.json')
    replay=read('research/llm-wiki/analysis/endpoint-log-fix/pj1-live/replay-result.json')
    assert replay['ok'] and replay['periodic_replay_confirmed'] and replay['rows_after']==1
    delivered=read('research/llm-wiki/analysis/endpoint-log-fix/pj1-live/delivered.json')
    historical_as_of=data['as_of']
    pg_lines=[json.loads(line) for line in (audit/'pg-snapshot-deployed.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    pg_result=next((row for row in pg_lines if row.get('result')=='PASS'),None)
    auto_lines=[json.loads(line) for line in (audit/'pj1-live/automatic-check.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    auto_result=next((row for row in reversed(auto_lines) if row.get('stage')=='final'),None)
    assert live['ok'] and live['automatic_process'] and live['other_uid_excluded'] and live['actual_os_event_received']
    assert live['scoped_empty_reconciliation'] and live['collector_fault_visible'] and live['last_success_preserved']
    assert live['cursor_no_advance_on_failure'] and live['broker_survived_observer_failure'] and live['recovery']
    assert auto_result and auto_result['ok'] and auto_result['run_id']==live['run_id']
    assert pg_result and pg_result['schema'] and all(pg_result['cases'].values())
    assert pg_lines[-1].get('observation')=='schema-dropped'
    assert deployment['ok'] and deployment['readiness']['status']=='ready'
    prepared=reviewed['prepared_sha256']
    manifest_sha={entry['path']:entry['new_sha256'] for entry in manifest}
    assert prepared==manifest_sha
    deployed_images=(deployment['source_hashes']['agent-service'],deployment['source_hashes']['gateway'])
    for path,sha in prepared.items():
        if path.startswith('endpoint-agent/'):
            remote='/endpoint-kit/'+path.removeprefix('endpoint-agent/')
        else:
            remote='/app/app/'+path.removeprefix('full_stack_lab/gateway/app/')
        assert any(image.get(remote)==sha for image in deployed_images), f'deployment hash mismatch: {path}'
    assert delivered['os_event']['id']==1388
    assert delivered['agent']['observation']['process']['state']=='success'
    assert delivered['agent']['observation']['network']['state']=='disabled'
    expected_event=next(row for row in auto_lines if row.get('stage')=='fixtures-active')['expected_event']
    def utc_stamp(value):
        return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
    projection=lambda event:{'event_id':event['event_id'],'observed_at':utc_stamp(event['observed_at']),
        'kind':event['kind'],'details':event['details']}
    expected_projection=projection(expected_event)
    received_projection=projection(delivered['os_event'])
    assert expected_projection==received_projection, 'OS event projection mismatch'
    projection_sha256=hashlib.sha256(json.dumps(expected_projection,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    assert all((REPO/path).exists() for path in [baseline_path,
        'research/llm-wiki/analysis/endpoint-log-fix/source-reviewed.json',
        'research/llm-wiki/analysis/endpoint-log-fix/deploy-manifest.json',
        'research/llm-wiki/analysis/endpoint-log-fix/deployment.json',
        'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/result.json',
        'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/delivered.json',
        'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/automatic-check.jsonl',
        'research/llm-wiki/analysis/endpoint-log-fix/pg-snapshot-deployed.jsonl'])

    evidence_paths=[
        'research/llm-wiki/analysis/endpoint-log-fix/source-reviewed.json',
        'research/llm-wiki/analysis/endpoint-log-fix/deploy-manifest.json',
        'research/llm-wiki/analysis/endpoint-log-fix/deployment.json',
        'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/result.json',
        'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/delivered.json',
        'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/automatic-check.jsonl',
        'research/llm-wiki/analysis/endpoint-log-fix/pg-snapshot-deployed.jsonl',
        'research/llm-wiki/analysis/endpoint-log-fix/review.md',
        'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/replay-result.json']
    configs={
      'G05.03': {
        'stage_scores':{'implementation':0.5,'regression':1,'deployment':1,'real_device':0.5,'acceptance_complete':0},
        'implementation_assessment':'partial_candidate',
        'implementation_review_note':'Linux managed 범위의 프로세스·stdio 자동 관측과 전달이 추가됐지만, 네트워크 탐색은 비활성이고 실제 MCP 앱 프로세스/다른 OS는 확인하지 않았다.',
        'known_gap':'PJ1 Linux 관리 UID에서 합성 marker 프로세스의 자동 발견·전달과 별도 실제 AppArmor 거부 이벤트 전달을 확인했다. 사용자 실제 MCP 프로세스, Windows, 다른 UID, 자연어/모델 호출은 확인하지 않았다.',
        'stage_notes':{
          'implementation':'관리 Linux UID의 프로세스·stdio 관측 및 자동 전송 경로가 있고 네트워크 탐색은 비활성이다. 실사용 MCP 식별이나 전체 OS 범위는 미완료.',
          'regression':'현재 관리형 검사기 9개, Node 14개, endpoint observation/auth 검증과 격리 PostgreSQL 8개 조건 PASS. 전부 정의된 Linux 수집·표시 범위이며 실제 Windows 집행은 포함하지 않는다.',
          'deployment':'PJ1에 검수된 agent/managed-linux/os-observer 및 서버 경로를 배포했고, 확인 가능한 파일은 manifest·배포 SHA와 일치한다. 별도 Windows 실제기기 배포 증거가 아니다.',
          'real_device':'Linux UID 한정 PJ1에서 합성 marker 프로세스 자동 전송과 실제 OS 차단 이벤트를 확인. 실제 사용자 MCP 프로세스·다른 UID·Windows는 미검증.',
          'acceptance_complete':'지원 OS·수집 범위 전체 및 실제 MCP 앱 연동, 운영 중 offline/retry 범위를 검수해야 한다.'}},
      'G06.03': {
        'stage_scores':{'implementation':0.5,'regression':0.5,'deployment':1,'real_device':0.5,'acceptance_complete':0},
        'implementation_assessment':'partial_candidate',
        'implementation_review_note':'24시간 전체 거부 집계는 이미 제공된다. 채널별 수집 상태·신선도·listener 상세와 최근 200행 범위 구분을 보강했지만 페이지네이션과 전 구간 집계는 미완료.',
        'known_gap':'채널별 상태·신선도와 listener 상세는 이번에 보강했다. 최근 200건 조회를 넘는 페이지 이동·전체 누적집계, 모든 정보원 장애·장기 오프라인 조건은 미검증이다.',
        'stage_notes':{
          'implementation':'기존 24시간 전체 거부 집계를 유지하며 collector 상태·신선도와 listener 전용 상세를 추가했다. 최근 200건 조회에 한정되며 페이지 이동/전체 누적 분포는 미완료.',
          'regression':'UI/상태 및 endpoint 수집 회귀가 통과했지만, UI 상한을 넘는 페이지 이동·전체 누적집계와 모든 channel failure 경계는 완전 검수하지 않았다.',
          'deployment':'솔루션에 Console/receiver, PJ1에 agent/observer를 배포하고 각각 source/deployed hash를 대조했다.',
          'real_device':'Linux managed endpoint에서 상태·자동 process/OS event를 확인했다. 200건을 초과하는 페이지 이동이나 Windows 운영 상태는 확인하지 않았다.',
          'acceptance_complete':'200행 표시 상한의 안내만으로 전체 목록/집계 조건을 충족하지 않으며 페이지 이동과 수집 상태 경계 전반을 검수해야 한다.'}},
      'G06.04': {
        'stage_scores':{'implementation':0.5,'regression':0.5,'deployment':1,'real_device':0.5,'acceptance_complete':0},
        'implementation_assessment':'partial_candidate',
        'implementation_review_note':'기존 표본과 새 OS 이벤트의 안전한 projection/hash 증거가 있으며 deploy/source hash를 대조한다. 모든 전달 원본의 raw byte·무손실 보존 pipeline은 없다.',
        'known_gap':'새 PJ1 OS 표본 1388의 보존 이벤트와 전달 결과 projection이 일치한 범위를 확인했다. 원본 raw HTTP 전체, 전 이벤트 무손실 보존, 바이트 단위 보존은 확인하지 않았다.',
        'stage_notes':{
          'implementation':'일부 표본의 source/deployed hash 및 projection 검증 근거가 있다. 모든 이벤트에 대한 원본/수신 manifest와 mismatch 처리 pipeline은 미완료.',
          'regression':'현재 source/deployment hash, projection 대조와 격리 DB 8개 상태조건을 검증했다. 전체 이벤트를 대상으로 한 무손실·원본 바이트 검증은 없다.',
          'deployment':'검수된 PJ1 배포 source hash 및 observer/receiver 파일 hash를 대조했다.',
          'real_device':'PJ1의 새 OS 표본 1388 projection이 보존 수신자료와 일치했다. raw HTTP 전체 및 원본 전체 event collection은 확인하지 않았다.',
          'acceptance_complete':'모든 이벤트의 출처 raw digest, 안전한 projection digest, 변환 및 수신 기록과 손실 경계 검증이 필요하다.'}}}
    for row in data['items']:
        if row['id'] not in configs:
            continue
        cfg=configs[row['id']]
        row.update({k:v for k,v in cfg.items() if k not in ('stage_scores','stage_notes')})
        row['stage_scores']=cfg['stage_scores']
        row['stage_notes']=cfg['stage_notes']
        row['actual_evidence_paths']=list(dict.fromkeys(evidence_paths))
        row['evidence']=[{'path':path,'sha256':digest(path)} for path in row['actual_evidence_paths']]
        row['progress']=round(sum(row['stage_scores'].values())*20,1)
        row['complete']=all(score==1 for score in row['stage_scores'].values())

    data['as_of']=datetime.now(timezone.utc).isoformat()
    data['audit_as_of']=datetime.fromtimestamp(auto_result['at'],timezone.utc).isoformat()
    data['branch']='10/14-endpoint-telemetry-fix'
    data['snapshot']=True
    data['source_snapshot']={'path':baseline_path,'as_of':historical_as_of,'historical_progress':21.8,
        'note':'보존된 사전 스냅샷은 해당 시점의 확정 이력으로 취급했다. 그 시점의 audit source hash를 현재 파일과 재비교하지 않았다.'}
    data['basis_head']='ab6936c64f3578de8360b840f1928681714fa7bb'
    for goal in data['goals']:
        rows=[item for item in data['items'] if item['goal_id']==goal['id']]
        goal['progress']=round(sum(item['progress'] for item in rows)/4,1)
        goal['complete']=sum(item['complete'] for item in rows)
    data['summary']['progress']=round(sum(item['progress'] for item in data['items'])/40,1)
    data['summary']['complete']=sum(item['complete'] for item in data['items'])
    data['summary']['stage_equivalent_counts']={stage:round(sum(item['stage_scores'][stage] for item in data['items']),1) for stage in STAGES}
    data['summary']['implementation_full']=sum(item['stage_scores']['implementation']==1 for item in data['items'])
    data['summary']['implementation_partial']=sum(item['stage_scores']['implementation']==0.5 for item in data['items'])
    data['summary']['implementation_missing']=sum(item['stage_scores']['implementation']==0 for item in data['items'])
    assert data['summary']['progress']==24.8 and data['summary']['complete']==0
    data['findings']=[
      {'id':'LOG-01','priority':'P1','title':'자동 프로세스 관측 범위','state':'Linux 표본 검증',
       'detail':'PJ1 Linux 관리 UID에서 합성 marker 프로세스 자동 발견·전달이 확인됐다. 네트워크 탐색은 비활성으로 유지했고, 이를 실제 사용자 MCP 프로세스 관측으로 확대하지 않는다.',
       'verification':'PJ1 자동 검증 run result와 delivered listener, source/deploy hash 기록을 대조. 실제 AppArmor 차단 이벤트 전달도 별도 확인.',
       'next':'지원 OS·UID·프로세스 식별 조건과 수집 범위를 정하고, 실제 허가된 MCP 프로그램을 포함한 양성·음성·다른 UID 시험을 수행.',
       'tasks':['G05.03','G06.03'],'evidence':'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/result.json'},
      {'id':'LOG-02','priority':'P1','title':'수집 상태와 탐지 0건 구분','state':'Linux 검증·전체 범위 미완료',
       'detail':'채널별 상태 및 last-success 보존, collector fault·recovery 경로를 검증했다. 네트워크 탐색 disabled는 0건 성공과 구별하고, Windows 실제기기는 확인하지 않았다.',
       'verification':'PJ1 result/delivered, 9개 관리형 회귀, 관측/auth 회귀와 PostgreSQL 전용 8조건 기록.',
       'next':'실제 운영 단말에서 stale/offline/unauthorized/partial/failure 상태와 UI의 번역·복구 표현을 OS별 검증.',
       'tasks':['G06.03'],'evidence':'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/automatic-check.jsonl'},
      {'id':'LOG-03','priority':'P1','title':'전용 상세의 listener 누락','state':'수정 배포·범위 검수 필요',
       'detail':'listener 전용 상세와 수집상태 표시가 제공 Console에 추가됐다. 전체 행 수는 최근 200건 조회 범위로 제한되며 전체 누적/페이지 이동은 제공하지 않는다.',
       'verification':'Console/상태 단위검사와 PJ1 배포 hash 및 전용 화면 수신 확인.',
       'next':'최근 200건 상한·잘림 안내를 넘는 페이지 이동과 집계가 필요하면 별도 완료조건으로 검증.',
       'tasks':['G06.01','G06.03'],'evidence':'research/llm-wiki/analysis/endpoint-log-fix/deployment.json'},
      {'id':'LOG-04','priority':'P1','title':'부분 snapshot에서 기존 행 보존','state':'격리 DB 회귀 PASS',
       'detail':'불완전·legacy unmarked-empty·source mismatch에서 삭제하지 않고, 명시적 complete에서만 해당 범위 삭제하며 delete failure는 transaction rollback한다.',
       'verification':'전용 PostgreSQL schema에서 8가지 독립 사전/사후 조건 모두 PASS; schema dropped 확인.',
       'next':'운영 사용량에서 cap·다중 source와 offline 재시도 조건을 확장 검증하고 지원 계약을 유지.',
       'tasks':['G05.03','G06.03'],'evidence':'research/llm-wiki/analysis/endpoint-log-fix/pg-snapshot-deployed.jsonl'},
      {'id':'LOG-05','priority':'P1','title':'오래된 관측 상태 처리','state':'회귀 및 PJ1 복구 확인',
       'detail':'stale 관측을 현재 탐지 0건으로 바꾸지 않으며 보수적 listener count를 유지하는 조건과 collector failure 후 last-success/cursor 보존·복구를 확인했다.',
       'verification':'격리 PG stale/rollback 조건 PASS; PJ1 fault-visible·last-success-preserved·cursor-no-advance·recovery true.',
       'next':'장기 운용 중 stale 경계와 UI 표시·경보 운영기준을 제품 규모에서 검증.',
       'tasks':['G06.03','G09.03'],'evidence':'research/llm-wiki/analysis/endpoint-log-fix/pj1-live/result.json'},
      {'id':'LOG-06','priority':'P1','title':'Windows 차단 이벤트 수집 경로','state':'코드·합성 단위검사만 완료',
       'detail':'Windows collector 코드와 합성 단위 검사는 확인됐지만 실제 Windows 기기 수집·권한·전달은 미검증이다. 사용자는 우선 Linux 범위를 선택했다.',
       'verification':'정적 source hash 및 PowerShell parser/unit checks; 실제 Windows managed endpoint 시험 없음.',
       'next':'Linux 완료 범위와 분리해 Windows를 지원할 때 실제 이벤트 source·권한·offline recovery를 실기기로 확인.',
       'tasks':['G05.04','G06.01','G06.03'],'evidence':'research/llm-wiki/analysis/endpoint-log-fix/source-reviewed.json'}]
    sample=delivered['os_event']
    recovered=next(row for row in auto_lines if row.get('stage')=='recovery-pass')['agent']
    occurred=datetime.fromisoformat(sample['observed_at'].replace('Z','+00:00'))
    received=datetime.fromisoformat(sample['received_at'].replace('Z','+00:00'))
    delivery=next(row for row in auto_lines if row.get('stage')=='automatic-delivery-pass')
    fixtures=next(row for row in auto_lines if row.get('stage')=='fixtures-active')
    data['pipeline']=[
      {'title':'기기에서 관측','state':'부분','detail':'관리 Linux UID에서 합성 marker 프로세스와 실제 AppArmor 거부 이벤트를 각각 확인했다. 다른 UID·Windows·실제 MCP 앱 프로세스는 미검증.'},
      {'title':'수집·전송','state':'부분','detail':'PJ1 Linux managed 경로에서 process/stdio 및 OS event 자동 전달, collector failure 표시와 복구를 확인했다. 네트워크 탐색은 비활성이다.'},
      {'title':'솔루션 수신·저장','state':'부분','detail':'OS 이벤트 1388 표본의 안전한 projection 일치와 격리 DB 8조건을 확인했다. 원본 전체·raw HTTP 전체 무손실은 미확인.'},
      {'title':'화면 표시','state':'부분','detail':'listener 전용 상세와 channel 상태 표시를 배포했다. 200건은 최근 조회 범위이며 전체 누적/페이지 이동은 없다.'},
      {'title':'정책·감사 해석','state':'부분','detail':'비활성·실패·stale과 0건을 구분하는 경로를 보강했다. 수집기는 자기 보고를 포함하며 OS 전체 관측을 보장하지 않는다.'}]
    data['live_sample']={
      'service_active':'active','netscan':'disabled','automatic_process':True,
      'other_uid_excluded':live['other_uid_excluded'],'os_event_id':sample['id'],
      'normalized_projection_equal':True,
      'projection_sha256':projection_sha256,
      'source_artifact_sha256':digest('research/llm-wiki/analysis/endpoint-log-fix/pj1-live/automatic-check.jsonl'),
      'poll_delivery_seconds':round(delivery['at']-fixtures['at'],2),
      'ingest_latency_seconds':round((received-occurred).total_seconds(),2),
      'collector_fault_visible':live['collector_fault_visible'],
      'last_success_preserved':live['last_success_preserved'],
      'cursor_no_advance_on_failure':live['cursor_no_advance_on_failure'],
      'recovery':live['recovery'],'duplicate_event_rows':replay['rows_after'],
      'periodic_replay_dedup':True,
      'listener_count_now':0,'listener_count_sample':1,
      'last_seen_at':recovered['observation']['os']['reported_at'],
      'last_scan_at':delivered['listener']['observed_at'],
      'served_console_sha256':deployment['source_hashes']['gateway']['/app/app/agent_static/console.js'],
      'observed_at':sample['observed_at'],'received_at':sample['received_at'],
      'kind':'실행 차단','target':'python3.12',
      'scope':'PJ1 관리 Linux 범위; 합성 marker 프로세스 자동 전송과 실제 OS 차단 이벤트 표본. 실제 MCP/모델 호출 없음.'}
    data['exclusions']=[
      'D-79 자가 승인 9-tool 원장 744–800은 긍정 검증에서 제외.',
      'E13 변형은 부분 시험이며 공식 E01–E13 카드의 미실행 상태를 완료로 바꾸지 않음.',
      '설치·코드·MCP 설정·SDK protocol success는 자연어 관리 하네스 호출 성공과 별도.',
      '실제 사용자 MCP 프로세스 식별, 다른 UID/root, Windows 실기기, 모든 앱/하네스와 92개 도구 효과는 검증 범위 밖.',
      'OS 표본 1388의 projection 일치는 raw HTTP 전체, 모든 원본 이벤트 수집, 무손실 보존을 증명하지 않음.',
      '최근 200건 목록은 전체 누적 건수나 완전한 페이지 이동이 아님. 이미 제공되는 24시간 전체 거부 집계의 존재를 부정하지 않음.',
      'Windows 신규 collector는 코드·합성 단위검사만 확인했고 실제 Windows 기기 수집은 미검증.',
      'snapshot-before-log-fix의 감사 source hash는 당시 확정 이력으로 보존하며 현재 소스와 재대조하지 않음. 이번 근거는 reviewed/prepared/deployed SHA 및 현재 PJ1·DB 결과로 별도 검증.']
    data['next_actions']=[
      {'order':1,'title':'200건 범위와 상세 탐색 완성','tasks':'G06.03','done_when':'200건 상한에서 잘림과 조회 범위가 드러나고, 전체 누적집계 또는 페이지 이동 정책이 확인된다.'},
      {'order':2,'title':'실제 허가 MCP 프로세스 범위 검증','tasks':'G05.03','done_when':'격리된 실제 지원 MCP 앱 실행을 합성 marker와 구분하고, 자동·수동·OS event·network scope 및 다른 UID 경계를 확인한다.'},
      {'order':3,'title':'전체 이벤트 원본·projection provenance','tasks':'G06.04','done_when':'원본/수신 artifact와 안전한 projection digest·변환·누락 범위를 이벤트별로 연결하고 end-to-end mismatch를 검증한다.'},
      {'order':4,'title':'Windows 실기기 경계 검증','tasks':'G05.04 · G06.01 · G06.03','done_when':'사용자가 Windows 지원 범위를 선택하면 실제 Windows 이벤트 생산원·권한·전송·offline recovery를 검증한다.'}]
    return write_outputs(data)

def build():
    proposal = read('research/llm-wiki/analysis/wbs-review/suggestions.json')
    korean = read('research/llm-wiki/analysis/wbs-review/korean-copy.json')
    live = read('research/llm-wiki/analysis/endpoint-log-audit/live-readonly.json')
    static = read('research/llm-wiki/analysis/endpoint-log-audit/static-review.json')
    checks = read('research/llm-wiki/analysis/wbs-review/current-checks.json')
    ids = [r['id'] for r in proposal['items']]
    assert len(set(ids)) == len(ids) == 40
    assert Counter(r['goal_id'] for r in proposal['items']) == Counter({f'G{i:02}':4 for i in range(1,11)})
    for path, expected in static['source_sha256'].items():
        assert digest(path) == expected, f'audit source changed: {path}'
    assert live['event_sample_comparison']['equal_normalized_projection']
    items = []
    for raw in proposal['items']:
        row = dict(raw)
        row.update(korean[row['id']])
        row['source_pac_ids'] = list(row['source_pac_ids'])
        if row['id'] in ('G01.03', 'G08.04'):
            row['source_pac_ids'].append('PAC04')
            row['completion_condition'] += ' 시험 환경은 운영 경로와 분리하고 합성 데이터·지정된 격리 자원으로 검증한다.'
        assessment = row['implementation_assessment']
        scores = {key: (0.5 if value else 0) for key,value in row['stage_booleans'].items()}
        scores['implementation'] = {'complete':1, 'partial_candidate':0.5, 'not_implemented':0}[assessment]
        row['stage_notes'] = {
            'implementation': row.get('implementation_review_note', '현재 소스에 해당 경로가 있으며 범위별 구현 평가는 별도다.'),
            'regression': '현재 소스와 대응하는 요구조건 전체 회귀 근거 미확인. 과거 PASS는 날짜가 있는 참고 근거다.',
            'deployment': '과거 특정 판본·선택 경로 배포 증거만 있으면 0.5점. 소스 존재는 배포 근거가 아니다.',
            'real_device': '과거 특정 계정·하네스·효과 표본이면 0.5점. Windows·모든 계정·모든 도구로 확대하지 않는다.',
            'acceptance_complete': '완료조건 전체와 미해결 결함을 검수하기 전에는 0점.',
        }
        if row['id'] == 'G05.01':
            assert next(c for c in checks['checks'] if c['name']=='managed-health')['exit_code']==0
            scores['regression'] = 1
            row['actual_evidence_paths'].append('research/llm-wiki/analysis/wbs-review/current-checks.json')
            row['stage_notes']['regression'] = '현재 검사기 소스에서 정상군·foreign profile·disabled/missing Windows rule 등 기존 9개 회귀 통과. 실제 Windows 집행은 별도.'
            scores['deployment'] = 1
            row['stage_notes']['deployment'] = 'PJ1 설치 Linux 관리기·agent·OS collector 3파일이 현재 소스 LF 정규화 SHA와 일치. Linux 관리 경로에 한정.'
        if row['id'] in ('G09.01', 'G09.02', 'G09.03'):
            assert next(c for c in checks['checks'] if c['name']=='resource-display')['exit_code']==0
            scores['regression'] = 0.5
            row['actual_evidence_paths'].append('research/llm-wiki/analysis/wbs-review/current-checks.json')
            row['stage_notes']['regression'] = '현재 표시 로직 4개 회귀 통과: 0·미측정·오래된 값·실패·잘못된 범위 구분. backend/권한 통합 회귀는 환경 의존성 미충족으로 미실행.'
        if row['id']=='G03.03':
            row['stage_notes']['deployment'] = '과거 배포 근거만 부분 인정. 이번 실제 image core.py SHA와 현재 working-tree LF SHA가 달라 현재 코드 배포로 인정하지 않음.'
        if row['id'] in ('G05.03','G06.03','G06.04'):
            row['actual_evidence_paths'] = list(row['actual_evidence_paths']) + [
                'research/llm-wiki/analysis/endpoint-log-audit/live-readonly.json',
                'research/llm-wiki/analysis/endpoint-log-audit/static-review.json']
        if row['id']=='G06.04':
            scores['real_device'] = 0.5
            row['stage_notes']['real_device'] = '현재 API 표본1387과 기기에 보존한 실제 이벤트의 event_id/UTC시각/종류/details 정규화 projection SHA 일치. raw HTTP 전체 무결성과 전체 이벤트 완전성은 미확인.'
        if row['id'] in ('G10.03', 'G10.04'):
            scores = {'implementation':1,'regression':1,'deployment':0,'real_device':0,'acceptance_complete':0}
            row['implementation_assessment']='complete'
            row['stage_notes']['implementation']='이번 작업에서 40개 WBS·PAC 의미 매핑·근거 상세·채널별 전달 문제·다운로드 화면 구현.'
            row['stage_notes']['regression']='정본 40개 ID/목표별4개/계산/경로/감사 소스 hash/표본 projection 일치 검증.'
            row['known_gap']='웹은 갱신 시각이 있는 검수 스냅샷이다. 제품 API 실시간 연동과 운영 수집기 자동화는 별도 후속.'
            row['actual_evidence_paths'].append('research/development-status-site/build_snapshot.py')
        for p in row['actual_evidence_paths']:
            assert (REPO/p.split('#')[0]).exists(), p
        row['stage_scores'] = scores
        row.pop('stage_booleans', None)
        row.pop('evidence_bound_note', None)
        row.pop('implementation_review_note', None)
        row['progress'] = round(sum(scores.values()) * 20, 1)
        row['complete'] = all(v==1 for v in scores.values())
        row['priority'] = 'P0' if row['id'] in ('G05.03','G06.03','G06.04','G03.02') else 'P1' if row['goal_id'] in ('G05','G06','G07','G08') else 'P2'
        row['evidence'] = [{'path':p, 'sha256':digest(p.split('#')[0]) if (REPO/p.split('#')[0]).is_file() else None} for p in row['actual_evidence_paths']]
        items.append(row)
    findings = [
        {'id':'LOG-01','priority':'P0','title':'자동 프로세스 관측이 비활성', 'state':'확인됨',
         'detail':'PJ1 observer 설정 NETSCAN=0. 프로세스·stdio 목록 자동 POST를 건너뛴다. Ghidra SDK 성공과 자동 로그 전달은 별개다.',
         'verification':'현재 기기 설정 읽기 + 설치 소스 SHA 일치 + 이전 수동 1건 대조',
         'next':'네트워크 스캔과 프로세스 관측을 분리하고 UID·수집 scope·보존 정책을 명시. 승인 범위를 정한 뒤 자동 전달 정상·음성군 시험.',
         'tasks':['G05.03','G06.03'], 'evidence':'research/llm-wiki/analysis/endpoint-log-audit/live-readonly.json'},
        {'id':'LOG-02','priority':'P0','title':'관측 미실행과 정상 종료가 같은 상태로 표시', 'state':'정적 확인',
         'detail':'설정 inventory는 성공할 수 있지만 listener scan 비활성·401/403·정책 꺼짐도 exit 0이다. supervisor의 observer=ok는 각 관측 채널의 성공을 뜻하지 않는다.',
         'verification':'Linux/Windows supervisor와 report_listeners 반환 경로 검토',
         'next':'채널별 disabled/unauthorized/partial/failed/success와 마지막 성공·수신 시각을 보존. 미수집을 0건 탐지로 표시하지 않기.',
         'tasks':['G06.03'], 'evidence':'research/llm-wiki/analysis/endpoint-log-audit/static-review.json'},
        {'id':'LOG-03','priority':'P1','title':'전용 상세에서 수신 프로세스·리스너 행 누락', 'state':'현재 제공 화면 코드 확인',
         'detail':'API는 listeners를 반환하고 넓은 통합 목록은 사용하지만, 통제 범위 → 미등록·잔존은 inv.entries와 OS events만 집계한다. 전체 화면에서 안 보인다는 주장은 하지 않는다.',
         'verification':'실제 서비스가 제공하는 Console JS에서도 coverage의 inv.listeners 참조 없음',
         'next':'프로세스·리스너 표 및 count/chart 추가. 설정 발견·MCP 추정·OS 차단을 구분하고 최근 N건/잘림 범위를 표시.',
         'tasks':['G06.01','G06.03'], 'evidence':'research/llm-wiki/analysis/endpoint-log-audit/live-readonly.json'},
        {'id':'LOG-04','priority':'P0','title':'부분 snapshot이 기존 발견 행을 지울 수 있음', 'state':'정적 위험·재현 대기',
         'detail':'agent는 500개에서 자르지만 수신기는 목록을 전체 snapshot으로 간주하고 누락 행을 DELETE한다. 정보원 실패·부분 결과도 완전성 계약이 없다.',
         'verification':'제출 cap과 receiver DELETE 코드 검토. 실제 손실 발생은 이번 작업에서 재현하지 않음.',
         'next':'source별 complete/partial 및 scan ID 계약 추가. incomplete에서는 기존 행 보존. 격리 DB에서 501건·정보원 실패·재시도·정상 전체 삭제 시험.',
         'tasks':['G05.03','G06.03'], 'evidence':'research/llm-wiki/analysis/endpoint-log-audit/static-review.json'},
        {'id':'LOG-05','priority':'P1','title':'오래된 발견과 현재 관측 상태가 섞임', 'state':'정적 확인',
         'detail':'shadow 집계 쿼리는 관측 시각을 검사하지 않는다. 스캔 중단 후 과거 행이 남아 현재 신호처럼 사용될 수 있다. stale 행을 단순 삭제해 정상으로 만들면 안 된다.',
         'verification':'shadow_listener_count_for 쿼리와 현재 last_scan_at/last_seen_at 분리',
         'next':'stale·unknown coverage 상태 분리. 과거 감사 행 유지와 정책 입력의 신선도 기준을 함께 설계.',
         'tasks':['G06.03','G09.03'], 'evidence':'research/llm-wiki/analysis/endpoint-log-audit/static-review.json'},
        {'id':'LOG-06','priority':'P1','title':'Windows 차단 이벤트 수집 경로 공백', 'state':'소스 범위 확인',
         'detail':'Windows managed loop에는 Linux journald OS observer에 대응하는 차단 이벤트 collector가 없다. Linux 표본으로 Windows 전달 성공을 주장할 수 없다.',
         'verification':'Windows managed supervisor 소스 검토. 실제 Windows 기기 시험 미실행.',
         'next':'지원 범위 결정 후 Windows 실제 이벤트 생산원·권한·수집·중복·오프라인 복구를 격리 실기기에서 검증.',
         'tasks':['G05.04','G06.01','G06.03'], 'evidence':'research/llm-wiki/analysis/endpoint-log-audit/static-review.json'},
    ]
    goals=[]
    assert {p for row in items for p in row['source_pac_ids']} == {f'PAC{i:02}' for i in range(1,25)}
    for i,title in enumerate(GOALS,1):
        group=[r for r in items if r['goal_id']==f'G{i:02}']
        goals.append({'id':f'G{i:02}','title':title,'progress':round(sum(r['progress'] for r in group)/4,1),
                      'complete':sum(r['complete'] for r in group),'total':4})
    totals={key:round(sum(r['stage_scores'][key] for r in items),1) for key in STAGES}
    data = {'schema_version':1,'title':'MCP 목표 기능 · WBS 현황','as_of':datetime.now(timezone.utc).isoformat(),
        'audit_as_of':live['captured_at'],'basis_head':'ab6936c64f3578de8360b840f1928681714fa7bb',
        'branch':'10/14-endpoint-log-wbs','snapshot':True,
        'rubric':{'stage_labels':STAGES,'stage_weight_percent':20,'task_weight':1,
            'scores':{'0':'미확인·미구현','0.5':'부분 구현·선택 표본·과거 판본 근거','1':'해당 단계의 정해진 범위 충족'},
            'formula':'40개 작업 각각의 5단계 점수(0/0.5/1) × 20%, 작업 동일 가중 평균. 기능 수·공수·일정·외부 인증 완료율이 아님.',
            'complete_rule':'5단계가 모두 1인 작업만 최종 완료. 신규 WBS의 현재 검수 기준이며 과거 실험 카드 완료를 변경하지 않음.'},
        'summary':{'progress':round(sum(r['progress'] for r in items)/40,1), 'complete':sum(r['complete'] for r in items),
            'total':40,'stage_equivalent_counts':totals,'implementation_full':sum(r['stage_scores']['implementation']==1 for r in items),
            'implementation_partial':sum(r['stage_scores']['implementation']==0.5 for r in items),
            'implementation_missing':sum(r['stage_scores']['implementation']==0 for r in items)},
        'goals':goals,'items':items,'findings':findings,
        'pipeline':[
            {'title':'기기에서 관측','state':'부분','detail':'관리 UID의 OS 거부 이벤트 생산 확인. 자동 프로세스 관측은 꺼짐.'},
            {'title':'수집·전송','state':'부분','detail':'Linux OS 주기 수집 표본 자동 전달. stdio는 과거 수동 1회만 전달.'},
            {'title':'솔루션 수신·저장','state':'부분','detail':'표본 1387 보존·정규화 내용 일치. 전체 무손실·부분 snapshot 계약은 미확인.'},
            {'title':'화면 표시','state':'누락','detail':'차단 표와 넓은 통합 목록 경로 있음. 전용 상세에 listener 행 미반영.'},
            {'title':'정책·감사 해석','state':'공백','detail':'미수집·오래된 관측·탐지 0 구분, freshness와 전체 범위 표시 보강 필요.'},
        ],
        'live_sample':{'service_active':live['service_active'],'netscan':live['listener_scan_setting'],
            'os_event_id':1387,'normalized_projection_equal':True,
            'projection_sha256':live['event_sample_comparison']['received_projection_sha256'],
            'source_artifact_sha256':live['event_sample_comparison']['source_artifact_sha256'],
            'poll_delivery_seconds':35.84,'ingest_latency_seconds':32.42,
            'listener_count_now':live['listener_rows_for_endpoint'],
            'last_seen_at':live['endpoint_agents'][0]['last_seen_at'],
            'last_scan_at':live['endpoint_agents'][0]['last_scan_at'],
            'served_console_sha256':live['served_console_sha256'],
            'observed_at':'2026-10-14T10:04:15.120155Z','received_at':'2026-10-14T10:04:47.543552Z',
            'kind':'실행 차단','target':'python3.12',
            'scope':'관리 Linux UID의 과거 interpreter 실행 거부 1건. Ghidra 프로세스 자동 탐지·전송의 증거가 아님.'},
        'exclusions':['D-79 자가 승인 9-tool 원장 744–800: 긍정 검증에서 제외.',
            'E13 변형은 부분 시험. 공식 E01–E13 카드의 미실행 상태를 완료로 바꾸지 않음.',
            '로컬 SDK 프로토콜 성공·MCP 설정·설치는 자연어 관리 하네스 호출 성공과 별도.',
            '관리 UID 밖 계정·root·Windows·모든 앱·92개 도구 전체 효과는 검증 범위 밖.',
            '로그 수신 raw HTTP 바이트 전체 보존/무손실을 표본 projection 일치로 보장하지 않음.',
            '현재 core.py·Console JS working tree와 배포 이미지 전체는 동일하지 않음. 현재 PJ1 collector 3파일과 receiver endpoint_plane은 LF 정규화 SHA 일치.'],
        'next_actions':[
            {'order':1,'title':'로그 가시성과 수집 상태 분리','tasks':'G05.03 · G06.03','done_when':'설정·프로세스·OS 각 채널의 비활성/권한없음/실패/부분/성공과 마지막 수신 시각이 보인다.'},
            {'order':2,'title':'부분 snapshot 삭제 방지','tasks':'G05.03 · G06.03','done_when':'501건·정보원 실패·오프라인 재시도에서 기존 행 유지, 전체 성공에서만 삭제 대조가 실행된다.'},
            {'order':3,'title':'실제 하네스 경계 결함 수정','tasks':'G03 · G05 · G08','done_when':'DEV-31 토큰 helper 접근·DEV-29 상태 세션·DEV-30 거부 잡음을 정상군/공격군으로 재검증한다.'},
            {'order':4,'title':'종료·폐기와 전체 지원 범위 검증','tasks':'G07 · G08','done_when':'실제 provider 자격 철회·세션 종료·Windows 및 지원 하네스의 독립 효과와 복구를 증명한다.'},
        ]}
    return write_outputs(data)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--after-log-fix',action='store_true',help='기존 스냅샷에서 검수된 세 로그 작업만 갱신')
    args=parser.parse_args()
    build_after_log_fix() if args.after_log_fix else build()
