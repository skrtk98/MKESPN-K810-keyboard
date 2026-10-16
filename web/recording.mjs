import {macroKey} from './macros.mjs?v=20261016-unified';
const CODES={Enter:40,Escape:41,Backspace:42,Tab:43,Space:44,Minus:45,Equal:46,BracketLeft:47,BracketRight:48,Backslash:49,Semicolon:51,Quote:52,Backquote:53,Comma:54,Period:55,Slash:56,CapsLock:57,PrintScreen:70,ScrollLock:71,Pause:72,Insert:73,Home:74,PageUp:75,Delete:76,End:77,PageDown:78,ArrowRight:79,ArrowLeft:80,ArrowDown:81,ArrowUp:82,NumLock:83,NumpadDivide:84,NumpadMultiply:85,NumpadSubtract:86,NumpadAdd:87,NumpadEnter:88,NumpadDecimal:99,ControlLeft:224,ShiftLeft:225,AltLeft:226,MetaLeft:227,ControlRight:228,ShiftRight:229,AltRight:230,MetaRight:231};
export function recordedKey(code) {
  if(/^Key[A-Z]$/.test(code))return macroKey(code.slice(3));
  if(/^Digit[0-9]$/.test(code))return macroKey(code.slice(5));
  if(/^F([1-9]|1[0-9]|2[0-4])$/.test(code))return macroKey(code);
  if(/^Numpad[0-9]$/.test(code))return code.endsWith('0')?98:Number(code.slice(-1))+88;
  return CODES[code];
}
export class MacroRecorder {
  constructor(){this.events=[];this.held=new Map();this.last=null;}
  append(event,time) {
    if(!Number.isFinite(time))throw new Error('記録時刻が不正です。');
    if(this.events.length+this.held.size+3>=275)throw new Error('記録できる操作数に達しました。');
    let wait=this.last===null?8:Math.max(8,Math.floor((time-this.last)/8)*8);
    if(this.events.length+Math.ceil(wait/10000)+this.held.size+3>=275)throw new Error('待機時間を含めた記録上限に達しました。');
    if(this.events.length) {
      this.events.at(-1).delay=Math.min(10000,wait);wait-=this.events.at(-1).delay;
      while(wait>0){this.events.push({type:'delay',delay:Math.min(10000,wait)});wait-=Math.min(10000,wait);}
    }
    if(this.events.length+this.held.size+3>=275)throw new Error('記録できる操作数に達しました。');
    this.events.push({...event,delay:8});this.last=time;
    const down=event.type.endsWith('down'),up=event.type.endsWith('up');
    const id=event.type.startsWith('key-')?`key:${event.key}`:event.type.startsWith('mouse-')?`mouse:${event.button}`:null;
    if(down&&id)this.held.set(id,{...event,type:event.type.replace('down','up')});
    if(up&&id)this.held.delete(id);
  }
  finish(time) {
    for(const event of [...this.held.values()])this.append(event,time);
    return structuredClone(this.events);
  }
}
