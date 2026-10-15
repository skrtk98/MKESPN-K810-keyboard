import {K810,CONTROLS,KEY_GROUPS,CONFIG_SIZE,keyLabel,offset,diffKeys,keymapOnly,backupOf,parseBackup} from './protocol.mjs';

const $=id=>document.getElementById(id);
const RECOVERY_KEY='mkespn-k810:recovery:v1';
let session=null, snapshot=null, draft=null, selected='kp1', demo=false, busy=false, uncertain=false, recoveryDoc=null;
const keyButtons=new Map();

function message(text,type='info') { $('status').textContent=text; $('status').className=`notice ${type}`; }
function render() {
  const hasData=!!snapshot, changes=hasData?diffKeys(snapshot.data,draft):[];
  for(const [id,label] of CONTROLS) {
    const button=keyButtons.get(id), code=hasData?draft[offset(id)]:null;
    button.querySelector('.key-name').textContent=code===null?'—':keyLabel(code);
    button.setAttribute('aria-pressed',String(selected===id));
    button.setAttribute('aria-label',`${label}、${code===null?'未読み取り':keyLabel(code)}${hasData&&code!==snapshot.data[offset(id)]?'、未保存':''}`);
    button.classList.toggle('changed',hasData&&code!==snapshot.data[offset(id)]);
    button.disabled=busy;
  }
  $('editor-title').textContent=CONTROLS.find(c=>c[0]===selected)[1];
  $('current-key').textContent=hasData?keyLabel(snapshot.data[offset(selected)]):'未読み取り';
  $('key-select').querySelectorAll('[data-extra]').forEach(o=>o.remove());
  if(hasData) {
    const code=draft[offset(selected)];
    if(!Array.from($('key-select').options).some(o=>Number(o.value)===code)) {
      const option=new Option(keyLabel(code),String(code)); option.dataset.extra='true'; $('key-select').add(option);
    }
    $('key-select').value=String(code);
  }
  $('key-select').disabled=busy||!hasData||uncertain;
  $('revert-key').disabled=busy||!hasData||draft[offset(selected)]===snapshot?.data[offset(selected)];
  $('apply').disabled=busy||demo||!session||!changes.length||uncertain;
  $('reset').disabled=busy||!changes.length;
  $('reload').disabled=busy||!session;
  $('export').disabled=busy||!hasData||demo||uncertain;
  $('import').disabled=busy||!hasData||demo||uncertain;
  $('recovery').disabled=busy||!recoveryDoc;
  $('connect').disabled=busy||!!session||!('hid' in navigator)||!window.isSecureContext;
  $('demo').disabled=busy||!!session;
  $('disconnect').hidden=!session;
  $('disconnect').disabled=busy;
  $('workspace').setAttribute('aria-busy',String(busy));
  $('mode-badge').textContent=demo?'デモ · 本体には保存されません':session?'実機の設定':'プレビュー';
  $('change-count').textContent=changes.length?`${changes.length}件の変更`:'変更なし';
  $('no-changes').hidden=changes.length>0;
  $('changes').replaceChildren(...changes.map(change=>{
    const li=document.createElement('li');
    for(const [tag,text] of [['span',change.label],['span',keyLabel(change.before)],['span','→'],['strong',keyLabel(change.after)]]) {
      const item=document.createElement(tag); item.textContent=text; li.append(item);
    }
    return li;
  }));
}
async function run(action,{writing=false}={}) {
  if(busy) return;
  busy=true; render();
  try { await action(); }
  catch(error) {
    if(writing) uncertain=true;
    if(error.name==='NotFoundError') message('機器の選択がキャンセルされました。');
    else message(`${error.message}${writing?' 保存前の復元データを取得し、本体から再読み取りしてください。':''}`,'error');
  } finally { busy=false; render(); }
}
async function usbLock(action) {
  if(!navigator.locks) throw new Error('このブラウザの排他制御に対応していません。PC版ChromeまたはEdgeを使用してください。');
  return navigator.locks.request('mkespn-k810-usb',{ifAvailable:true},lock=>{
    if(!lock) throw new Error('別のタブが通信中です。処理が終わってからお試しください。');
    return action();
  });
}
function download(doc,name) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}));
  const link=document.createElement('a'); link.href=url; link.download=name; link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function setSnapshot(value) { snapshot=value; draft=value.data.slice(); uncertain=false; }
async function reload() {
  message('本体の設定を読み取っています…');
  setSnapshot(await usbLock(()=>session.exclusive(()=>session.snapshot())));
  message('現在の設定を読み取りました。キーを選んで編集できます。','success');
}

