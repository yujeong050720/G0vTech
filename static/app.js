const $ = id => document.getElementById(id);
const errors = {INVALID_CODE:'체험 코드를 확인하세요.',NOT_CONFIGURED:'서버 연결 설정이 준비 중입니다.',SYNTHETIC_INPUT_ONLY:'가상약A 1정 처방 또는 가상약B 1정 처방을 입력하세요.',BUSY:'다른 실험이 진행 중입니다. 잠시 뒤 시도하세요.',RATE_LIMIT:'잠시 쉬었다가 1분 뒤 다시 시도하세요.',DAILY_LIMIT:'오늘의 무료 체험 20회를 모두 사용했습니다. UTC 자정 이후 다시 이용하세요.',METADATA_UNAVAILABLE:'기록 서버 연결을 확인할 수 없습니다. 운영자에게 알려주세요.',NOT_FOUND:'기록을 찾을 수 없습니다.'};
let receipt, running=false;
document.querySelectorAll('[data-prompt]').forEach(button=>button.addEventListener('click',()=>{$('prescription').value=button.dataset.prompt;}));
fetch('/health').then(r=>r.json()).then(data=>{$('setup').hidden=data.configured;}).catch(()=>{});
async function api(path, code, data){
  const response=await fetch(path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json','X-Demo-Code':code},body:data?JSON.stringify(data):undefined,signal:AbortSignal.timeout(30000)});
  const result=await response.json();
  if(!response.ok)throw new Error(errors[result.error]||'요청을 처리하지 못했습니다.');
  return result;
}
function render(data){
  receipt=data;
  const storage=data.storage||{}, ai=data.ai||{};
  $('ipfs-state').textContent=storage.cid?'암호화 파일 업로드 완료':storage.failed_stage==='IPFS'?'IPFS 업로드 실패':storage.status==='ENCRYPTED'?'암호화 완료 · 업로드 중':'대기 / 처리 중';
  $('chain-state').textContent=storage.status==='REGISTERED'?'실제 원장 등록 완료':storage.status==='CHAIN_PENDING'?'거래 확인 대기 · 재전송하지 마세요':storage.status==='FAILED'?'저장 실패: '+storage.failed_stage:'대기 / 처리 중';
  $('ai-state').textContent=ai.status==='SUCCEEDED'?'암호문 계산 · 복호화 완료':ai.status==='FAILED'?'AI 실행 실패':'대기 / 처리 중';
  $('answer-box').hidden=ai.status!=='SUCCEEDED';
  $('answer').textContent=ai.explanation||'';
  $('verified').textContent=ai.verified?'평문 기준 계산과 수치 검증 통과':'';
  $('proof').hidden=!storage.cid;
  $('cid').textContent=storage.cid||'';
  const validHash=/^0x[0-9a-fA-F]{64}$/.test(storage.tx_hash||'');
  $('transaction').hidden=!validHash;
  if(validHash)$('transaction').href='https://sepolia.etherscan.io/tx/'+storage.tx_hash;
  $('download').hidden=data.status!=='DONE';
}
$('demo-form').addEventListener('submit',async event=>{
  event.preventDefault();if(running)return;
  running=true;$('submit').disabled=true;
  const code=$('code').value, prescription=$('prescription').value.trim();
  $('status').textContent='실험을 시작합니다. 실제 거래 확인까지 시간이 걸릴 수 있습니다.';
  render({status:'PENDING'});
  let started=false;
  try{
    const job=await api('/api/runs',code,{prescription});started=true;
    // Store only a random receipt id, never access codes or keys.
    sessionStorage.setItem('medical-demo-run',job.id);
    for(let count=0;count<100;count++){
      const result=await api('/api/runs/'+job.id,code);render(result);
      if(result.status==='DONE'){
        $('status').textContent=result.storage.status==='REGISTERED'&&result.ai.status==='SUCCEEDED'?'전체 과정이 완료됐습니다.':'실험이 끝났습니다. 각 단계의 성공 여부를 확인하세요.';return;
      }
      if(result.status==='INTERRUPTED')throw new Error('서버가 재시작되었거나 처리가 중단됐습니다. 거래 해시가 있다면 확인 후 운영자에게 알려주세요.');
      await new Promise(resolve=>setTimeout(resolve,3000));
    }
    throw new Error('확인 시간이 초과됐습니다. 같은 실험을 즉시 다시 제출하지 마세요.');
  }catch(error){$('status').textContent=(error.name==='TimeoutError'?'응답이 늦어지고 있습니다. 중복 제출하지 마세요.':error.message)+(started?' 기록 ID: '+sessionStorage.getItem('medical-demo-run'):'');}
  finally{running=false;$('submit').disabled=false;}
});
$('download').addEventListener('click',()=>{
  if(!receipt)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='demo-result-'+receipt.id+'.json';a.click();URL.revokeObjectURL(url);
});
$('resume').addEventListener('click',async()=>{
  const id=sessionStorage.getItem('medical-demo-run');
  if(!id){$('status').textContent='이 탭에서 진행한 실험이 없습니다.';return;}
  try{const result=await api('/api/runs/'+id,$('code').value);render(result);$('status').textContent='최근 실험 상태: '+result.status;}
  catch(error){$('status').textContent=error.message;}
});
