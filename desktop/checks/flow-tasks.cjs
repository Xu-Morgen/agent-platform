const {app}=require('electron'),assert=require('node:assert/strict'),http=require('node:http'),{once}=require('node:events');
const {Backend}=require('../main/backend.cjs'),{openDesktop}=require('../main/desktop.cjs');
const watchdog=setTimeout(()=>app.exit(1),30000);
app.whenReady().then(async()=>{
 let mode='success',pending;
 const respond=res=>res.end(JSON.stringify({done:true,done_reason:'stop',message:{role:'assistant',content:mode==='bad'?'{}':'{"text":"协议替身"}'},prompt_eval_count:2,eval_count:3}));
 const server=http.createServer((req,res)=>{req.resume();pending=res;if(mode!=='wait')respond(res)});
 server.listen(0,'127.0.0.1');await once(server,'listening');
 const backend=new Backend(),window=await openDesktop(backend),run=s=>window.webContents.executeJavaScript(s);
 const wait=e=>run(`new Promise((resolve,reject)=>{const end=Date.now()+7000;const check=()=>{if(${e})resolve();else if(Date.now()>end)reject(new Error('UI timeout '+${JSON.stringify(e)}));else setTimeout(check,20)};check()})`);
 try{
  await wait("document.querySelector('#status').textContent.includes('后端已就绪')");
  const env=await run(`window.agentPlatform.createEnvironment({name:'替身',connections:[{connectionId:'model',kind:'model',baseUrl:'http://127.0.0.1:${server.address().port}',model:'synthetic'}]})`);
  const block=(await run("window.agentPlatform.loadResource({kind:'block',path:'examples/flows/blocks/rename.py'})")).data;
  const pkg=(await run("window.agentPlatform.loadResource({kind:'package',path:'examples/execution/model-package'})")).data;
  const bind=source=>[{target:[],source}],input={kind:'input',path:[]},ref=nodeId=>({kind:'node',nodeId,path:[]});
  const pure={name:'纯块任务',inputContract:block.inputContract,outputContract:block.outputContract,flow:[{kind:'block',nodeId:'convert',artifactRef:block.resourceId,inputs:bind(input)}],output:bind(ref('convert')),nodeConfigurations:{},examples:[{name:'合法样例',input:{legacyText:'合成'}}]};
  const modeled={name:'循环包任务',inputContract:pkg.inputContract,outputContract:pkg.outputContract,
   flow:[{kind:'repeat',nodeId:'loop',count:2,carry:{contract:pkg.inputContract,initial:bind(input),update:bind(ref('generate'))},body:[{kind:'package',nodeId:'generate',artifactRef:pkg.resourceId,inputs:bind({kind:'carry',nodeId:'loop',path:[]})}]}],
   output:bind(ref('loop')),nodeConfigurations:{generate:{parameters:{maxOutputTokens:64},budget:{loopLimit:2,tokenLimit:2048},capabilities:{chat:{kind:'model',environmentId:env.data.environmentId,connectionId:'model'}}}},budget:{loopLimit:2,tokenLimit:2048,strictTokenLimit:false},examples:[{name:'合成',input:{text:'合成'}}]};
  const saved=[];
  for(const flow of [pure,modeled]){const result=await run(`window.agentPlatform.createService(${JSON.stringify({name:flow.name,flow})})`);assert.ok(result.ok,JSON.stringify(result));saved.push(result.data);}
  await run("refreshServices()");await run("location.hash='/tasks'");
  for(const [service,behavior] of [[saved[0],'success'],[saved[1],'success'],[saved[1],'bad'],[saved[1],'wait']]){
   mode=behavior;pending=null;
   await run(`document.querySelector('#task-service-select').value=${JSON.stringify(service.serviceId)};document.querySelector('#task-service-select').dispatchEvent(new Event('change'));document.querySelector('#task-input').value='';document.querySelector('#task-example').click()`);
   await wait("document.querySelector('#task-input').value!==''");
   assert.ok((await run("document.querySelector('#task-current').textContent")).includes(service.activeInstanceId));
   const previous=await run("document.querySelector('#task-run-id').value");
   await run("document.querySelector('#task-form').requestSubmit()");
   await wait(`document.querySelector('#task-run-id').value!==${JSON.stringify(previous)}`);
   if(mode==='wait'){
    await wait("document.querySelector('#task-steps').textContent.includes('model.generate.chat')");assert.ok(pending);
    await run("document.querySelector('#task-cancel').click()");await wait("document.querySelector('#task-cancel-status').textContent.includes('等待当前模型传输结束')");
    respond(pending);await wait("document.querySelector('#task-status').textContent.startsWith('cancelled')");
   }else{
    await wait(`document.querySelector('#task-status').textContent.startsWith('${mode==='bad'?'failed':'completed'}')`);
    if(mode==='bad'){assert.match(await run("document.querySelector('#task-error').textContent"),/OUTPUT_VALIDATION_ERROR/);assert.match(await run("document.querySelector('#task-steps').textContent"),/generate/);assert.equal(await run("document.querySelector('#task-result').textContent"),'');}
    else {await wait("document.querySelector('#task-result').textContent!==''");assert.match(await run("document.querySelector('#task-steps').textContent"),/合成|协议替身/);
     if(service===saved[1]){assert.match(await run("document.querySelector('#task-steps').textContent"),/loop\[1\]/);assert.match(await run("document.querySelector('#task-usage').textContent"),/loop 2/);}}
   }
  }
  console.log('PASS I8-T05: pure/package service examples, fixed instance, loop path/output/usage, concrete failure and cancel waiting');
 }finally{await backend.stop();window.destroy();server.closeAllConnections();server.close();clearTimeout(watchdog);app.quit()}
}).catch(e=>{console.error(e);app.exit(1)});
