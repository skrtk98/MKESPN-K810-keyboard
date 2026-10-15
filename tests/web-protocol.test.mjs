import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {K810,CONTROLS,CONFIG_SIZE,offset,packet,writePackets,hex,baseFromHeader,backupOf,parseBackup,keymapOnly,
  WHEEL_ACTIONS,WHEEL_OFFSET,wheelValue,setWheel,settingsOnly,diffSettings} from '../web/protocol.mjs';
const vectors=JSON.parse(await readFile(new URL('./vendor_vectors.json',import.meta.url)));
const noWait=async()=>{};

class MockDevice {
  constructor() {
    this.vendorId=0x30fa;this.productId=0x2350;this.opened=true;
    this.collections=[{usagePage:0xff01,usage:1,featureReports:[{reportId:7}]}];
    this.memory=new Uint8Array(8192).fill(255);
    this.memory.set([0xe1,0x1e,0xe0,0,0xf0,0x0f,0,0],0xd0);
    this.memory.set(Array.from({length:CONFIG_SIZE},(_,i)=>i%255),0xe0);
    this.trace=[];this.staged=[];this.readAt=0;this.commits=0;
  }
  async sendFeatureReport(id,bytes) {
    const b=Uint8Array.from([id,...bytes]);this.trace.push({set:hex(b)});
    assert.equal(bytes.length,7);
    const address=b[4]+b[5]*256;
    if(b[1]!==0x18) return;
    if(b[2]===3) this.staged[b[3]]=b[6];
    if(b[2]===5) this.readAt=address+b[3];
    if(b[2]===9) {this.memory.set(this.staged.slice(0,b[7]+1),address);this.commits++;}
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
  assert.deepEqual(after.data,keymapOnly(before.data,draft));assert.equal(device.commits,2);
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
test('both wheel directions are committed as exactly one byte with no other changes',async()=>{
  const device=new MockDevice(),api=new K810(device,{wait:noWait});
  device.memory[0xe0+WHEEL_OFFSET]=0x10;
  const before=await api.snapshot();
  const draft=setWheel(setWheel(before.data,'up',2),'down',3);
  const after=await api.apply(before,draft,async()=>{});
  assert.equal(diffSettings(before.data,draft).length,2);
  assert.equal(device.commits,1);assert.equal(after.data[WHEEL_OFFSET],0x23);
  assert.deepEqual(after.data.slice(0,WHEEL_OFFSET),before.data.slice(0,WHEEL_OFFSET));
  assert.deepEqual(after.data.slice(WHEEL_OFFSET+1),before.data.slice(WHEEL_OFFSET+1));
  assert.equal(api.configurationActive,false);
  assert.deepEqual(device.trace.slice(-3).map(x=>x.set),['0718110000000000','0718000000000000','0720000000000000']);
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
