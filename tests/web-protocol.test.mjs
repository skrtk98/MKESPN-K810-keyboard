import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {K810,CONTROLS,KEY_GROUPS,CONFIG_SIZE,offset,packet,writePackets,hex,baseFromHeader,backupOf,parseBackup,keymapOnly,
  WHEEL_ACTIONS,WHEEL_OFFSET,wheelValue,setWheel,settingsOnly,diffSettings} from '../web/protocol.mjs';
const vectors=JSON.parse(await readFile(new URL('./vendor_vectors.json',import.meta.url)));
const applyVectors=JSON.parse(await readFile(new URL('./vendor_apply_vectors.json',import.meta.url)));
const extendedVectors=JSON.parse(await readFile(new URL('./vendor_extended_vectors.json',import.meta.url)));
import {compileMacro,decodeMacro,macroEntry,planMacro,extendedBlocks} from '../web/macros.mjs';
import {LIGHT_MODES,decodeLight,setLight,lightBlocks} from '../web/lighting.mjs';
import {MacroRecorder,recordedKey} from '../web/recording.mjs';
import {parseLibrary,persistLibrary} from '../web/library.mjs';
const noWait=async()=>{};

test('recorded timing belongs to the preceding operation and stopping releases held keys',()=>{
  const recorder=new MacroRecorder(),key=recordedKey('KeyA');
  recorder.append({type:'key-down',key},100);
  const events=recorder.finish(1100);
  assert.equal(events[0].delay,1000);assert.equal(events[1].type,'key-up');
  assert.doesNotThrow(()=>compileMacro({events}));
  assert.equal(recordedKey('Numpad0'),98);assert.equal(recordedKey('ControlRight'),228);
  assert.throws(()=>recorder.append({type:'delay'},Number.MAX_VALUE),/上限/);
});

test('macro library validates imported executable specs and failed storage keeps source intact',()=>{
  const source={format:'mkespn-k810-macro-library-v1',groups:[{id:'group',name:'test',macros:[{id:'macro',name:'click',spec:{events:[{type:'mouse-down',button:'left'},{type:'mouse-up',button:'left'}]}}]}]};
  assert.deepEqual(parseLibrary(source),source);
  assert.throws(()=>persistLibrary({setItem(){throw new Error('quota');}},source),/quota/);
  assert.equal(source.groups[0].macros.length,1);
  const bad=structuredClone(source);bad.groups[0].macros[0].spec.events.pop();
  assert.throws(()=>parseLibrary(bad),/離す/);
});

test('mouse button codes follow original insertion handlers rather than display conversion',async()=>{
  const vectors=JSON.parse(await readFile(new URL('./vendor_mouse_handler_vectors.json',import.meta.url)));
  for(const entry of vectors.cases) {
    const {payload}=compileMacro({events:[{type:'mouse-down',button:entry.button},{type:'mouse-up',button:entry.button}]});
    assert.equal(payload[entry.down?3:5],entry.code);
    assert.equal(entry.event_type,entry.down?1:2);
  }
});

test('Light-tab fields match 25 original x86 Apply fixtures',async()=>{
  const vectors=JSON.parse(await readFile(new URL('./vendor_lighting_vectors.json',import.meta.url)));
  for(const vector of vectors.cases) {
    const config=new Uint8Array(248);
    for(const block of vector.blocks)config.set(Buffer.from(block.data,'hex'),block.write_address-0xe0);
    const decoded=decodeLight(config);
    for(const [key,value] of Object.entries(vector.fields))assert.deepEqual(decoded[key],value);
    const {mode_code,...fields}=vector.fields;
    const updated=setLight(new Uint8Array(248).fill(170),{...fields,mode:LIGHT_MODES[mode_code][0]});
    for(const [key,value] of Object.entries(vector.fields))assert.deepEqual(decodeLight(updated)[key],value);
    assert.equal(updated[0],170);
    for(let i=2;i<=14;i+=2)assert.equal(updated[i]&240,160);
  }
});

