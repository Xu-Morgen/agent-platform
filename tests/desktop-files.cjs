const { test } = require('node:test');
const assert = require('node:assert/strict');
const { fields } = require('../desktop/renderer/task-files.js');
const file = { $ref: '#/$defs/File', 'x-platform-file': { formats: ['pdf', 'docx'] } };
test('文件控件由标注驱动，支持对象、可空字段和数组', () => {
  const schema = {type:'object',required:['document'],properties:{
    document:file, extra:{anyOf:[file,{type:'null'}]}, files:{type:'array',items:file},
    arbitraryPath:{type:'string'},
  }};
  assert.deepEqual(fields(schema,{files:[{}]}), [
    {path:['document'],required:true,formats:['pdf','docx']},
    {path:['extra'],required:false,formats:['pdf','docx']},
    {path:['files',0],required:true,formats:['pdf','docx']},
  ]);
});
test('普通 JSON 契约没有文件控件，根文件契约有一个控件', () => {
  assert.deepEqual(fields({type:'object',properties:{file:{type:'string'}}}), []);
  assert.deepEqual(fields(file), [{path:[],required:true,formats:['pdf','docx']}]);
});

function renderer() {
  const fs = require('node:fs'), vm = require('node:vm');
  class Element {
    constructor() { this.children=[];this.value='{}';this.listeners={}; }
    replaceChildren(...children) { this.children=children; }
    append(...children) { this.children.push(...children); }
    addEventListener(name, callback) { this.listeners[name]=callback; }
  }
  const input=new Element(), host=new Element(), events=[], removed=[];
  const window={agentPlatform:{removeTaskFile:async id=>removed.push(id)},dispatchEvent:event=>events.push(event)};
  const document={querySelector:selector=>selector==='#task-input'?input:host,createElement:()=>new Element()};
  const context=vm.createContext({window,document,Event:class {constructor(type){this.type=type;}},CustomEvent:class {constructor(type,values){this.type=type;Object.assign(this,values);}}});
  vm.runInContext(fs.readFileSync(require.resolve('../desktop/renderer/task-files.js'),'utf8'),context);
  return {window,input,host,events,removed};
}
test('保存结束前拒绝提交，保存完成后注入引用，可替换和移除', async () => {
  const {window,host,removed}=renderer();
  const schema={type:'object',required:['document'],properties:{document:file}};
  window.taskFiles.setSchema(schema);
  let complete;
  window.agentPlatform.selectTaskFile=()=>new Promise(resolve=>complete=resolve);
  const selecting=host.children[0].children[1].onclick();
  assert.equal(window.taskFiles.pending,true);
  assert.throws(()=>window.taskFiles.input({}),/尚未保存/);
  const first={fileId:'first',originalName:'first.pdf',size:12,format:'pdf'};
  complete({ok:true,data:first});await selecting;
  assert.equal(window.taskFiles.pending,false);
  assert.equal(window.taskFiles.input({}).document.fileId,'first');
  window.agentPlatform.selectTaskFile=async()=>({ok:true,data:{...first,fileId:'second'}});
  await host.children[0].children[1].onclick();
  assert.equal(window.taskFiles.input({}).document.fileId,'second');
  assert.deepEqual(removed,['first']);
  await host.children[0].children[2].onclick();
  assert.throws(()=>window.taskFiles.input({}),/请选择|请先选择/);
  assert.deepEqual(removed,['first','second']);
});
test('取消选择保持原引用，切换服务后迟到上传不会污染新输入', async () => {
  const {window,host,removed,events}=renderer();
  window.taskFiles.setSchema(file);
  window.agentPlatform.selectTaskFile=async()=>({ok:true,data:{fileId:'first',originalName:'first.pdf',size:12,format:'pdf'}});
  await host.children[0].children[1].onclick();
  window.agentPlatform.selectTaskFile=async()=>({ok:true,data:null});
  await host.children[0].children[1].onclick();
  assert.equal(window.taskFiles.input({}).fileId,'first');
  assert.equal(events.at(-2).type,'task-files-notice');
  let complete;
  window.agentPlatform.selectTaskFile=()=>new Promise(resolve=>complete=resolve);
  const selecting=host.children[0].children[1].onclick();
  window.taskFiles.setSchema({});
  complete({ok:true,data:{fileId:'late'}});await selecting;
  assert.deepEqual(removed,['late']);
  assert.equal(window.taskFiles.input({}).fileId,undefined);
});
