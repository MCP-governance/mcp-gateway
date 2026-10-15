import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import os from 'node:os';
const bundle=process.env.CODEX_NODE_MODULES||path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const require=createRequire(path.join(bundle,'..','artifact-runtime.cjs'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const read=async name=>JSON.parse(await fs.readFile(path.join(root,name),'utf8'));
const req=(await read('analysis/requirements.json')).records;
const code=await read('analysis/code-structure.json');
const comp=(await read('analysis/competitor-mapping.json')).records;
const ints=await read('analysis/integrations.json');
const cases=await read('analysis/integration-cases.json');
const mcps=await read('analysis/mcp-candidates.json');
const refs=await read('analysis/reference-updates.json');
const skills=await read('analysis/skill-candidates.json');
const oss=await read('analysis/oss-reuse.json');
const exp=await read('catalogs/experiments.json');
const labels={source_only:'소스 확인',gap:'미충족/미구현',partial:'일부 확인',verified_unit:'단위 통과',verified_field:'실기기 통과'};
const plain=value=>value==null?'—':typeof value==='object'?JSON.stringify(value):String(value);
const clean=value=>typeof value==='string'&&value.startsWith('=')?"'"+value:value;
const packageBrief=r=>{const p=r.package_provenance||{}, artifact=p.package||{};
 return [artifact.name||r.name,artifact.version||r.version_or_commit||'공식 서버 판본 별도 고정',
 p.sha256?'Registry metadata SHA256: '+p.sha256:'배포판 세부 근거는 analysis/mcp-candidates.json',
 '설치·활성·실행 확인 아님'].join('\n');};
const wb=Workbook.create();
const summary=wb.worksheets.add('현황');
const sheets=[];
function table(name,headers,rows,widths){
 const s=wb.worksheets.add(name); sheets.push(s); s.showGridLines=false;
 const cols=headers.length, last=rows.length+4;
 s.getRangeByIndexes(1,0,1,1).values=[[name]];
 s.getRangeByIndexes(1,0,1,1).format.font={name:'Malgun Gothic',size:14,bold:true,color:'#17365D'};
 s.getRangeByIndexes(3,0,rows.length+1,cols).values=[headers,...rows].map(r=>r.map(clean));
 s.getRangeByIndexes(3,0,rows.length+1,cols).format.font={name:'Malgun Gothic',size:10,color:'#202D3A'};
 s.getRangeByIndexes(3,0,rows.length+1,cols).format.wrapText=true;
 s.getRangeByIndexes(3,0,rows.length+1,cols).format.verticalAlignment='top';
 s.getRangeByIndexes(3,0,1,cols).format={fill:'#17365D',font:{name:'Malgun Gothic',size:10,bold:true,color:'#FFFFFF'},rowHeight:30,wrapText:true};
 if(rows.length) s.getRangeByIndexes(4,0,rows.length,cols).format.rowHeight=100;
 widths.forEach((w,i)=>s.getRangeByIndexes(3,i,rows.length+1,1).format.columnWidth=w);
 s.tables.add(s.getRangeByIndexes(3,0,rows.length+1,cols),true,'Data'+sheets.length);
 if(rows.length)s.getRangeByIndexes(4,0,rows.length,cols).format.autofitRows();
 s.freezePanes.freezeRows(4);s.freezePanes.freezeColumns(2);
 return s;
}
table('요구사항',['ID','영역','조건','통과 기준','음성/경계 입력','검증 상태','우선순위','남은 조건','코드 근거','시험 근거','JSON 정본'],
 req.map(r=>[r.id,r.area,r.requirement,r.acceptance,r.negative_cases.join('\n'),labels[r.status],r.priority,r.gap,
 r.code_evidence.map(e=>`${e.path}:${e.line_start} ${e.symbol} (${e.source_state})`).join('\n'),
 r.test_evidence.map(e=>`${e.path}:${e.line_start||''} ${e.symbol||''}\n${e.verification}\n${e.run_evidence||''}`).join('\n')||'미실행','analysis/requirements.json']),[16,16,22,65,50,20,12,60,75,62,44]);
const reqSheet=wb.worksheets.getItem('요구사항');
reqSheet.getRange(`F5:F${req.length+4}`).dataValidation={rule:{type:'list',values:Object.values(labels)}};
reqSheet.getRange(`G5:G${req.length+4}`).dataValidation={rule:{type:'list',values:['P0','P1','P2']}};
reqSheet.getRange(`F5:F${req.length+4}`).conditionalFormats.add('containsText',{text:'미충족',format:{fill:'#FCE4D6',font:{color:'#9C0006'}}});
const functions=code.modules.flatMap((m,mi)=>m.functions.map((f,fi)=>[m.path,f.symbol,f.line_start,f.line_end,f.async,f.call_expressions.length,m.source_state,
 `analysis/code-structure.json modules[${mi}].functions[${fi}].call_expressions`,m.sha256]));
table('코드구조',['파일','함수','시작 행','끝 행','async','호출 표현 수','소스 상태','전체 호출 연결 정본','파일 SHA256'],functions,[72,38,12,12,12,16,24,80,75]);
table('기능대조',['ID','요구사항 ID','제품','확인한 구체 사실','기준 판본','확인 수준','우리의 남은 조건','근거 URL','고정 발췌'],
 comp.map(r=>[r.id,r.requirement_id,r.product,r.feature,r.version_or_commit,r.verification,r.our_gap,r.evidence_url,r.evidence_paths.join('\n')]),[16,18,26,95,55,50,90,95,75]);
table('연동대상',['ID','제품','구분','판본','경로','인증','지원 설명','라이선스','현재 공백','공식 근거'],
 ints.map(r=>[r.id,r.product,r.category,r.version_or_commit,r.route,r.auth,r.capabilities,r.license,r.gap,r.source_url]),[14,28,22,50,65,50,65,65,80,90]);
table('연동시험',['ID','제품','시험 조건','통과 기준','음성 입력','사전 조건','절차','상태','증거','실패 시 수정','코드 근거','공식 출처'],
 cases.map(r=>[r.id,r.product,r.feature,r.expected,r.negative_case,r.prerequisites.join('\n'),r.procedure.join('\n'),r.status,r.evidence,
 r.failure_fix,r.code_evidence.map(e=>`${e.path}:${e.line_start} ${e.symbol}`).join('\n'),r.source_refs.join('\n')]),[14,24,32,85,65,75,75,16,75,90,90,100]);
table('MCP대상',['ID','대상','패키지/판본','수송','로컬/원격 배치','인증 경계','라이선스','실험','현재 확인','출처'],
 mcps.map(r=>[r.id,r.title,packageBrief(r),plain(r.transport),plain(r.deployment_paths),plain(r.auth_boundary),r.license,plain(r.experiment_ids),plain(r.verification),r.source_url]),[25,32,85,25,90,90,85,28,70,90]);
table('실험계획',['ID','실험','실제 MCP ID','사전 조건','입력','절차','통과 기준','상태','원복'],
 exp.map(r=>[r.id,r.title,r.target_id,r.prerequisites.join('\n'),plain(r.input),r.steps.join('\n'),plain(r.expected),r.status,r.cleanup.join('\n')]),[14,45,30,100,90,105,110,16,90]);
table('연구근거',['ID','논문','게재 상태','학술지/학회','게재일','읽은 범위','차용 방법','한계','공식 근거'],
 refs.map(r=>[r.id,r.title,r.publication_status,r.venue,r.published_on,r.reading_scope,r.methodology_adaptation,plain(r.limitations),r.source_url]),[16,95,30,65,20,100,110,110,90]);
table('OSS스킬',['ID','이름','구분','commit','라이선스','현재 적용','활용 방법','한계/선정 조건','공식 출처'],
 [...skills.map(r=>[r.id,r.title,'공개 스킬',r.commit,r.license,r.status,plain(r.reuse_plan),plain(r.review_notes),r.source_url]),
 ...oss.map(r=>[r.id,r.title,'OSS/SDK',r.commit,r.license,r.status,plain(r.implementation_guidance),plain(r.selection_gate),r.source_url])],
 [16,50,22,55,38,65,100,110,85]);
summary.showGridLines=false; summary.tabColor='#17365D';
summary.getRange('A2:G2').values=[['MCP 기업 제공 요구사항·호환성 검증 대장',null,null,null,null,null,null]];
summary.getRange('A2:G2').format.font={name:'Malgun Gothic',size:14,bold:true,color:'#17365D'};
summary.getRange('A4:B9').values=[['검증 층','요구사항 수'],['소스 확인',null],['미충족/미구현',null],['단위 통과',null],['실기기 통과',null],['총 조건',req.length]];
for(let i=5;i<=8;i++)summary.getRange(`B${i}`).formulas=[[`=COUNTIFS('요구사항'!$F$5:$F$${req.length+4},A${i})`]];
summary.getRange('D4:F4').values=[['자료','레코드 수','의미']];
summary.getRange('D5:F11').values=[['코드 모듈',code.modules.length,'AST 구조 목록'],['함수',functions.length,'동적 호출 전체 감사와 다름'],['비교 사실',comp.length,'8개 제품의 고정 근거'],['연동 조건',cases.length,'실행 전 조건; 모두 미실행'],['실제 MCP 후보',mcps.length,'상용/공개 OSS만'],['실험 계획',exp.length,'모두 미실행'],['논문 재검토',refs.length,'정식 저널/학회/preprint 구분']];
summary.getRange('A12:F14').values=[['기준 HEAD',code.metadata.head,null,null,null,null],['현재 브랜치',code.metadata.branch,null,null,null,null],
 ['범위','단위 통과를 기업 검증 완료로 세지 않습니다. 실기기/독립 효과가 없는 조건은 남은 조건으로 유지합니다.',null,null,null,null]];
summary.getRange('A4:F14').format.font={name:'Malgun Gothic',size:10,color:'#202D3A'};
summary.getRange('A4:F14').format.rowHeight=30;
summary.getRange('A4:B4').format={fill:'#17365D',font:{color:'#FFFFFF',bold:true}};
summary.getRange('D4:F4').format={fill:'#17365D',font:{color:'#FFFFFF',bold:true}};
summary.getRange('A:A').format.columnWidth=24;summary.getRange('B:B').format.columnWidth=58;
summary.getRange('C:C').format.columnWidth=4;summary.getRange('D:D').format.columnWidth=26;
summary.getRange('E:E').format.columnWidth=16;summary.getRange('F:F').format.columnWidth=42;
summary.getRange('B12:B14').format.wrapText=true;summary.getRange('A14:F14').format.rowHeight=60;
summary.getRange('A12:F14').format.verticalAlignment='center';
const preview=path.join(root,'analysis/previews');await fs.mkdir(preview,{recursive:true});
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'현황!A4:F11',include:'values,formulas',tableMaxRows:9,tableMaxCols:6,maxChars:2200})).ndjson);
const countValues=summary.getRange('B5:B8').values.flat();
const expected=['source_only','gap','verified_unit','verified_field'].map(s=>req.filter(r=>r.status===s).length);
if(JSON.stringify(countValues)!==JSON.stringify(expected))throw new Error('Summary status counts do not reconcile');
const row=5, status=wb.worksheets.getItem('요구사항').getRange(`F${row}`);const saved=status.values;
status.values=[['실기기 통과']];wb.recalculate();
if(summary.getRange('B8').values[0][0]!==expected[3]+(saved[0][0]==='실기기 통과'?0:1))throw new Error('Status update does not recalculate');
status.values=saved;wb.recalculate();
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!',options:{useRegex:true,maxResults:20},maxChars:1500})).ndjson);
for(const s of process.argv.includes('--previews')?[summary,...sheets]:[]){
 const image=await wb.render({sheetName:s.name,range:s===summary?'A1:F14':'A1:F7',scale:1,format:'png'});
 await fs.writeFile(path.join(preview,s.name+'.png'),new Uint8Array(await image.arrayBuffer()));
}
const output=path.join(root,'analysis/outputs/01a13365-enterprise');await fs.mkdir(output,{recursive:true});
const file=await SpreadsheetFile.exportXlsx(wb);await file.save(path.join(output,'MCP_기업호환성_검증대장.xlsx'));
await fs.writeFile(path.join(root,'analysis/workbook-manifest.json'),JSON.stringify({format:'xlsx',sheets:['현황',...sheets.map(s=>s.name)],requirements:req.length,
 functions:functions.length,comparisons:comp.length,integration_conditions:cases.length,real_mcp_candidates:mcps.length,
 output_path:'analysis/outputs/01a13365-enterprise/MCP_기업호환성_검증대장.xlsx',summary_counts:expected,source_head:code.metadata.head},null,2)+'\n');
console.log('EXPORTED '+path.join(output,'MCP_기업호환성_검증대장.xlsx'));
