import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

test('discussion view shows real addressed exchanges and keeps reply linkage', () => {
  const script = readFileSync(new URL('./static/app.js', import.meta.url), 'utf8');
  const start = script.indexOf('function renderDiscussions()');
  const end = script.indexOf('\nfunction ', start + 1);
  let shown;
  const panel={children:[],replaceChildren(...children){this.children=children;},append(child){this.children.push(child);}};
  const context = vm.createContext({
    $: id => id === 'discussion-search' ? {value:'COORD'} : panel,
    node:(tag,className,text)=>({tag,text}),
    renderChanged:(key,inputs,draw)=>draw(),
    state:{worker:{handoffs:[{task:'COORD',model:'opus-fixture',state:'waiting_quota',round:1}]},events:[
      {id:1,author:'Codex',kind:'message',task_id:'COORD',to:'Claude',body:'request'},
      {id:2,author:'Claude',kind:'message',task_id:'COORD',to:'Codex',reply_to:1,body:'change requested'},
      {id:3,author:'System',kind:'message',task_id:'COORD',to:'All',body:'poll'},
      {id:4,author:'Claude',kind:'message',task_id:'MAIN',to:'All',body:'COORD git summary'},
      {id:5,author:'Gemini',kind:'message',task_id:'OTHER',to:'Codex',body:'unrelated'},
      {id:6,author:'System',kind:'message',task_id:'COORD',to:'Claude',body:'stored real request',source_id:'handoff-request-message-1'},
    ]},
    eventMatchesFilter:(event,author,query)=>(event.body+' '+event.task_id).toLowerCase().includes(query),
    renderFeed:(container,events)=>{shown=events;},
  });
  vm.runInContext(script.slice(start,end)+'\nrenderDiscussions()',context);
  assert.deepEqual(Array.from(shown,e=>e.id),[1,2,6]);
  assert.equal(shown[1].reply_to,1);
  assert.match(panel.children[1].text,/한도 회복 대기/);
  const html=readFileSync(new URL('./static/index.html', import.meta.url),'utf8');
  assert.match(html,/data-channel="discussions"/);
  assert.match(html,/id="discussion-feed"[^>]*aria-live="polite"/);
});