test('LED macro pattern records and relocation match the original serializer',async()=>{
  const vectors=JSON.parse(await readFile(new URL('./vendor_macro_extension_vectors.json',import.meta.url)));
  for(const entry of vectors.cases.filter(e=>e.code===0xf9)) {
    const raw=Buffer.from(entry.led_hex,'hex'),sequence=[];
    for(let i=4;i<raw.length;i+=4)sequence.push({mode:LIGHT_MODES[raw[i]][0],color:raw[i+1],duration_ms:raw[i+2]*100});
    const spec={events:[{type:'led',behavior:entry.types[0]-13,sequence}]};
    const result=compileMacro(spec,0x240);
    assert.equal(hex(result.payload),entry.writes.filter(w=>w.write_address>=0x240).map(w=>w.data).join(''));
    const first=planMacro(macroDevice().memory,0xe0,offset('kp1'),spec),second=planMacro(first.image,0xe0,offset('kp2'),{events:[{type:'delay'}]});
    assert.deepEqual(second.image.slice(0x240,0x240+result.payload.length),first.image.slice(0x240,0x240+result.payload.length));
  }
});

test('Light write guard preserves shared bits and rejects invalid values',()=>{
  const before=new Uint8Array(248).fill(170),after=setLight(before,{mode:'off'});
  assert.deepEqual(lightBlocks(before,after),[24]);
  after[0]^=1;assert.throws(()=>lightBlocks(before,after),/照明以外/);
  assert.throws(()=>setLight(before,{speed:7}),/整数/);
  assert.throws(()=>setLight(before,{colors_enabled:0}),/整数/);
});

test('explicit Light save verifies configuration and ordinary imports preserve lighting',async()=>{
  const device=new MockDevice(),session=new K810(device,{wait:noWait}),snapshot=await session.snapshot();
  const draft=snapshot.data.slice();draft[1]^=255;
  assert.equal(settingsOnly(snapshot.data,draft)[1],snapshot.data[1]);
  const fields={mode:'constant',brightness:3,colors:Array.from({length:7},()=>[255,15,15])};
  let recovery;
  const result=await session.apply(snapshot,snapshot.data,async d=>{recovery=d;},fields);
  assert.deepEqual(result.data,setLight(snapshot.data,fields));
  assert.equal(recovery.data_hex,hex(snapshot.data));
});

test('combined Light and macro save keeps flags and uses full verification',async()=>{
  const device=macroDevice(),session=new K810(device,{wait:noWait}),snapshot=await session.snapshot();
  const spec={events:[{type:'mouse-down',button:'left'},{type:'mouse-up',button:'left'}]};
  const result=await session.applyExtended(snapshot,snapshot.data,new Map([['kp1',spec]]),null,async()=>{}, {mode:'constant',brightness:6});
  assert.equal(decodeLight(result.data).mode,'constant');assert.equal(result.data[0],snapshot.data[0]);
  const bad=result.image.slice();bad[snapshot.base]^=1;
  assert.throws(()=>extendedBlocks(result.image,bad,snapshot.base,true),/許可/);
});

