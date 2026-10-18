import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {assessJevTokenAdmission as assessV4} from '../src/orchestration/jev-token-admission-v4.mjs';
import {assessJevTokenAdmission,jevTokenAdmissionPolicy} from '../src/orchestration/jev-token-admission-v5.mjs';

const sha=value=>createHash('sha256').update(value).digest('hex');
const request={model:'jev-latest',state:'state',questions:{choose:{type:'choice',instructions:'Choose the existing owner.',
  criteria:{renderer:'Existing renderer owner.',producer:'Existing producer owner.'}}}};
const policySha=sha(readFileSync(new URL('../docs/orchestration/contracts/jev-token-admission.v5.json',import.meta.url)));

test('v5 admits the documented jev-1.14 build that v4 blocks, and nothing else changes',()=>{
  const observedModel='typesafe/jev-1.14-20261014';
  const v4=assessV4(request,{stage:'profiles',observedModel});
  assert.deepEqual(v4.reason_codes,['JEV_TOKEN_ADMISSION_MODEL_UNVERIFIED']);
  const v5=assessJevTokenAdmission(request,{stage:'profiles',observedModel,expectedPolicySha256:policySha});
  assert.equal(v5.admission,'admit_observed');assert.deepEqual(v5.reason_codes,[]);
  assert.equal(v5.observed_model,observedModel);assert.equal(v5.model_context_assumption,'jev-1.14.0');
  assert.equal(v5.schema_version,'jev-token-admission-result/v5');assert.deepEqual(v5.policy_source.sha256,policySha);
  assert.deepEqual(v5.measurements,v4.measurements);assert.deepEqual(v5.local_caps,v4.local_caps);
  for(const model of ['jev-1.13.0','typesafe-ai/jev',null])
    assert.deepEqual(assessJevTokenAdmission(request,{stage:'repair',observedModel:model}).reason_codes,[]);
  assert.equal(jevTokenAdmissionPolicy().accepted_observed_model_labels.includes(observedModel),true);
});

test('v5 still blocks unknown builds, unknown stages, other requested models and a changed policy hash',()=>{
  const codes=(options,body=request)=>assessJevTokenAdmission(body,options).reason_codes;
  assert.deepEqual(codes({stage:'profiles',observedModel:'typesafe/jev-1.15-20261101'}),['JEV_TOKEN_ADMISSION_MODEL_UNVERIFIED']);
  assert.deepEqual(codes({stage:'profiles',observedModel:'jev-1.14'}),['JEV_TOKEN_ADMISSION_MODEL_UNVERIFIED']);
  assert.deepEqual(codes({stage:'deploy',observedModel:'typesafe/jev-1.14-20261014'}),['JEV_TOKEN_ADMISSION_STAGE_UNVERIFIED']);
  assert.deepEqual(codes({stage:'profiles',observedModel:'typesafe/jev-1.14-20261014'},{...request,model:'clef'}),['JEV_TOKEN_ADMISSION_MODEL_UNVERIFIED']);
  assert.deepEqual(codes({stage:'profiles',expectedPolicySha256:'0'.repeat(64)}),['JEV_TOKEN_ADMISSION_POLICY_CHANGED']);
});
