const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../api/templates/api/dashboard.html'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];

function harness() {
  const elements = new Map();
  const el = id => {
    if (!elements.has(id)) elements.set(id, {value: '', textContent: '', hidden: false, disabled: false, checked: true, setAttribute(k,v) {this[k]=v;}});
    return elements.get(id);
  };
  const timers = new Map(), events = {}, documentEvents = {}, requests = [], utterances = [], recognizers = [];
  let sequence = 0, cancels = 0;
  const context = {
    AbortController, console, isSecureContext: true,
    setTimeout(fn) {timers.set(++sequence,fn);return sequence;}, clearTimeout(id) {timers.delete(id);},
    document: {hidden:false, documentElement:{lang:'en-US'},getElementById:el,querySelector:()=>({value:'csrf-test'}),addEventListener:(name,fn)=>documentEvents[name]=fn},
    addEventListener:(name,fn)=>events[name]=fn,
    speechSynthesis:{speak:u=>utterances.push(u),cancel:()=>cancels++,getVoices:()=>[]},
    SpeechSynthesisUtterance:class {constructor(text){this.text=text;}},
    SpeechRecognition:class {constructor(){recognizers.push(this);} start(){this.started=true;} abort(){this.aborted=true;}},
    fetch:async (url,options)=>{requests.push({url,...options});return {ok:true,json:async()=>({reply_text:'Realistic reply'})};}
  };
  context.window=context;
  vm.createContext(context); vm.runInContext(source,context);
  const flush = async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
  return {context,el,timers,events,documentEvents,requests,utterances,recognizers,flush,get cancels(){return cancels;}};
}