class MockDevice {
  constructor() {
    this.vendorId=0x30fa;this.productId=0x2350;this.opened=true;
    this.collections=[{usagePage:0xff01,usage:1,featureReports:[{reportId:7}]}];
    this.memory=new Uint8Array(8192).fill(255);
    this.memory.set([0xe1,0x1e,0xe0,0,0xf0,0x0f,0,0],0xd0);
    this.memory.set(Array.from({length:CONFIG_SIZE},(_,i)=>i%255),0xe0);
    this.trace=[];this.staged=[];this.readAt=0;this.commits=0;
    this.operatingFlags=this.memory[0xe0];this.writes=[];
  }
  async sendFeatureReport(id,bytes) {
    const b=Uint8Array.from([id,...bytes]);this.trace.push({set:hex(b)});
    assert.equal(bytes.length,7);
    const address=b[4]+b[5]*256;
    if(b[1]===9) this.operatingFlags=b[2];
    if(b[1]!==0x18) return;
    if(b[2]===3) this.staged[b[3]]=b[6];
    if(b[2]===5) this.readAt=address+b[3];
    if(b[2]===9) {
      this.memory.set(this.staged.slice(0,b[7]+1),address);this.commits++;
      this.writes.push({address,data:this.memory.slice(address,address+b[7]+1)});
      if(address===0xe0) this.operatingFlags=this.memory[0xe0];
    }
  }
  async receiveFeatureReport(id) {
    this.trace.push({get:8});
    return new DataView(Uint8Array.of(id,this.memory[this.readAt],0,0,0,0,0,0).buffer);
  }
}
test('write packets match the original app x86 vectors',()=>{
  assert.deepEqual(writePackets(vectors.address,Uint8Array.from(Buffer.from(vectors.data,'hex'))).map(b=>({set:hex(b)})),vectors.write);
});
test('WebHID read matches original app vectors and excludes report ID when sending',async()=>{
  const device=new MockDevice(); device.memory.set(Buffer.from(vectors.data,'hex'),vectors.address);
  const api=new K810(device,{wait:noWait});
  assert.equal(hex(await api.read(vectors.address,8)),vectors.data);
  assert.deepEqual(device.trace,vectors.read);
  assert.equal(device.commits,0);
});
test('read the base from the signed EEPROM header without a variable-length WebHID call',async()=>{
  const api=new K810(new MockDevice(),{wait:noWait});
  assert.equal((await api.snapshot()).base,0xe0);
  assert.throws(()=>baseFromHeader(new Uint8Array(8)),/ヘッダー/);
  assert.throws(()=>baseFromHeader(Uint8Array.of(0xe1,0x1e,0xff,0x1f,0xf0,0x0f,0,0)),/領域/);
});
test('save only selected key bytes, preserve neighboring rows and all other configuration',async()=>{
  const device=new MockDevice(),api=new K810(device,{wait:noWait});
  const before=await api.snapshot(),draft=before.data.slice();draft[offset('kp1')]=104;draft[offset('up')]=26;
  // An imported or tampered draft cannot modify RGB, wheel or another matrix row.
  draft[0]=200;draft[offset('kp1')+1]=3;draft[0xc8]=8;
  let recovery;
  const after=await api.apply(before,draft,async doc=>{recovery=doc;});
  assert.deepEqual(after.data,keymapOnly(before.data,draft));assert.equal(device.commits,3);
  assert.deepEqual(device.writes[0],{address:before.base,data:before.data.slice(0,8)});
  assert.equal(device.operatingFlags,before.data[0]);
  assert.deepEqual((await parseBackup(recovery)).data,before.data);
});
test('refuse stale snapshots before committing writes',async()=>{
  const device=new MockDevice(),api=new K810(device,{wait:noWait}),before=await api.snapshot();
  device.memory[before.base+3]^=1;
  const draft=before.data.slice();draft[offset('kp1')]=104;
  await assert.rejects(api.apply(before,draft,async()=>{}),/再読み取り/);assert.equal(device.commits,0);
});
test('backup persistence failure prevents every EEPROM commit',async()=>{
  const device=new MockDevice(),api=new K810(device,{wait:noWait}),before=await api.snapshot();
  const draft=before.data.slice();draft[offset('kp1')]=104;
  await assert.rejects(api.apply(before,draft,async()=>{throw new Error('storage full');}),/storage full/);
  assert.equal(device.commits,0);
});
test('a transport failure releases the exclusive operation guard',async()=>{
  const api=new K810(new MockDevice(),{wait:noWait});
  await assert.rejects(api.exclusive(async()=>{throw new Error('disconnected');}));
  assert.equal(api.active,false);
  assert.equal(await api.exclusive(async()=>42),42);
});
test('reject corrupt and cross-device backup files',async()=>{
  const api=new K810(new MockDevice(),{wait:noWait}),doc=await backupOf(await api.snapshot());
  await assert.rejects(parseBackup({...doc,sha256:'bad'}),/チェックサム/);
  await assert.rejects(parseBackup({...doc,vendor_id:123}),/バックアップ/);
});
test('matrix offsets match original serializer',()=>{
  for(const [id] of CONTROLS) {
    const col=(offset(id)-0x48)/8;
    assert.equal(vectors.table[col].address,0xe0+offset(id));
    assert.equal(Buffer.from(vectors.table[col].data,'hex')[0],col);
  }
});
test('refuse malformed feature responses and unsupported collections',async()=>{
  const device=new MockDevice(),api=new K810(device,{wait:noWait});
  device.receiveFeatureReport=async()=>new DataView(new ArrayBuffer(7));
  await assert.rejects(api.getByte(),/Report形式/);
  device.vendorId=1;await assert.rejects(api.open(),/インターフェース/);
});
test('wheel nibble packing matches original x86 packer and one-byte write',()=>{
  assert.deepEqual(writePackets(0x100,Uint8Array.of(0x23)).map(b=>({set:hex(b)})),vectors.wheel_write);
  for(const entry of vectors.wheel_packing) {
    let data=new Uint8Array(CONFIG_SIZE);
    data=setWheel(setWheel(data,'up',entry.up),'down',entry.down);
    assert.equal(hex(data.slice(WHEEL_OFFSET,WHEEL_OFFSET+1)),entry.data);
  }
  assert.deepEqual(WHEEL_ACTIONS.map(a=>a[0]),[0,1,2,3,7,8,9,10]);
});
test('wheel save replays control block to activate settings and commits one wheel byte',async()=>{
  const device=new MockDevice(),api=new K810(device,{wait:noWait});
  device.memory[0xe0+WHEEL_OFFSET]=0x10;
  const before=await api.snapshot();
  const draft=setWheel(setWheel(before.data,'up',2),'down',3);
  const after=await api.apply(before,draft,async()=>{});
  assert.equal(diffSettings(before.data,draft).length,2);
  assert.equal(device.commits,2);assert.equal(after.data[WHEEL_OFFSET],0x23);
  assert.deepEqual(device.writes,[{address:before.base,data:before.data.slice(0,8)},{address:before.base+WHEEL_OFFSET,data:Uint8Array.of(0x23)}]);
  assert.equal(device.operatingFlags,before.data[0]);
  assert.deepEqual(after.data.slice(0,WHEEL_OFFSET),before.data.slice(0,WHEEL_OFFSET));
  assert.deepEqual(after.data.slice(WHEEL_OFFSET+1),before.data.slice(WHEEL_OFFSET+1));
  assert.equal(api.configurationActive,false);
  assert.deepEqual(device.trace.slice(-3).map(x=>x.set),['0718110000000000','0718000000000000','0720000000000000']);
});

