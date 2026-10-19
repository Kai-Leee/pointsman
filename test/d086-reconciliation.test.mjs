import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,writeFileSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {createTokenBudget} from '../src/benchmark/budget.mjs';
import {validateD086Reconciliation,reconcileD086Response} from '../scripts/reconcile-d086-response.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
const policy=path=>({schema_version:'jev-token-budget/v4',ledger_path:path,max_input_tokens:null,reserve_input_tokens:65536});
const balance={paidInputTokensRemaining:1e6,tokensReserved:0,tokenDebt:0,spending_frozen:false};
const response={model:'typesafe/jev-1.14-20261014',usage:{input_tokens:18132,output_tokens:621},
 billing:{mode:'tokens',modelMultiplier:'1',creditsCharged:'0',paidInputTokensUsed:'18132',runId:'saved-provider-run'},
 receipt:{method:'POST',destination:'https://jev-ai.pro/api/v1/systemone',status:200,automaticRetries:0,durationMs:1215}};
const save=(p,x)=>writeFileSync(p,JSON.stringify(x)+'\n',{mode:0o600});
function fixture(){const dir=mkdtempSync(join(tmpdir(),'d086-reconcile-'));const path=join(dir,'ledger.json'),config=policy(path),budget=createTokenBudget(config);
 const ids={request_id:'jev-1',run_id:'jev_profile-run',attempt_id:'jev_profile-run-jev-0006',group_id:'d073-decisions'};
 const reservation=budget.reserve(ids,balance,{leaseMs:100000});
 const other=budget.reserve({...ids,request_id:'other',attempt_id:'another-attempt'},balance,{leaseMs:100000});
 assert.throws(()=>budget.settle(reservation,{...response,model:'typesafe/jev-1.14-20990101'}),{code:'BUDGET_MODEL_UNSUPPORTED'});
 const pending=budget.snapshot();budget.close();
 const eventBase={...ids,provider:'jev'};const events=[{...eventBase,event:'budget_reserved',budget:pending},
 {...eventBase,event:'inference_started'},{...eventBase,event:'inference_finished',status:'completed',...response},
 {...eventBase,event:'budget_blocked',code:'BUDGET_MODEL_UNSUPPORTED',outcome_uncertain:true}];
 const eventPath=join(dir,'events.jsonl');writeFileSync(eventPath,events.map(e=>JSON.stringify(e)).join('\n')+'\n');
 const receiptPath=join(dir,'receipt.json'),resultPath=join(dir,'result.json');
 save(receiptPath,{provider:'jev',attempt_id:ids.attempt_id,code:'BUDGET_MODEL_UNSUPPORTED',status:'uncertain',inference_started:true,usage:null});
 save(resultPath,{run_id:ids.run_id,status:'uncertain',stop_code:'BUDGET_MODEL_UNSUPPORTED',budget_after:pending});
 const plan={schema_version:'d086-response-reconciliation/v1',ledger_config:config,ledger_sha256:hash(readFileSync(path)),
 events_path:eventPath,events_sha256:hash(readFileSync(eventPath)),provider_receipt_path:receiptPath,provider_receipt_sha256:hash(readFileSync(receiptPath)),
 arm_result_path:resultPath,arm_result_sha256:hash(readFileSync(resultPath)),attempt_id:ids.attempt_id,reservation_id:reservation};
 return{dir,path,plan,events,eventPath,receiptPath,resultPath,reservation,other};}

test('exact documented1.14 build settles; aliases, prefixes and future dated builds stay unsupported',()=>{
 for(const model of ['typesafe/jev-1.14-20261014','jev-latest','jev-1.14','typesafe/jev-1.14-20261015','typesafe/jev-1.14-20261014-extra']){
  const dir=mkdtempSync(join(tmpdir(),'d086-model-'));let b;try{b=createTokenBudget(policy(join(dir,'ledger.json')));const id=b.reserve({request_id:'r1',run_id:'run',attempt_id:'attempt',group_id:'group'},balance,{leaseMs:10000});
   if(model===response.model){const got=b.settle(id,{...response,model});assert.equal(got.charged_input_tokens,18132);assert.equal(got.reservations_pending,0);}
   else{assert.throws(()=>b.settle(id,{...response,model}),{code:'BUDGET_MODEL_UNSUPPORTED'});assert.equal(b.snapshot().charged_input_tokens,0);assert.equal(b.snapshot().reservations_pending,1);}
  }finally{b?.close();rmSync(dir,{recursive:true,force:true});}}
});