test('TTS updates start/end state and completes without available voice list',async()=>{
 const h=harness();h.el('text').value='my marks';await h.el('send').onclick();
 assert.equal(h.utterances.length,1);assert.equal(h.el('stop-audio').disabled,false);
 h.utterances[0].onstart();assert.match(h.el('audio-status').textContent,/Reading/);
 h.utterances[0].onend();assert.equal(h.el('audio-status').textContent,'Read aloud finished.');assert.equal(h.el('stop-audio').disabled,true);
});
test('new reply cancels old audio; late old callbacks cannot restart it',async()=>{
 const h=harness();h.el('text').value='my marks';await h.el('send').onclick();const old=h.utterances[0];
 await h.el('send').onclick();const newest=h.utterances[1];newest.onstart();old.onend();old.onerror();
 assert.equal(h.utterances.length,2);assert.match(h.el('audio-status').textContent,/Reading/);assert.ok(h.cancels>=2);
});
test('double submission produces one request and re-enables controls',async()=>{
 const h=harness();let finish;h.context.fetch=(url,options)=>{h.requests.push({url,...options});return new Promise(r=>finish=r);};
 h.el('text').value='my marks';const first=h.el('send').onclick();await h.el('send').onclick();assert.equal(h.requests.length,1);assert.equal(h.el('send').disabled,true);
 finish({ok:true,json:async()=>({reply_text:'Done'})});await first;assert.equal(h.el('send').disabled,false);
});
test('empty question and empty response never produce speech',async()=>{
 const h=harness();await h.el('send').onclick();assert.equal(h.requests.length,0);
 h.context.fetch=async()=>({ok:true,json:async()=>({reply_text:'   '})});h.el('text').value='my marks';await h.el('send').onclick();assert.equal(h.utterances.length,0);
});
test('long replies are bounded and read sequentially without duplicate chunks',async()=>{
 const h=harness();h.context.fetch=async()=>({ok:true,json:async()=>({reply_text:'long response '.repeat(500)})});h.el('text').value='policy';await h.el('send').onclick();
 let index=0;while(index<h.utterances.length){const u=h.utterances[index++];assert.ok(u.text.length<=180);u.onend();assert.ok(index<50);}
 assert.ok(index>1);assert.ok(h.utterances.reduce((n,u)=>n+u.text.length,0)<=4000);assert.match(h.el('audio-status').textContent,/first 4,000/);assert.ok(h.el('reply').textContent.length>4000);
});
test('speech errors and watchdog clear the speaking state',async()=>{
 const h=harness();h.el('text').value='my marks';await h.el('send').onclick();h.utterances[0].onerror();assert.match(h.el('audio-status').textContent,/failed/);assert.equal(h.el('stop-audio').disabled,true);
 await h.el('send').onclick();[...h.timers.values()][0]();assert.match(h.el('audio-status').textContent,/timed out/);assert.equal(h.el('stop-audio').disabled,true);
});
test('missing TTS API and synchronous synthesis failure preserve the reply',async()=>{
 const h=harness();h.context.speechSynthesis=undefined;h.el('text').value='marks';await h.el('send').onclick();assert.match(h.el('audio-status').textContent,/unavailable/);assert.equal(h.el('reply').textContent,'Realistic reply');
 h.context.speechSynthesis={cancel(){},speak(){throw Error('device unavailable');}};await h.el('send').onclick();assert.equal(h.el('stop-audio').disabled,true);assert.match(h.el('audio-status').textContent,/unavailable/);
});
test('stop and opt-out cancel playback without replaying on opt-in',async()=>{
 const h=harness();h.el('text').value='marks';await h.el('send').onclick();h.el('stop-audio').onclick();assert.match(h.el('audio-status').textContent,/stopped/);
 h.el('speak-replies').checked=false;h.el('speak-replies').onchange();await h.el('send').onclick();assert.equal(h.utterances.length,1);
 h.el('speak-replies').checked=true;h.el('speak-replies').onchange();assert.equal(h.utterances.length,1);
});
test('native recognition start is requested once; toggle aborts and ignores stale result',async()=>{
 const h=harness();h.el('mic').onclick();assert.equal(h.recognizers.length,1);assert.ok(h.recognizers[0].started);h.el('mic').onclick();assert.ok(h.recognizers[0].aborted);
 h.recognizers[0].onresult({results:[[{transcript:'my marks'}]]});await h.flush();assert.equal(h.requests.length,0);
});
test('recognized transcript uses authenticated API and ignores duplicate events',async()=>{
 const h=harness();h.el('mic').onclick();const r=h.recognizers[0];r.onstart();assert.match(h.el('voice-status').textContent,/Listening/);
 const event={results:[[{transcript:'Show my AD3491 marks'}]]};r.onresult(event);r.onresult(event);await h.flush();
 assert.equal(h.requests.length,1);assert.deepEqual(JSON.parse(h.requests[0].body),{text:'Show my AD3491 marks'});assert.equal(h.requests[0].headers['X-CSRFToken'],'csrf-test');assert.equal(h.utterances.length,1);
});
test('spoken confirmation uses the existing signed token and only once',async()=>{
 const h=harness();h.context.fetch=async(url,options)=>{h.requests.push({url,...options});return {ok:true,json:async()=>({reply_text:'Confirm?',requires_confirmation:true,pending:'signed-token'})};};
 h.el('text').value='mark me absent';await h.el('send').onclick();h.el('mic').onclick();h.recognizers[0].onresult({results:[[{transcript:'Yes.'}]]});await h.flush();
 assert.equal(h.requests[1].url,'/api/confirm/');assert.deepEqual(JSON.parse(h.requests[1].body),{confirm:'yes',pending:'signed-token'});
});
test('permission, hardware, network and no-speech errors have actionable fallbacks',()=>{
 for(const [error,pattern] of [['not-allowed',/macOS/],['audio-capture',/No microphone/],['network',/could not connect/],['no-speech',/No speech/],['service-not-allowed',/speech service/]]){
  const h=harness();h.el('mic').onclick();h.recognizers[0].onerror({error});assert.match(h.el('voice-status').textContent,pattern);assert.equal(h.el('mic')['aria-pressed'],'false');assert.equal(h.requests.length,0);
 }
});
test('unsupported/insecure browser and start exception remain usable as text',()=>{
 const h=harness();h.context.isSecureContext=false;h.el('mic').onclick();assert.match(h.el('voice-status').textContent,/HTTPS/);
 h.context.isSecureContext=true;h.context.SpeechRecognition=undefined;h.el('mic').onclick();assert.match(h.el('voice-status').textContent,/unavailable/);
 h.context.SpeechRecognition=class {start(){throw Object.assign(Error(),{name:'NotAllowedError'});}abort(){}};h.el('mic').onclick();assert.match(h.el('voice-status').textContent,/permission was denied/);assert.equal(h.el('send').disabled,false);
});
test('recognition timeout/end/empty transcript never invent a request',()=>{
 for(const mode of ['timeout','end','empty']){const h=harness();h.el('mic').onclick();const r=h.recognizers[0];
  if(mode==='timeout')[...h.timers.values()][0]();else if(mode==='end')r.onend();else r.onresult({results:[[{transcript:' ' }]]});
  assert.equal(h.requests.length,0);assert.equal(h.el('mic')['aria-pressed'],'false');assert.ok(h.el('voice-status').textContent);
 }
});
test('page lifecycle cancels speech/recognition and ignores in-flight response',async()=>{
 const h=harness();h.el('mic').onclick();h.events.pagehide();assert.ok(h.recognizers[0].aborted);
 let finish;h.context.fetch=(url,options)=>{h.requests.push({url,...options});return new Promise(r=>finish=r);};h.el('text').value='marks';const request=h.el('send').onclick();
 h.context.document.hidden=true;h.documentEvents.visibilitychange();assert.ok(h.requests[0].signal.aborted);finish({ok:true,json:async()=>({reply_text:'Stale'})});await request;
 assert.equal(h.utterances.length,0);assert.notEqual(h.el('reply').textContent,'Stale');assert.equal(h.el('send').disabled,false);
});
test('failed new request invalidates previous confirmation',async()=>{
 const h=harness();h.context.fetch=async()=>({ok:true,json:async()=>({reply_text:'Confirm',requires_confirmation:true,pending:'old-token'})});h.el('text').value='mark me absent';await h.el('send').onclick();
 h.context.fetch=async()=>{throw Error('offline');};await h.el('send').onclick();assert.equal(h.el('confirmation').hidden,true);await h.el('yes').onclick();assert.match(h.el('status').textContent,/offline/);
});
test('expired session and malformed server response restore controls safely',async()=>{
 const h=harness();h.el('text').value='marks';h.context.fetch=async()=>({redirected:true});await h.el('send').onclick();assert.match(h.el('status').textContent,/Sign in again/);
 h.context.fetch=async()=>({ok:true,json:async()=>{throw Error('HTML');}});await h.el('send').onclick();assert.match(h.el('status').textContent,/server could not answer/);assert.equal(h.el('send').disabled,false);
});