test('activation prelude follows the full original Apply trace for both KEYSMODE values',async()=>{
  assert.equal(applyVectors.source_sha256,vectors.source_sha256);
  for(const name of ['synthetic_apply','keys_mode_zero']) {
    const trace=applyVectors[name],writes=trace.filter(x=>'write_address' in x);
    assert.equal(trace[0].set,'0709410000000000');
    const control=writes.find(x=>x.write_address===0xe0),wheel=writes.find(x=>x.write_address===0x100);
    assert.ok(writes.indexOf(control)<writes.indexOf(wheel));
    const device=new MockDevice();device.memory.set(Buffer.from(control.data,'hex'),0xe0);
    device.memory[0x100]=0x10;
    const api=new K810(device,{wait:noWait}),before=await api.snapshot();
    await api.apply(before,setWheel(setWheel(before.data,'up',2),'down',3),async()=>{});
    assert.deepEqual(device.writes.map(x=>({write_address:x.address,data:hex(x.data)})),[control,wheel]);
    assert.equal(device.operatingFlags,parseInt(control.data.slice(0,2),16));
    const current=await api.snapshot(),commits=device.commits;
    await api.apply(current,current.data,async()=>{throw new Error('No backup required for noop');});
    assert.equal(device.commits,commits);
  }
});
test('each wheel edit preserves opposite direction and rejects unsupported backup values',()=>{
  const original=new Uint8Array(CONFIG_SIZE);original[WHEEL_OFFSET]=0x10;
  for(const direction of ['up','down']) for(const [code] of WHEEL_ACTIONS) {
    const after=setWheel(original,direction,code),opposite=direction==='up'?'down':'up';
    assert.equal(wheelValue(after,opposite),wheelValue(original,opposite));
  }
  const draft=original.slice();draft[WHEEL_OFFSET]=0xff;
  assert.throws(()=>settingsOnly(original,draft),/ホイール設定/);
});
test('read-only snapshot exits configuration mode even for an invalid header',async()=>{
  const device=new MockDevice(),api=new K810(device,{wait:noWait});
  device.memory[0xd0]=0;
  await assert.rejects(api.snapshot(),/ヘッダー/);
  assert.equal(device.commits,0);
  assert.deepEqual(device.trace.slice(-3).map(x=>x.set),['0718110000000000','0718000000000000','0720000000000000']);
});

function macroDevice() {
  const device=new MockDevice();device.memory[0xfe]=0xd8;device.memory[0xff]=1;
  device.memory.fill(255,0x128,0x1c8);device.memory[0x128]=20;device.memory[0x130]=26;
  device.memory.fill(0,0x1d8,0x240);return device;
}

