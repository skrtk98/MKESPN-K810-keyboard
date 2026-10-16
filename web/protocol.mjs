import {planMacro,restoreMacroImage,extendedBlocks,MACRO_CODES} from './macros.mjs?v=20261016-unified';
import {setLight,lightBlocks} from './lighting.mjs?v=20261016-unified';
export const CONFIG_SIZE = 248;
export const WHEEL_OFFSET = 0x20;
export const WHEEL_ACTIONS = [
  [0,'音量を上げる'],[1,'音量を下げる'],[2,'上にスクロール'],[3,'下にスクロール'],
  [7,'LED速度を上げる'],[8,'LED速度を下げる'],[9,'LEDを明るくする'],[10,'LEDを暗くする'],
];
export const wheelLabel = code => WHEEL_ACTIONS.find(a=>a[0]===code)?.[1] ?? `未対応の設定（${code}）`;
export function wheelValue(data,direction) {
  if(!['up','down'].includes(direction)) throw new Error('ホイール方向が不正です。');
  return (data[WHEEL_OFFSET]>>(direction==='up'?4:0))&15;
}
export function setWheel(data,direction,value) {
  if(!WHEEL_ACTIONS.some(a=>a[0]===value)) throw new Error('未対応のホイール設定です。');
  wheelValue(data,direction);
  const result=data.slice(),shift=direction==='up'?4:0;
  result[WHEEL_OFFSET]=(result[WHEEL_OFFSET]&(shift?15:240))|(value<<shift);
  return result;
}
export const CONTROLS = [
  ['kp1', '上段 1', 89], ['kp2', '上段 2', 90], ['kp3', '上段 3', 91],
  ['kp4', '上段 4', 92], ['kp5', '上段 5', 93], ['kp6', '中段 1', 94],
  ['kp7', '中段 2', 95], ['kp8', '中段 3', 96], ['enter', '右側の縦長キー', 40],
  ['tab', '左下の横長キー', 43], ['kp9', '下段 中央', 97], ['kp0', '下段 右', 98],
  ['left', 'スティック 左', 80], ['right', 'スティック 右', 79],
  ['down', 'スティック 下', 81], ['up', 'スティック 上', 82],
];
export const KEY_GROUPS = [
  ['文字', Array.from({length:26}, (_, i) => [i+4, String.fromCharCode(65+i)])],
  ['数字', [...Array.from({length:9}, (_, i) => [i+30, String(i+1)]), [39, '0']]],
  ['ファンクション', Array.from({length:24}, (_, i) => [i < 12 ? i+58 : i+92, `F${i+1}`])],
  ['操作', [[40,'Enter'],[41,'Escape'],[42,'Backspace'],[43,'Tab'],[44,'Space'],
    [45,'-'],[46,'='],[47,'['],[48,']'],[49,'\\'],[51,';'],[52,"'"],[53,'`'],[54,','],[55,'.'],[56,'/'],
    [57,'Caps Lock'],[70,'Print Screen'],[71,'Scroll Lock'],[72,'Pause'],[73,'Insert'],[74,'Home'],
    [75,'Page Up'],[76,'Delete'],[77,'End'],[78,'Page Down'],[79,'→'],[80,'←'],[81,'↓'],[82,'↑']]],
  ['テンキー', [[83,'Num Lock'],[84,'テンキー /'],[85,'テンキー *'],[86,'テンキー -'],[87,'テンキー +'],
    [88,'テンキー Enter'],...Array.from({length:9}, (_,i)=>[89+i,`テンキー ${i+1}`]),[98,'テンキー 0'],[99,'テンキー .']]],
  ['修飾キー', [[224,'左 Ctrl'],[225,'左 Shift'],[226,'左 Alt'],[227,'左 Windows / Command'],
    [228,'右 Ctrl'],[229,'右 Shift'],[230,'右 Alt'],[231,'右 Windows / Command']]],
  ['その他', [[0,'無効（出力なし）']]],
  ['メディア・アプリ', [[0xc9,'再生／一時停止'],[0xca,'音量を下げる'],[0xcb,'音量を上げる'],
    [0xcc,'次の曲'],[0xcd,'前の曲'],[0xce,'メディアプレーヤー'],[0xcf,'メール'],[0xd0,'ブラウザ 進む'],
    [0xd1,'ブラウザ 停止'],[0xd2,'ブラウザ 戻る'],[0xd3,'ブラウザ 更新'],[0xd4,'ブラウザ 検索'],
    [0xd5,'ブラウザ お気に入り'],[0xd6,'ミュート'],[0xd7,'マイコンピューター'],[0xd8,'再生を停止'],
    [0xd9,'電卓'],[0xda,'ブラウザ ホーム']]],
  ['照明操作', [[0xe8,'照明の色を切り替える'],[0xe9,'照明モードを切り替える'],[0xea,'照明を明るくする'],
    [0xeb,'照明を暗くする'],[0xec,'照明速度を上げる'],[0xed,'照明速度を下げる'],[0xf0,'照明をオン／オフ']]],
];
export const keyLabel = code => KEY_GROUPS.flatMap(g=>g[1]).find(k=>k[0]===code)?.[1] ?? (MACRO_CODES.includes(code)?`マクロ ${MACRO_CODES.indexOf(code)+1}`:`特殊キー 0x${code.toString(16).padStart(2,'0')}`);
export const hex = bytes => Array.from(bytes, b=>b.toString(16).padStart(2,'0')).join('');
export function fromHex(s) {
  if (typeof s !== 'string' || s.length % 2 || !/^[0-9a-f]*$/i.test(s)) throw new Error('バックアップのデータ形式が不正です。');
  return Uint8Array.from(s.match(/../g) ?? [], x=>parseInt(x,16));
}
export function offset(id) {
  const i = CONTROLS.findIndex(c=>c[0]===id);
  if (i < 0) throw new Error('未対応のキー位置です。');
  return 0x48 + i*8;
}
export const equal = (a,b) => a.length===b.length && a.every((v,i)=>v===b[i]);
export function packet(command=0,index=0,address=0,value=0,last=0) {
  if (!Number.isInteger(address) || address<0 || address>=8192) throw new Error('設定アドレスが範囲外です。');
  return Uint8Array.of(7,0x18,command,index,address&255,address>>8,value,last);
}
export function writePackets(address,data) {
  if (!data.length || data.length>32 || address+data.length>8192) throw new Error('書き込み範囲が不正です。');
  return [...Array.from(data,(b,i)=>packet(3,i,address,b,data.length-1)),
    packet(9,0,address,0,data.length-1),packet(1,0,address)];
}
export function baseFromHeader(header) {
  if (header.length!==8 || header[0]!==0xe1 || header[1]!==0x1e || header[4]!==0xf0 || header[5]!==0x0f) {
    throw new Error('K810の設定ヘッダーを確認できません。書き込みは行いません。');
  }
  const base=header[2]+256*header[3];
  if (base<0xd8 || base%8 || base+CONFIG_SIZE>8192) throw new Error('未対応の設定領域です。');
  return base;
}
export function diffKeys(before, after) {
  if (before.length!==CONFIG_SIZE || after.length!==CONFIG_SIZE) throw new Error('設定データの長さが不正です。');
  return CONTROLS.flatMap(([id,label])=>before[offset(id)]===after[offset(id)] ? [] :
    [{id,label,before:before[offset(id)],after:after[offset(id)]}]);
}
export function keymapOnly(before, draft) {
  const result=before.slice();
  for (const [id] of CONTROLS) result[offset(id)]=draft[offset(id)];
  return result;
}
export function settingsOnly(before,draft) {
  if(before.length!==CONFIG_SIZE || draft.length!==CONFIG_SIZE) throw new Error('設定データの長さが不正です。');
  let result=keymapOnly(before,draft);
  for(const direction of ['up','down']) {
    const value=wheelValue(draft,direction);
    if(value!==wheelValue(before,direction)) result=setWheel(result,direction,value);
  }
  return result;
}
export function diffSettings(before,after) {
  const changes=diffKeys(before,after);
  for(const direction of ['up','down']) {
    const oldValue=wheelValue(before,direction),newValue=wheelValue(after,direction);
    if(oldValue!==newValue) changes.push({id:`wheel-${direction}`,kind:'wheel',label:`ホイール ${direction==='up'?'上':'下'}方向`,before:oldValue,after:newValue});
  }
  return changes;
}
export async function checksum(data) {
  return hex(new Uint8Array(await crypto.subtle.digest('SHA-256',data)));
}
export async function backupOf(snapshot) {
  const doc={format:'mkespn-k810-config-v1',created_utc:new Date().toISOString(),vendor_id:0x30fa,product_id:0x2350,
    base:snapshot.base,metadata_hex:'',header_hex:hex(snapshot.header),data_hex:hex(snapshot.data),sha256:await checksum(snapshot.data)};
  if(snapshot.image) {doc.eeprom_hex=hex(snapshot.image);doc.eeprom_sha256=await checksum(snapshot.image);}
  return doc;
}
export async function parseBackup(doc) {
  if (doc?.format!=='mkespn-k810-config-v1' || doc.vendor_id!==0x30fa || doc.product_id!==0x2350 ||
      !Number.isInteger(doc.base) || doc.base<0xd8 || doc.base%8 || doc.base+CONFIG_SIZE>8192) {
    throw new Error('このK810用のバックアップではありません。');
  }
  const data=fromHex(doc.data_hex);
  if (data.length!==CONFIG_SIZE || await checksum(data)!==doc.sha256) throw new Error('バックアップのサイズまたはチェックサムが一致しません。');
  let image;
  if(doc.eeprom_hex!==undefined) {
    image=fromHex(doc.eeprom_hex);
    if(image.length!==8192||await checksum(image)!==doc.eeprom_sha256||!equal(image.slice(doc.base,doc.base+CONFIG_SIZE),data)) throw new Error('完全バックアップの照合に失敗しました。');
  }
  return {base:doc.base,data,image};
}