test('preview binds source hashes, attempt and current pending linkage without locking or changing ledger',()=>{const f=fixture();try{
 const before=readFileSync(f.path);const result=reconcileD086Response({plan:f.plan,outDirectory:join(f.dir,'preview')});
 assert.equal(result.status,'validated_not_applied');assert.equal(result.model_calls,0);assert.equal(result.network_calls,0);
 assert.equal(result.input_tokens,18132);assert.deepEqual(readFileSync(f.path),before);assert.equal(existsSync(f.path+'.lock'),false);
 assert.equal(validateD086Reconciliation(f.plan).entry.attempt_id,f.plan.attempt_id);
 }finally{rmSync(f.dir,{recursive:true,force:true});}});

test('explicit apply preserves before/after bytes and only reconciles the bound pending entry once',()=>{const f=fixture();try{
 const before=readFileSync(f.path),sourceBefore=[f.eventPath,f.receiptPath,f.resultPath].map(p=>hash(readFileSync(p)));
 const out=join(f.dir,'applied'),audit=reconcileD086Response({plan:f.plan,outDirectory:out,apply:true});
 assert.equal(audit.status,'reconciled');assert.equal(audit.after.charged_input_tokens-audit.before.charged_input_tokens,18132);
 assert.equal(audit.after.settled_requests-audit.before.settled_requests,1);assert.deepEqual(audit.after.pending_reservation_ids,[f.other]);
 assert.deepEqual(readFileSync(join(out,'ledger-before.json')),before);assert.deepEqual(readFileSync(join(out,'ledger-after.json')),readFileSync(f.path));
 assert.deepEqual([f.eventPath,f.receiptPath,f.resultPath].map(p=>hash(readFileSync(p))),sourceBefore);
 assert.equal(existsSync(f.path+'.lock'),false);
 assert.throws(()=>reconcileD086Response({plan:f.plan,outDirectory:join(f.dir,'again'),apply:true}),{code:'D086_RECONCILIATION_HASH_MISMATCH'});
 assert.equal(existsSync(join(f.dir,'again')),false);
 }finally{rmSync(f.dir,{recursive:true,force:true});}});

test('source hash mismatch, cross-attempt and wrong reservation cannot mutate or acquire a ledger lock',()=>{
 for(const mutate of [p=>({...p,events_sha256:'0'.repeat(64)}),p=>({...p,attempt_id:'another-attempt'}),p=>({...p,reservation_id:'wrong-reservation'})]){
 const f=fixture();try{const before=readFileSync(f.path);assert.throws(()=>reconcileD086Response({plan:mutate(f.plan),outDirectory:join(f.dir,'rejected'),apply:true}));
 assert.deepEqual(readFileSync(f.path),before);assert.equal(existsSync(f.path+'.lock'),false);assert.equal(existsSync(join(f.dir,'rejected')),false);
 }finally{rmSync(f.dir,{recursive:true,force:true});}}
});

test('hash-rebound wrong billing and model still fail semantic validation before a ledger mutation',()=>{
 for(const mutate of [e=>{e.model='typesafe/jev-1.14-20261015';},e=>{e.billing={...e.billing,modelMultiplier:'2'};},e=>{e.receipt={...e.receipt,destination:'https://other.example/api'};}]){
 const f=fixture();try{const before=readFileSync(f.path);mutate(f.events[2]);writeFileSync(f.eventPath,f.events.map(e=>JSON.stringify(e)).join('\n')+'\n');
 const plan={...f.plan,events_sha256:hash(readFileSync(f.eventPath))};assert.throws(()=>reconcileD086Response({plan,outDirectory:join(f.dir,'rejected'),apply:true}));
 assert.deepEqual(readFileSync(f.path),before);assert.equal(existsSync(f.path+'.lock'),false);
 }finally{rmSync(f.dir,{recursive:true,force:true});}}
});
