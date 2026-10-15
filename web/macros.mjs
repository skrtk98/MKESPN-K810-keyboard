import {lightMask,LIGHT_MODES} from './lighting.mjs?v=20261015-feedback';
export const MACRO_CODES=[...Array.from({length:11},(_,i)=>0xa5+i),...Array.from({length:9},(_,i)=>0xb8+i)];
const MODES={'repeat':0,'while-held':2,'until-click':1},BUTTONS={left:241,right:243,middle:242};
function number(value,min,max,label) {
  if(!Number.isInteger(value)||value<min||value>max) throw new Error(`${label}は${min}〜${max}の整数を指定してください。`);
  return value;
}
export function macroKey(value) {
  if(typeof value==='number') return value;
  const name=String(value).toLowerCase();
  if(/^[a-z]$/.test(name)) return name.charCodeAt(0)-93;
  if(/^[1-9]$/.test(name)) return Number(name)+29;
  if(name==='0') return 39;
  const f=/^f(\d+)$/.exec(name);
  if(f&&Number(f[1])>=1&&Number(f[1])<=24) return Number(f[1])+(Number(f[1])<=12?57:91);
  const names={ctrl:224,left_ctrl:224,shift:225,left_shift:225,alt:226,left_alt:226,win:227,left_gui:227,
    right_ctrl:228,right_shift:229,right_alt:230,right_gui:231,enter:40,escape:41,tab:43,space:44,backspace:42,
    left:80,right:79,up:82,down:81,delete:76};
  if(name in names) return names[name];
  if(/^0x[\da-f]+$/.test(name)) return parseInt(name,16);
  throw new Error(`未対応のキーです：${value}`);
}
export function compileMacro(spec,address=0) {
  if(!spec||typeof spec!=='object') throw new Error('マクロ形式が不正です。');
  const mode=MODES[spec.mode??'repeat'];
  if(mode===undefined) throw new Error('繰り返し方法が不正です。');
  const repeat=number(spec.repeat??1,1,65535,'繰り返し回数');
  if(!Array.isArray(spec.events)||!spec.events.length||spec.events.length>275) throw new Error('マクロは1〜275行で作成してください。');
  const output=[mode===0?repeat&255:1,mode===0?repeat>>8:0],held=new Set(),ledSections=[];let count=0;
  const word=n=>[n&255,(n>>8)&255];
  for(const event of spec.events) {
    const ticks=Math.max(1,Math.floor(number(event.delay??8,8,10000,'待機時間')/8));
    const extra=ticks>127?Math.floor(ticks/127):0,delay=Math.max(1,ticks-extra*127);
    let identity=null,down=false;
    if(['key-down','key-up','mouse-down','mouse-up'].includes(event.type)) {
      down=event.type.endsWith('down');
      const mouse=event.type.startsWith('mouse-'),code=mouse?BUTTONS[event.button]:macroKey(event.key);
      if(mouse?code===undefined:!Number.isInteger(code)||!((code>=4&&code<=0xa4)||(code>=0xe0&&code<=0xe7))) throw new Error('キーまたはマウスボタンが不正です。');
      identity=`${mouse?'mouse':'key'}:${code}`;output.push(delay|(down?128:0),code);
    } else if(event.type==='scroll') output.push(delay,0xf7,number(event.steps,-127,127,'スクロール量')&255,0);
    else if(event.type==='move') output.push(delay,0xf6,...word(number(event.x,-32767,32767,'横移動量')),...word(number(event.y,-32767,32767,'縦移動量')));
    else if(event.type==='delay') output.push(delay,0);
    else if(event.type==='led') {
      if(!Array.isArray(event.sequence)||!event.sequence.length||event.sequence.length>16||ledSections.length>=5)throw new Error('照明は1〜16段階、マクロ内で5件まで追加できます。');
      const body=[event.sequence.length-1,0,0,0];
      for(const step of event.sequence) {
        const mode=LIGHT_MODES.findIndex(m=>m[0]===step.mode);if(mode<0)throw new Error('照明シーケンスのモードが不正です。');
        body.push(mode,number(step.color??0,0,7,'照明の色番号'),Math.floor(number(step.duration_ms??1000,100,25500,'照明の持続時間')/100),1);
      }
      ledSections.push({position:output.length,behavior:number(event.behavior??0,0,2,'照明の実行方式'),body});output.push(delay,0xf9,0,0);
    }
    else throw new Error(`未対応のイベントです：${event.type}`);
    if(identity) {if(down) held.add(identity);else held.delete(identity);}
    for(let i=0;i<extra;i++) output.push(127,0);
    count+=1+extra;
  }
  if(held.size) throw new Error('押したキー・マウスボタンを離す行も追加してください。');
  while(output.length%8) output.push(0);
  for(const {position,behavior,body} of ledSections) {
    const pointer=address+output.length;
    if(pointer+body.length>8192-0x48)throw new Error('照明データがEEPROMの範囲外です。');
    output[position+2]=pointer&255;output[position+3]=(pointer>>8)|(behavior<<6);
    output.push(...body);while(output.length%8)output.push(0);
  }
  return {payload:Uint8Array.from(output),count,mode};
}
export function macroEntry(address,count,mode) {
  number(address,0,8191,'保存先');number(count,1,16383,'イベント数');
  if(![0,1,2].includes(mode)) throw new Error('繰り返し方法が不正です。');
  return Uint8Array.of(7,(count&127)|(mode===2?128:0),address&255,(address>>8)|(mode===1?128:0),count>>7);
}
export function tableAddress(image,base) {
  if(image.length!==8192||image[0xd0]!==0xe1||image[0xd1]!==0x1e||image[0xd2]+image[0xd3]*256!==base) throw new Error('EEPROMのヘッダーが不正です。');
  const table=image[base+30]+image[base+31]*256;
  if(table!==base+248) throw new Error('未対応のマクロ領域です。');
  return table;
}
export function decodeMacro(image,base,keyOffset) {
  const table=tableAddress(image,base),slot=MACRO_CODES.indexOf(image[base+keyOffset]);
  if(slot<0)throw new Error('選択したキーにはマクロが割り当てられていません。');
  const record=image.slice(table+slot*5,table+slot*5+5),address=record[2]+(record[3]&63)*256;
  const count=(record[1]&127)+(record[4]<<7),limit=8192-0x48;
  if(record[0]!==7||!count||address<table+104||address+2>limit||(record[3]&64)||((record[1]&128)&&(record[3]&128)))throw new Error('既存マクロには未対応のフラグ・形式があります。');
  const mode=record[3]&128?'until-click':record[1]&128?'while-held':'repeat';
  const repeat=image[address]+image[address+1]*256,events=[];let at=address+2;
  for(let n=0;n<count;n++) {
    if(at+2>limit)throw new Error('既存マクロが範囲外です。');
    const timing=image[at],code=image[at+1],delay=(timing&127)*8;
    if(!delay)throw new Error('既存マクロの待機時間が不正です。');
    const size=code===0xf6?6:[0xf7,0xf9,0xfa].includes(code)?4:2;
    if(at+size>limit)throw new Error('既存マクロが範囲外です。');
    const word=i=>{const v=image[i]+image[i+1]*256;return v>32767?v-65536:v;};let event;
    if(code===0)event={type:'delay',delay};
    else if((code>=4&&code<=0xa4)||(code>=0xe0&&code<=0xe7))event={type:timing&128?'key-down':'key-up',key:code,delay};
    else if(Object.values(BUTTONS).includes(code))event={type:timing&128?'mouse-down':'mouse-up',button:Object.keys(BUTTONS).find(k=>BUTTONS[k]===code),delay};
    else if(code===0xf6)event={type:'move',x:word(at+2),y:word(at+4),delay};
    else if(code===0xf7) {
      if(image[at+3]!==0)throw new Error('未対応のスクロール命令です。');
      event={type:'scroll',steps:image[at+2]>127?image[at+2]-256:image[at+2],delay};
    }
    else if(code===0xf9) {
      const pointer=image[at+2]+(image[at+3]&63)*256,behavior=image[at+3]>>6;
      if(pointer<table+104||pointer+4>limit||image[pointer]>15||behavior>2)throw new Error('照明シーケンスの形式が不正です。');
      const sequence=[];
      for(let j=0;j<=image[pointer];j++) {
        const p=pointer+4+j*4;
        if(p+4>limit||!LIGHT_MODES[image[p]]||image[p+1]>7||!image[p+2]||image[p+3]!==1)throw new Error('未対応の照明シーケンスです。');
        sequence.push({mode:LIGHT_MODES[image[p]][0],color:image[p+1],duration_ms:image[p+2]*100});
      }
      event={type:'led',behavior,sequence,delay};
    } else throw new Error(`未対応のマクロ命令0x${code.toString(16)}を保持するため、読み込みを中止しました。`);
    events.push(event);at+=size;
  }
  const spec={mode,repeat,events};compileMacro(spec);return spec;
}
function references(image,base,table) {
  const slots=new Set(Array.from(image.slice(base+0x48,base+0xe8)).filter(c=>MACRO_CODES.includes(c)).map(c=>MACRO_CODES.indexOf(c))),ranges=[];
  for(const slot of slots) {
    const record=image.slice(table+slot*5,table+slot*5+5),address=record[2]+(record[3]&63)*256,count=(record[1]&127)+(record[4]<<7);
    if(record[0]!==7||address<table+104||address>=8192-0x48) throw new Error('既存マクロの形式を確認できません。');
    let end=address+2;
    for(let i=0;i<count;i++) {
      if(end+2>8192-0x48) throw new Error('既存マクロが範囲外です。');
      const code=image[end+1];
      if(code===0xfb) throw new Error('既存GPIOマクロの領域を保護するため保存を中止しました。');
      if(code===0xf9) {
        if(end+4>8192-0x48)throw new Error('照明参照が範囲外です。');
        const pointer=image[end+2]+(image[end+3]&63)*256;
        if(pointer<table+104||pointer>=8192-0x48||image[pointer]>15)throw new Error('照明シーケンスの位置・長さが不正です。');
        const sectionEnd=pointer+4+4*(image[pointer]+1);
        if(sectionEnd>8192-0x48)throw new Error('照明シーケンスが範囲外です。');
        ranges.push([pointer,(sectionEnd+7)&~7]);
      }
      end+=code===0xf6?6:[0xf7,0xf9,0xfa].includes(code)?4:2;
    }
    if(end>8192-0x48) throw new Error('既存マクロが範囲外です。');
    ranges.push([address,(end+7)&~7]);
  }
  return {slots,ranges};
}
export function planMacro(image,base,keyOffset,spec) {
  const table=tableAddress(image,base),{slots,ranges}=references(image,base,table);
  const slot=Array.from({length:20},(_,i)=>i).find(i=>!slots.has(i));
  if(slot===undefined) throw new Error('マクロ20枠がすべて使用中です。');
  let {payload,count,mode}=compileMacro(spec);let address;
  for(let a=(table+111)&~7;a+payload.length<=8192-0x48;a+=8) {
    if(image.slice(a,a+payload.length).every(v=>v===255)&&!ranges.some(([start,end])=>a<end&&a+payload.length>start)) {address=a;break;}
  }
  if(address===undefined) throw new Error('このマクロを保存できる未使用領域がありません。');
  ({payload,count,mode}=compileMacro(spec,address));
  const after=image.slice();after.set(payload,address);after.set(macroEntry(address,count,mode),table+slot*5);after[base+keyOffset]=MACRO_CODES[slot];
  return {image:after,slot};
}
export function restoreMacroImage(before,saved,base) {
  const table=tableAddress(before,base);
  if(tableAddress(saved,base)!==table) throw new Error('マクロ領域が一致しません。');
  const target=before.slice();target.set(saved.slice(table,8192-0x48),table);
  target.set(saved.slice(base+0x48,base+0xe8),base+0x48);target[base+32]=saved[base+32];
  return target;
}
export function extendedBlocks(before,after,base,lighting=false) {
  const table=tableAddress(before,base),changed=[];
  for(let a=0;a<8192;a+=8) if(!before.slice(a,a+8).every((v,i)=>v===after[a+i])) changed.push(a);
  const allowed=a=>(a>=base+0x48&&a<base+0xe8)||(a>=table&&a<8192-0x48);
  const lightAllowed=a=>lighting&&lightMask(a-base);
  if(before.some((v,a)=>v!==after[a]&&!allowed(a)&&a!==base+32&&(!lightAllowed(a)||((v^after[a])&~lightMask(a-base))))) throw new Error('許可していない領域の変更です。');
  if(changed.some(a=>!allowed(a)&&a!==base+32&&!(lighting&&[base,base+8,base+24].includes(a)))) throw new Error('許可していない領域の変更です。');
  const addresses=[...changed.filter(a=>a>=((table+111)&~7)),...changed.filter(a=>a>=table&&a<((table+111)&~7)),...changed.filter(a=>a>=base+0x48&&a<base+0xe8)];
  const blocks=[{address:base,data:after.slice(base,base+8)},...changed.filter(a=>lighting&&[base+8,base+24].includes(a)).map(a=>({address:a,data:after.slice(a,a+8)})),...addresses.map(a=>({address:a,data:after.slice(a,a+8)}))];
  if(before[base+32]!==after[base+32]) blocks.push({address:base+32,data:after.slice(base+32,base+33)});
  return blocks;
}