test('read existing key, mouse, scroll, movement and LED macros without changing memory',()=>{
  const samples=[
    {mode:'while-held',events:[{type:'key-down',key:104,delay:96},{type:'key-up',key:104,delay:96}]},
    {mode:'until-click',events:[{type:'mouse-down',button:'right'},{type:'mouse-up',button:'right'}]},
    {events:[{type:'scroll',steps:-3},{type:'move',x:-24,y:12}]},
    {events:[{type:'led',sequence:[{mode:'off',color:1,duration_ms:1000},{mode:'constant',color:2,duration_ms:2000}]}]}
  ];
  for(const spec of samples) {
    const initial=macroDevice().memory,before=initial.slice();
    const plan=planMacro(initial,0xe0,offset('kp1'),spec),copy=plan.image.slice();
    const decoded=decodeMacro(plan.image,0xe0,offset('kp1'));
    const address=plan.image[0x1da]+(plan.image[0x1db]&63)*256;
    assert.deepEqual(compileMacro(decoded,address).payload,compileMacro(spec,address).payload);
    assert.equal(decoded.mode,spec.mode??'repeat');
    assert.deepEqual(plan.image,copy);assert.deepEqual(initial,before);
    const invalid=copy.slice();invalid[0x1db]|=64;
    assert.throws(()=>decodeMacro(invalid,0xe0,offset('kp1')));
  }
  const modes=Object.fromEntries(extendedVectors.repeat_buttons.map(v=>[v.button,v.mode]));
  assert.equal(compileMacro(samples[0]).mode,modes[10]);assert.equal(compileMacro(samples[1]).mode,modes[11]);
});
test('media/lighting actions and macro bytes match original x86 fixtures',()=>{
  assert.deepEqual(KEY_GROUPS.slice(-2).flatMap(g=>g[1].map(x=>x[0])).sort((a,b)=>a-b),extendedVectors.actions.filter(a=>a.unique_index!==18).map(a=>a.code).sort((a,b)=>a-b));
  for(const vector of extendedVectors.macros) {
    const spec={...vector.spec,events:vector.spec.events.map(e=>e.type.startsWith('key-')?{...e,key:e.code}:e.type.startsWith('mouse-')?{...e,button:{241:'left',243:'right',242:'middle'}[e.code]}:e)};
    const {payload,count,mode}=compileMacro(spec);
    assert.equal(hex(payload),vector.payload);assert.equal(hex(macroEntry(0x240,count,mode)),vector.descriptor);
  }
});
test('macro apply saves full recovery, activates descriptor and verifies all EEPROM bytes',async()=>{
  const device=macroDevice(),api=new K810(device,{wait:noWait}),before=await api.snapshot();let recovery;
  const spec={events:[{type:'mouse-down',button:'left'},{type:'mouse-up',button:'left'}]};
  const after=await api.applyExtended(before,before.data,new Map([['kp1',spec]]),null,async doc=>recovery=doc);
  assert.equal(after.data[offset('kp1')],0xa5);assert.equal(device.memory[0x1d8],7);
  assert.equal(device.memory[0x240],1);assert.equal(device.memory[0x243],0xf1);
  const saved=await parseBackup(recovery);assert.equal(saved.image.length,8192);
  const restored=await api.applyExtended(after,saved.data,new Map(),saved.image,async()=>{});
  assert.deepEqual(restored.image,saved.image);
});
test('macro allocation preserves every referenced macro and rejects unknown referenced formats',()=>{
  const device=macroDevice(),before=device.memory.slice(),spec={events:[{type:'scroll',steps:-1}]};
  const first=planMacro(before,0xe0,offset('kp1'),spec),second=planMacro(first.image,0xe0,offset('kp2'),spec);
  assert.equal(first.slot,0);assert.equal(second.slot,1);
  assert.deepEqual(second.image.slice(0x240,0x248),first.image.slice(0x240,0x248));
  const bad=first.image.slice();bad[0x1d8]=0;
  assert.throws(()=>planMacro(bad,0xe0,offset('kp2'),spec),/形式/);
  const rgb=before.slice();rgb[0xe0+33]^=1;assert.throws(()=>extendedBlocks(before,rgb,0xe0),/領域/);
});
test('macro storage failure aborts before every commit and full backup corruption is rejected',async()=>{
  const device=macroDevice(),api=new K810(device,{wait:noWait}),before=await api.snapshot();
  await assert.rejects(api.applyExtended(before,before.data,new Map([['kp1',{events:[{type:'scroll',steps:1}]}]]),null,async()=>{throw new Error('storage full');}),/storage full/);
  assert.equal(device.commits,0);
  const backup=await backupOf(await api.fullSnapshot());
  await assert.rejects(parseBackup({...backup,eeprom_sha256:'bad'}),/完全バックアップ/);
});
test('macro editor rejects held keys, invalid parameters and unsupported event types',()=>{
  assert.throws(()=>compileMacro({events:[{type:'key-down',key:'a'}]}),/離す/);
  assert.throws(()=>compileMacro({events:[{type:'move',x:999999,y:0}]}),/横移動/);
  assert.throws(()=>compileMacro({events:[{type:'key-up',key:4.5}]}),/不正/);
  assert.throws(()=>compileMacro({events:[{type:'unknown'}]}),/未対応/);
});
