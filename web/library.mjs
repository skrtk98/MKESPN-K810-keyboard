import {compileMacro} from './macros.mjs?v=20261016-unified';
export const LIBRARY_KEY='mkespn-k810:macro-library:v1';
export const emptyLibrary=()=>({format:'mkespn-k810-macro-library-v1',groups:[]});
export function parseLibrary(input) {
  if(input?.format!=='mkespn-k810-macro-library-v1'||!Array.isArray(input.groups)||input.groups.length>12)throw new Error('マクロライブラリの形式が不正です（グループは12個まで）。');
  const ids=new Set(),name=value=>{
    if(typeof value!=='string'||!value.trim()||value.length>64)throw new Error('名前は1〜64文字で指定してください。');return value.trim();
  };
  const id=value=>{
    if(typeof value!=='string'||!value||value.length>100||ids.has(value))throw new Error('ライブラリのIDが不正または重複しています。');ids.add(value);return value;
  };
  const groups=input.groups.map(group=>{
    if(!Array.isArray(group.macros)||group.macros.length>200)throw new Error('1グループに保存できるマクロは200件までです。');
    return {id:id(group.id),name:name(group.name),macros:group.macros.map(macro=>{
      compileMacro(macro.spec);return {id:id(macro.id),name:name(macro.name),spec:structuredClone(macro.spec)};
    })};
  });
  return {format:input.format,groups};
}
export function persistLibrary(storage,input) {
  const value=parseLibrary(input),json=JSON.stringify(value);
  if(json.length>1048576)throw new Error('ライブラリは1MiBまで保存できます。');
  storage.setItem(LIBRARY_KEY,json);return value;
}