export class K810 {
  constructor(device,{wait=ms=>new Promise(resolve=>setTimeout(resolve,ms)),progress=()=>{}}={}) {
    this.device=device; this.wait=wait; this.progress=progress; this.active=false; this.configurationActive=false;
  }
  static matches(d) {
    return d.vendorId===0x30fa && d.productId===0x2350 &&
      d.collections.some(c=>c.usagePage===0xff01 && c.usage===1 && c.featureReports.some(r=>r.reportId===7));
  }
  async open() {
    if (!K810.matches(this.device)) throw new Error('対応するK810設定インターフェースがありません。');
    if (!this.device.opened) await this.device.open();
  }
  async send(bytes) {
    if([0x18,9].includes(bytes[1])) this.configurationActive=true;
    await this.device.sendFeatureReport(7,bytes.slice(1));
    if(bytes[1]===0x20) this.configurationActive=false;
  }
  async finishConfiguration() {
    if(!this.configurationActive) return;
    await this.send(packet(0x11)); await this.wait(10); await this.send(packet());
    await this.send(Uint8Array.of(7,0x20,0,0,0,0,0,0)); await this.wait(10);
  }
  async getByte() {
    const view=await this.device.receiveFeatureReport(7);
    // The WebHID specification preserves the OS report ID in feature responses.
    if (view.byteLength!==8 || view.getUint8(0)!==7) throw new Error('未対応のFeature Report形式です。');
    return view.getUint8(1);
  }
  async read(address,length) {
    if (length<1 || length>32 || address+length>8192) throw new Error('読み取り範囲が不正です。');
    try {
      for(let i=0;i<length;i++) await this.send(packet(3,i,address,0,length-1));
      await this.wait(1); await this.send(packet(0,0,address)); await this.wait(1);
      const data=new Uint8Array(length);
      for(let i=0;i<length;i++) {
        await this.send(packet(5,i,address,0,length-1)); await this.wait(1); data[i]=await this.getByte();
      }
      return data;
    } finally { await this.wait(1); await this.send(packet(1)); }
  }
  async readRange(address,length) {
    const result=new Uint8Array(length);
    for(let i=0;i<length;i+=8) {
      result.set(await this.read(address+i,Math.min(8,length-i)),i);
      this.progress(Math.min(i+8,length),length);
    }
    return result;
  }
  async snapshot() {
    try {
      const header=await this.read(0xd0,8), base=baseFromHeader(header);
      const data=await this.readRange(base,CONFIG_SIZE);
      if (new Set(data).size<3) throw new Error('設定が空です。未対応のファームウェアの可能性があります。');
      return {base,header,data};
    } finally { await this.finishConfiguration(); }
  }
  async exclusive(action) {
    if(this.active) throw new Error('通信処理が実行中です。');
    this.active=true;
    try { return await action(); } finally {
      try { await this.finishConfiguration(); } finally { this.active=false; }
    }
  }
  async fullSnapshot() {
    try {
      const image=await this.readRange(0,8192),header=image.slice(0xd0,0xd8),base=baseFromHeader(header);
      const data=image.slice(base,base+CONFIG_SIZE);
      if(new Set(data).size<3) throw new Error('設定データが空です。');
      return {base,header,data,image};
    } finally {await this.finishConfiguration();}
  }
  async applyExtended(snapshot,draft,macros,restoreImage,saveRecovery,lighting=null) {
    return this.exclusive(async()=>{
      const current=await this.fullSnapshot();
      if(current.base!==snapshot.base||!equal(current.data,snapshot.data)) throw new Error('本体が変更されています。再読み取りしてください。');
      await saveRecovery(await backupOf(current));
      let intended=restoreImage?restoreMacroImage(current.image,restoreImage,current.base):current.image.slice();
      intended.set(settingsOnly(intended.slice(current.base,current.base+CONFIG_SIZE),draft),current.base);
      if(lighting)intended.set(setLight(intended.slice(current.base,current.base+CONFIG_SIZE),lighting),current.base);
      for(const [id,spec] of macros) intended=planMacro(intended,current.base,offset(id),spec).image;
      const blocks=extendedBlocks(current.image,intended,current.base,!!lighting);
      // Check every to-be-written byte again after the full read and backup.
      for(const block of blocks) if(!equal(await this.read(block.address,block.data.length),current.image.slice(block.address,block.address+block.data.length))) throw new Error('保存対象が変更されています。再読み取りしてください。');
      try {
        await this.send(Uint8Array.of(7,9,0x41,0,0,0,0,0));await this.wait(200);
        for(const block of blocks) {
          const reports=writePackets(block.address,block.data);
          for(const report of reports.slice(0,-2)) await this.send(report);
          await this.wait(2);await this.send(reports.at(-2));await this.wait(10);await this.send(reports.at(-1));
        }
      } finally {await this.send(packet(0x11));await this.wait(10);await this.send(packet());}
      const verified=await this.fullSnapshot();
      if(!equal(verified.image,intended)) throw new Error('完全バックアップとの読み戻し照合が一致しません。保存前データから復元してください。');
      return verified;
    });
  }
  async apply(snapshot,draft,saveRecovery,lighting=null) {
    return this.exclusive(async()=>{
      let intended=settingsOnly(snapshot.data,draft);
      const lightOffsets=lighting?lightBlocks(intended,setLight(intended,lighting)):[];
      if(lighting)intended=setLight(intended,lighting);
      const changes=diffSettings(snapshot.data,intended);
      if(!changes.length&&!lightOffsets.length) return snapshot;
      // Re-read before writing: never overwrite another app/tab's changes.
      const current=await this.snapshot();
      if(current.base!==snapshot.base || !equal(current.data,snapshot.data)) throw new Error('本体の設定が変更されています。再読み取りして編集し直してください。');
      await saveRecovery(await backupOf(current)); // Failure MUST abort before EEPROM commits.
      // Replaying the current control block is required even when it has no
      // changed bytes. The original Apply handler writes it after 07/09/41.
      const blocks=[{address:current.base,data:intended.slice(0,8)}];
      blocks.push(...lightOffsets.filter(a=>a!==0).map(a=>({address:current.base+a,data:intended.slice(a,a+8)})));
      if(current.data[WHEEL_OFFSET]!==intended[WHEEL_OFFSET]) blocks.push({address:current.base+WHEEL_OFFSET,data:intended.slice(WHEEL_OFFSET,WHEEL_OFFSET+1)});
      blocks.push(...changes.filter(c=>c.kind!=='wheel').map(c=>({address:current.base+offset(c.id),data:intended.slice(offset(c.id),offset(c.id)+8)})));
      try {
        await this.send(Uint8Array.of(7,9,0x41,0,0,0,0,0)); await this.wait(200);
        for(const block of blocks) {
          const reports=writePackets(block.address,block.data);
          for(const report of reports.slice(0,-2)) await this.send(report);
          await this.wait(2); await this.send(reports.at(-2)); await this.wait(10); await this.send(reports.at(-1));
        }
      } finally {
        await this.send(packet(0x11)); await this.wait(10); await this.send(packet());
      }
      const verified=await this.snapshot();
      if(!equal(verified.data,intended)) throw new Error('読み戻しが一致しません。復元用バックアップを保存し、接続し直してください。');
      return verified;
    });
  }
}
