import os
import json
from web3 import Web3

ABI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'contracts', 'abi.json')


class ChainPending(RuntimeError):
    """Broadcast/confirmation is uncertain. Reconcile this hash; do not resubmit."""


class ChainReverted(RuntimeError):
    """A receipt explicitly reports an unsuccessful transaction."""


def _load_abi():
    with open(ABI_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_web3():
    """
    필요 환경변수: WEB3_PROVIDER_URL
    (예: Infura/Alchemy의 Sepolia 등 테스트넷 RPC URL, 또는 로컬 Hardhat/Ganache 노드)
    """
    provider_url = os.environ.get('WEB3_PROVIDER_URL')
    if not provider_url:
        raise RuntimeError("환경변수 WEB3_PROVIDER_URL이 설정되어 있지 않습니다 (RPC 엔드포인트 URL).")
    return Web3(Web3.HTTPProvider(provider_url))


def get_contract(w3=None):
    """
    필요 환경변수: CONTRACT_ADDRESS (FileRegistry.sol 배포 주소)
    """
    w3 = w3 or get_web3()
    contract_address = os.environ.get('CONTRACT_ADDRESS')
    if not contract_address:
        raise RuntimeError("환경변수 CONTRACT_ADDRESS가 설정되어 있지 않습니다 (배포된 FileRegistry 컨트랙트 주소).")
    abi = _load_abi()
    return w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)


def register_file_on_chain(cid, filename, on_prepared=None):
    """
    IPFS CID와 파일명을 FileRegistry 컨트랙트의 registerFile()로 블록체인에 기록합니다.

    필요 환경변수: WEB3_PROVIDER_URL, CONTRACT_ADDRESS, PRIVATE_KEY
    (PRIVATE_KEY는 트랜잭션에 서명할 지갑의 개인키 — 반드시 테스트넷 전용 지갑을 쓰고,
     .env로만 관리하고 절대 코드/커밋에 남기지 마세요.)

    반환: {"tx_hash", "owner_address", "block_number", "status"}
    """
    private_key = os.environ.get('PRIVATE_KEY')
    if not private_key:
        raise RuntimeError("환경변수 PRIVATE_KEY가 설정되어 있지 않습니다 (트랜잭션 서명용 지갑 개인키).")

    w3 = get_web3()
    contract = get_contract(w3)
    account = w3.eth.account.from_key(private_key)

    tx = contract.functions.registerFile(cid, filename).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address, 'pending'),
        'gas': 300000,
        'gasPrice': w3.eth.gas_price,
    })

    signed_tx = account.sign_transaction(tx)
    # web3.py v6+ 는 raw_transaction, 이전 버전은 rawTransaction 속성을 사용합니다.
    raw_tx = getattr(signed_tx, 'raw_transaction', None) or signed_tx.rawTransaction
    # Persist the signed transaction hash BEFORE broadcasting, even if the RPC
    # accepts a transaction but its response is lost. Do not persist raw_tx/keys.
    tx_hash = Web3.to_hex(Web3.keccak(raw_tx))
    if on_prepared is not None:
        on_prepared(tx_hash, account.address)
    try:
        w3.eth.send_raw_transaction(raw_tx)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    except Exception as exc:
        raise ChainPending('거래 전송 또는 확인 상태가 불확실합니다. 저장된 tx_hash를 조회하세요.') from exc
    if receipt.status != 1:
        raise ChainReverted('블록체인 파일 등록 거래가 실패했습니다.')

    return {
        "tx_hash": tx_hash,
        "owner_address": account.address,
        "block_number": receipt.blockNumber,
        "status": receipt.status
    }


def get_file_count(user_address):
    contract = get_contract()
    return contract.functions.getFileCount(Web3.to_checksum_address(user_address)).call()


def get_file(user_address, index):
    contract = get_contract()
    cid, file_name, timestamp, owner = contract.functions.getFile(
        Web3.to_checksum_address(user_address), index
    ).call()
    return {
        "cid": cid,
        "fileName": file_name,
        "timestamp": timestamp,
        "owner": owner
    }