for(const [id,label] of CONTROLS) {
  const button=document.createElement('button'); button.type='button'; button.className=`key ${id}`;
  button.setAttribute('aria-pressed','false');
  const name=document.createElement('span'); name.className='key-name';
  const position=document.createElement('span'); position.className='key-position'; position.textContent=label;
  button.append(name,position); button.addEventListener('click',()=>{selected=id;render();});
  (CONTROLS.findIndex(c=>c[0]===id)<12?$('keypad'):$('stick')).append(button);
  keyButtons.set(id,button);
}
for(const [label,keys] of KEY_GROUPS) {
  const group=document.createElement('optgroup'); group.label=label;
  for(const [code,name] of keys) group.append(new Option(name,String(code)));
  $('key-select').append(group);
}
$('key-select').addEventListener('change',()=>{if(!busy&&draft) {draft[offset(selected)]=Number($('key-select').value);render();}});
$('revert-key').addEventListener('click',()=>{draft[offset(selected)]=snapshot.data[offset(selected)];render();});
$('reset').addEventListener('click',()=>{draft=snapshot.data.slice();render();message('未保存の変更をすべて取り消しました。');});
$('connect').addEventListener('click',()=>run(async()=>{
  const devices=await navigator.hid.requestDevice({filters:[{vendorId:0x30fa,productId:0x2350,usagePage:0xff01,usage:1}]});
  console.info('WebHID selection',JSON.stringify(devices.map(d=>({vendorId:d.vendorId,productId:d.productId,collections:d.collections}))));
  const device=devices.find(d=>K810.matches(d));
  if(!device) throw new Error('対応するK810が選択されていません。');
  const candidate=new K810(device,{progress:(done,total)=>message(`本体の設定を読み取っています… ${Math.round(done/total*100)}%`)});
  try {
    await candidate.open();
    const value=await usbLock(()=>candidate.exclusive(()=>candidate.snapshot()));
    session=candidate; demo=false; setSnapshot(value);
    $('device-status').replaceChildren();
    const dot=document.createElement('span'); dot.className='status-dot';
    $('device-status').append(dot,'接続済み · USB Keyboard（30FA:2350）');
    $('device-status').className='connected';
    message('本体の設定を読み取りました。編集後に保存すると、本体の割り当てが変わります。','success');
  } catch(error) { if(device.opened) await device.close(); throw error; }
}));
$('disconnect').addEventListener('click',()=>run(async()=>{
  await session.device.close(); session=null; snapshot=null;draft=null;demo=false;uncertain=false;
  $('device-status').textContent='未接続';$('device-status').className='';message('キーボードとの接続を終了しました。');
}));
$('demo').addEventListener('click',()=>{
  if(busy||session) return;
  demo=true;
  const data=new Uint8Array(CONFIG_SIZE).fill(255);
  const codes=[20,26,8,21,41,4,22,7,40,43,44,6,80,79,81,82];
  CONTROLS.forEach(([id],i)=>data[offset(id)]=codes[i]);
  setSnapshot({base:0xe0,header:Uint8Array.of(0xe1,0x1e,0xe0,0,0xf0,0x0f,0,0),data});
  message('デモモードです。自由に編集できます。本体への通信・書き込みは行いません。');render();
});
$('reload').addEventListener('click',()=>run(reload));
$('apply').addEventListener('click',()=>run(async()=>{
  if(!session||demo||uncertain) throw new Error('本体へ接続し直してください。');
  message('設定を確認して保存しています。USBを抜かずにお待ちください…');
  const result=await usbLock(()=>session.apply(snapshot,draft,async doc=>{
    localStorage.setItem(RECOVERY_KEY,JSON.stringify(doc));
    recoveryDoc=doc;
  }));
  setSnapshot(result);
  message('本体に保存し、読み戻しが一致することを確認しました。実際にキーを押して動作を確認してください。','success');
},{writing:true}));
$('export').addEventListener('click',()=>run(async()=>download(await backupOf(snapshot),`k810-${new Date().toISOString().replace(/[:.]/g,'-')}.json`)));
$('recovery').addEventListener('click',()=>{if(recoveryDoc)download(recoveryDoc,'k810-before-save.json');});
$('import').addEventListener('click',()=>$('backup-file').click());
$('backup-file').addEventListener('change',()=>run(async()=>{
  const file=$('backup-file').files[0]; $('backup-file').value='';
  if(!file) return;
  if(file.size>16384) throw new Error('バックアップファイルが大きすぎます。');
  const value=await parseBackup(JSON.parse(await file.text()));
  if(value.base!==snapshot.base) throw new Error('本体とバックアップの設定位置が一致しません。');
  draft=keymapOnly(snapshot.data,value.data);
  message('復元内容を読み込みました。変更一覧を確認し、「キーボードに保存する」で適用してください。');
}));
window.addEventListener('beforeunload',event=>{if(busy||(snapshot&&diffKeys(snapshot.data,draft).length)) {event.preventDefault();event.returnValue='';}});
navigator.hid?.addEventListener('disconnect',event=>{
  if(event.device!==session?.device) return;
  session=null;uncertain=true;
  $('device-status').textContent='USB接続が切れました';$('device-status').className='';
  message('USB接続が切れました。復元データを取得できます。再接続して本体の状態を確認してください。','error');render();
});
try { const saved=localStorage.getItem(RECOVERY_KEY); if(saved) {const doc=JSON.parse(saved);await parseBackup(doc);recoveryDoc=doc;} } catch { /* Corrupt local recovery never becomes a writable configuration. */ }
if(!('hid' in navigator)||!window.isSecureContext) {
  $('compatibility').hidden=false;
  $('compatibility').textContent='この環境では実機に接続できません。PC版Chrome・EdgeでHTTPSのページを開いてください。デモはこのまま利用できます。';
}
render();
