import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {assessJevTokenAdmission as assessV4, jevTokenAdmissionPolicy as v4Policy} from './jev-token-admission-v4.mjs';

const CONTRACT_PATH='docs/orchestration/contracts/jev-token-admission.v5.json';
const contractBytes=readFileSync(new URL(`../../${CONTRACT_PATH}`,import.meta.url));
const contract=JSON.parse(contractBytes), inheritedPolicy=v4Policy();
const sha=value=>createHash('sha256').update(value).digest('hex');
const policyHash=sha(contractBytes);
const hashValue=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const inheritedModulePath='src/orchestration/jev-token-admission-v4.mjs';
const inheritedModuleHash=sha(readFileSync(new URL('./jev-token-admission-v4.mjs',import.meta.url)));
const added=contract.additional_accepted_observed_model_labels;

if(contract.schema_version!=='jev-token-admission-contract/v5'
  ||contract.inherits.contract_path!==inheritedPolicy.source.path||contract.inherits.contract_sha256!==inheritedPolicy.source.sha256
  ||contract.inherits.module_path!==inheritedModulePath||contract.inherits.module_sha256!==inheritedModuleHash
  ||!Array.isArray(added)||!added.length||added.some(label=>typeof label!=='string'||inheritedPolicy.accepted_observed_model_labels.includes(label))
  ||!Array.isArray(contract.context_evidence)||!contract.context_evidence.length
  ||contract.context_evidence.some(item=>!hashValue(item.sha256)||typeof item.url!=='string'||typeof item.statement!=='string')
  ||contract.long_context!==false||contract.automatic_retries!==0
  ||contract.proven_token_upper_bound!==false||contract.provider_acceptance_guaranteed!==false) {
  throw new Error('JEV_TOKEN_ADMISSION_POLICY_INVALID');
}

/** The v4 policy with the documented jev-1.14 build labels added; source is the pinned v5 contract. */
export function jevTokenAdmissionPolicy() {
  return {...structuredClone(inheritedPolicy),...structuredClone(contract),
    accepted_observed_model_labels:[...inheritedPolicy.accepted_observed_model_labels,...added],
    inherited_policy_source:structuredClone(inheritedPolicy.source),source:{path:CONTRACT_PATH,sha256:policyHash}};
}

/** v4 assessment unchanged, except that an added 1.14 label is not an unverified observed model. */
export function assessJevTokenAdmission(request,{stage=null,observedModel=null,
  expectedRequestSha256=null,expectedPolicySha256=null}={}) {
  const documented=added.includes(observedModel);
  // v4 treats a null observation as "nothing observed yet": the requested-model check still applies.
  const result=assessV4(request,{stage,observedModel:documented?null:observedModel,expectedRequestSha256});
  result.observed_model=observedModel;
  if(documented)result.model_context_assumption=contract.additional_model_context_assumption;
  result.schema_version='jev-token-admission-result/v5';
  result.policy_id=contract.policy_id;result.policy_source={path:CONTRACT_PATH,sha256:policyHash};
  result.inherited_policy_source=structuredClone(inheritedPolicy.source);
  if(expectedPolicySha256!==null&&(!hashValue(expectedPolicySha256)||expectedPolicySha256!==policyHash))result.reason_codes.push('JEV_TOKEN_ADMISSION_POLICY_CHANGED');
  result.inference_allowed=result.reason_codes.length===0;
  result.admission=result.inference_allowed?'admit_observed':'blocked';
  return result;
}
