import {issuer} from './config.js';
let token='';
const status=document.querySelector('#status');
const redirect=location.origin+'/';
const b64=bytes=>btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
document.querySelector('#login').onclick=async()=>{
 const verifier=b64(crypto.getRandomValues(new Uint8Array(32)));
 const state=b64(crypto.getRandomValues(new Uint8Array(24)));
 sessionStorage.setItem('oidc_verifier',verifier);sessionStorage.setItem('oidc_state',state);
 const challenge=b64(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier))));
 const q=new URLSearchParams({client_id:'mcp-gateway',response_type:'code',scope:'openid',redirect_uri:redirect,state,code_challenge:challenge,code_challenge_method:'S256'});
 location.href=issuer+'/protocol/openid-connect/auth?'+q;
};
document.querySelector('#logout').onclick=()=>{token='';location.href=issuer+'/protocol/openid-connect/logout?'+new URLSearchParams({client_id:'mcp-gateway',post_logout_redirect_uri:redirect});};
async function api(path,options={}){
 const r=await fetch('/api'+path,{...options,headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'}});
 if(!r.ok)throw new Error('요청 실패 ('+r.status+')');return r.json();
}
async function refresh(){
 const tools=await api('/tools');const rows=Array.isArray(tools)?tools:(tools.tools||[]);
 document.querySelector('#tools').replaceChildren();
 for(const tool of rows){const tr=document.createElement('tr');
 for(const text of [tool.server,tool.tool,tool.approved?'허용':'차단']){const td=document.createElement('td');td.textContent=text;tr.append(td);}
 const td=document.createElement('td'),btn=document.createElement('button');btn.textContent=tool.approved?'차단':'허용';btn.onclick=async()=>{try{await api('/tools/'+encodeURIComponent(tool.server)+'/'+encodeURIComponent(tool.tool),{method:'PUT',body:JSON.stringify({approved:!tool.approved})});await refresh();}catch(e){status.textContent=e.message;}};td.append(btn);tr.append(td);document.querySelector('#tools').append(tr);}
 document.querySelector('#events').textContent=JSON.stringify(await api('/events'),null,2);
}
try{
 const q=new URLSearchParams(location.search);
 if(q.has('code')){
  if(q.get('state')!==sessionStorage.getItem('oidc_state'))throw Error('로그인 상태가 일치하지 않습니다.');
  const verifier=sessionStorage.getItem('oidc_verifier');sessionStorage.removeItem('oidc_verifier');sessionStorage.removeItem('oidc_state');
  history.replaceState({},'',redirect);
  const r=await fetch(issuer+'/protocol/openid-connect/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'authorization_code',client_id:'mcp-gateway',code:q.get('code'),redirect_uri:redirect,code_verifier:verifier})});
  if(!r.ok)throw Error('로그인에 실패했습니다.');token=(await r.json()).access_token;
  document.querySelector('#login').hidden=true;document.querySelector('#logout').hidden=false;status.textContent='로그인했습니다.';await refresh();
 }
}catch(e){status.textContent=e.message;}
