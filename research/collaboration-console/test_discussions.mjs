import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

test('discussion view shows real addressed exchanges and keeps reply linkage', () => {
  const script = readFileSync(new URL('./static/app.js', import.meta.url), 'utf8');
  const start = script.indexOf('function renderDiscussions()');
  const end = script.indexOf('\nfunction ', start + 1);
  let shown;
  const context = vm.createContext({
    $: id => id === 'discussion-search' ? {value:'COORD'} : {},
    state:{events:[
      {id:1,author:'Codex',kind:'message',task_id:'COORD',to:'Claude',body:'request'},
      {id:2,author:'Claude',kind:'message',task_id:'COORD',to:'Codex',reply_to:1,body:'change requested'},
      {id:3,author:'System',kind:'message',task_id:'COORD',to:'All',body:'poll'},
      {id:4,author:'Claude',kind:'message',task_id:'MAIN',to:'All',body:'COORD git summary'},
      {id:5,author:'Gemini',kind:'message',task_id:'OTHER',to:'Codex',body:'unrelated'},
    ]},
    eventMatchesFilter:(event,author,query)=>(event.body+' '+event.task_id).toLowerCase().includes(query),
    renderFeed:(container,events)=>{shown=events;},
  });
  vm.runInContext(script.slice(start,end)+'\nrenderDiscussions()',context);
  assert.deepEqual(Array.from(shown,e=>e.id),[1,2]);
  assert.equal(shown[1].reply_to,1);
  const html=readFileSync(new URL('./static/index.html', import.meta.url),'utf8');
  assert.match(html,/data-channel="discussions"/);
  assert.match(html,/id="discussion-feed"[^>]*aria-live="polite"/);
});
