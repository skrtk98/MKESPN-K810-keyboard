export const LIGHT_MODES=[['off','Backlight Off'],['breathing','Breathing'],['constant','Constant'],['response','Response'],
  ['neon','Neon'],['ambilight','Ambilight'],['comet-tail','Comet Tail'],['single-water','Single Water'],
  ['flow-water','Flow Water'],['flashing','Flashing'],['monochromatic-wave','Monochromatic Wave'],['partition','Partition'],['combination','Combination']];
const integer=(v,min,max,name)=>{if(!Number.isInteger(v)||v<min||v>max)throw new Error(`${name}は${min}〜${max}の整数で指定してください。`);return v;};
export function decodeLight(data) {
  if(data.length!==248)throw new Error('照明設定のサイズが不正です。');
  const mode_code=data[25]&15;
  return {mode:LIGHT_MODES[mode_code]?.[0]??'unknown',mode_code,brightness:6-((data[24]>>3)&7),speed:data[24]&7,
    direction:data[24]>>6,symmetry:!!(data[25]&128),color_selection:(data[25]>>4)&7,
    colors_enabled:data[26]&127,reaction_type:data[15]&3,
    colors:Array.from({length:7},(_,i)=>[255-16*(data[1+i*2]>>4),255-16*(data[2+i*2]&15),255-16*(data[1+i*2]&15)])};
}
export function setLight(data,changes) {
  if(data.length!==248||!changes||typeof changes!=='object'||Array.isArray(changes))throw new Error('照明設定が不正です。');
  const result=data.slice();
  for(const [name,value] of Object.entries(changes)) {
    if(name==='mode') {
      const index=LIGHT_MODES.findIndex(m=>m[0]===value);if(index<0)throw new Error('未対応の照明モードです。');
      result[25]=(result[25]&240)|index;
    } else if(['brightness','speed','direction'].includes(name)) {
      let v=integer(value,0,name==='direction'?3:6,name);
      const [mask,shift]=name==='brightness'?[56,3]:name==='direction'?[192,6]:[7,0];
      if(name==='brightness')v=6-v;result[24]=(result[24]&~mask)|(v<<shift);
    } else if(name==='symmetry') {
      if(typeof value!=='boolean')throw new Error('対称表示の値が不正です。');result[25]=(result[25]&127)|(value?128:0);
    } else if(name==='color_selection')result[25]=(result[25]&143)|(integer(value,0,7,name)<<4);
    else if(name==='colors_enabled')result[26]=(result[26]&128)|integer(value,1,127,name);
    else if(name==='reaction_type')result[15]=(result[15]&252)|integer(value,0,3,name);
    else if(name==='colors') {
      if(!Array.isArray(value)||value.length!==7)throw new Error('7色のRGBを指定してください。');
      value.forEach((rgb,i)=>{
        if(!Array.isArray(rgb)||rgb.length!==3)throw new Error('RGBの形式が不正です。');
        const [r,g,b]=rgb.map(c=>Math.floor((255-integer(c,0,255,'RGB'))/16));
        result[1+i*2]=(r<<4)|b;result[2+i*2]=(result[2+i*2]&240)|g;
      });
    } else throw new Error(`未対応の照明設定です：${name}`);
  }
  return result;
}
export function lightMask(at) {return at>=1&&at<=14?(at%2?255:15):at===15?3:at===24||at===25?255:at===26?127:0;}
export function lightBlocks(before,after) {
  if(before.length!==248||after.length!==248||before.some((v,i)=>(v^after[i])&~lightMask(i)))throw new Error('照明以外の変更が含まれています。');
  return [0,8,24].filter(a=>!before.slice(a,a+8).every((v,i)=>v===after[a+i]));
}
