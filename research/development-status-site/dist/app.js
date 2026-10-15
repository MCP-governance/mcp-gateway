"use strict";
const $ = (id) => document.getElementById(id);
let data;
function node(tag, cls, text) { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e; }
function date(value) { if(!value || !Number.isFinite(Date.parse(value)))return '—'; return new Date(value).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false})+' KST'; }
function text(id,value){$(id).textContent=value;}
function score(value){return node('span',value===1?'filled':value===0.5?'half':'open',value===1?'●':value===0.5?'◐':'○');}
function section(title,values){const box=node('section');box.append(node('h3','',title));for(const value of values)box.append(node('p','',value));return box;}
function showDetail(row){
  text('detail-id',row.id+' · '+row.goal_id+' · '+row.progress+'%');text('detail-title',row.title);
  const box=$('detail-content');box.replaceChildren();
  box.append(section('완료조건',[row.completion_condition]));
  for(const [key,label] of Object.entries(data.rubric.stage_labels)){
    const line=node('div','stage-line');line.append(score(row.stage_scores[key]),node('b','',` ${label} · ${row.stage_scores[key]}점`),node('p','',row.stage_notes[key]));box.append(line);
  }
  box.append(section('남은 공백',[row.known_gap]),section('원본 정책 매핑',[row.source_pac_ids.join(' · ')+' / PAC01–24 원본과 런타임 PAC-01–15는 별도 번호 체계입니다.']));
  const source=node('section');source.append(node('h3','','코드·함수와 시험 후보'));for(const p of [...row.code_symbols_files,...row.regression_test_candidates])source.append(node('code','path',p));box.append(source);
  const evidence=node('section');evidence.append(node('h3','','검수 근거 · 로컬 정본 경로'));for(const e of row.evidence){evidence.append(node('code','path',e.path));if(e.sha256)evidence.append(node('div','hash','SHA-256 '+e.sha256));}box.append(evidence);
  box.append(section('판단 범위',['과거 근거는 해당 보고일·판본·계정·경로의 표본입니다. 경로 표시가 실시간 로그 조회나 원본 파일 공개를 뜻하지 않습니다.']));
  $('detail').showModal();
}
function renderRows(){
 const query=$('search').value.trim().toLowerCase(),goal=$('goal-filter').value,status=$('status-filter').value;
 const rows=data.items.filter(r=>(!goal||r.goal_id===goal)&&(!query||[r.id,r.title,r.known_gap,...r.source_pac_ids].join(' ').toLowerCase().includes(query))&&(!status||status==='remaining'&&!r.complete||status==='missing'&&r.stage_scores.implementation===0||status==='partial'&&r.stage_scores.implementation===0.5||status==='complete'&&r.complete||status==='p0'&&r.priority==='P0'));
 $('rows').replaceChildren();for(const r of rows){const tr=node('tr');const first=node('td');const b=node('button','row-title',r.title);b.type='button';b.addEventListener('click',()=>showDetail(r));first.append(b,node('span','row-id',r.id));tr.append(first);
 const pac=node('td');pac.append(node('span','pac',r.source_pac_ids.join(' · ')));tr.append(pac,node('td','pct',r.progress+'%'));
 for(const key of Object.keys(data.rubric.stage_labels)){const td=node('td','stage');const s=score(r.stage_scores[key]);s.setAttribute('aria-label',data.rubric.stage_labels[key]+' '+r.stage_scores[key]+'점');td.append(s);tr.append(td);}
 const priority=node('td');priority.append(node('span','priority '+r.priority.toLowerCase(),r.priority));tr.append(priority);$('rows').append(tr);}
 text('row-count',rows.length+' / 40개');$('empty').hidden=!!rows.length;
}
async function init(){
 const response=await fetch('data.json',{cache:'no-store'});if(!response.ok)throw new Error('현황 데이터 응답 '+response.status);data=await response.json();
 if(data.items.length!==40||data.schema_version!==1)throw new Error('현황 데이터 형식을 확인할 수 없습니다.');
 text('as-of',date(data.as_of));text('audit-time','현장 조회 '+date(data.audit_as_of));
 text('progress',data.summary.progress+'%');$('overall-progress').value=data.summary.progress;
 text('complete',data.summary.complete+' / '+data.summary.total);text('implemented',data.summary.implementation_full+'개');text('partial','부분 '+data.summary.implementation_partial+'개 · 미구현 '+data.summary.implementation_missing+'개');
 for(const g of data.goals){const a=node('a','goal');a.href='#wbs';a.addEventListener('click',()=>{$('goal-filter').value=g.id;renderRows();});a.append(node('span','goal-id',g.id),node('span','goal-name',g.title));const p=node('progress');p.max=100;p.value=g.progress;p.setAttribute('aria-label',g.title+' 진척 '+g.progress+'%');a.append(p,node('span','goal-value',g.progress+'%'));$('goals').append(a);const opt=node('option','',g.id+' '+g.title);opt.value=g.id;$('goal-filter').append(opt);}
 for(const [key,label] of Object.entries(data.rubric.stage_labels)){const div=node('div','stage-total');const p=node('progress');p.max=40;p.value=data.summary.stage_equivalent_counts[key];p.setAttribute('aria-label',label+' 환산 '+p.value+' / 40');div.append(node('span','',label),p,node('strong','',p.value+' / 40점'));$('stage-totals').append(div);}
 for(const e of data.exclusions)$('exclusions').append(node('li','',e));
 for(const [i,p] of data.pipeline.entries()){const box=node('article','pipeline-step');box.append(node('div','index','0'+(i+1)),node('h3','',p.title),node('span','state',p.state),node('p','',p.detail));$('pipeline').append(box);}
 const s=data.live_sample;text('sample-scope',s.scope);
 text('sample-event','실행 차단 이벤트 #'+s.os_event_id);
 for(const [label,value] of [['서비스 상태',s.service_active==='active'?'실행 중':'확인 필요'],['프로세스 자동 관측',s.automatic_process?'관리 UID에서 활성':'미확인'],['네트워크 탐색',['0','disabled'].includes(s.netscan)?'중지':'설정 확인'],['주기 수집 후 조회 확인',s.poll_delivery_seconds+'초'],['표본 발생 → 수신',s.ingest_latency_seconds+'초'],['표본 정규화 내용',s.normalized_projection_equal?'일치':'불일치'],['오류 원복 후 수집',s.recovery?'복구 확인':'미확인']]){const row=node('div');row.append(node('dt','',label),node('dd','',value));$('sample-values').append(row);}
 for(const [label,value] of [['발생',date(s.observed_at)],['수신',date(s.received_at)],['복구 후 마지막 수신',date(s.last_seen_at)],['표본 프로세스 관측',date(s.last_scan_at)],['표본 projection SHA-256',s.projection_sha256],['기기 검사 로그 SHA-256',s.source_artifact_sha256]]){$('sample-hashes').append(node('p','hash',label+' · '+value));}
 for(const f of data.findings){const box=node('article','finding');const top=node('div','finding-top');top.append(node('span','priority '+f.priority.toLowerCase(),f.priority),node('span','',f.id+' · '+f.state));box.append(top,node('h3','',f.title),node('p','',f.detail),node('div','proof',f.verification));const details=node('details');details.append(node('summary','','개선 완료조건'),node('p','',f.next),node('code','path',f.evidence));box.append(details);const b=node('button','','연결된 WBS '+f.tasks.join(' · ')+' →');b.addEventListener('click',()=>{showDetail(data.items.find(r=>r.id===f.tasks[0]));});box.append(b);$('findings').append(box);}
 for(const n of data.next_actions){const box=node('article','next-item');box.append(node('div','order','0'+n.order),node('h3','',n.title),node('small','',n.tasks),node('p','',n.done_when));$('next-actions').append(box);}
 for(const id of ['search','goal-filter','status-filter'])$(id).addEventListener(id==='search'?'input':'change',renderRows);
 $('close').addEventListener('click',()=>$('detail').close());
 for(const a of document.querySelectorAll('nav a'))a.addEventListener('click',()=>{for(const x of document.querySelectorAll('nav a'))x.classList.toggle('selected',x===a);});
 renderRows();
}
init().catch(error=>{text('load-error','현황을 불러오지 못했습니다: '+error.message);$('load-error').hidden=false;text('as-of','데이터 미수신');});
