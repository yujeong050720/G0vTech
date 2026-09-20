// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract FileRegistry {
    // 1. 블록체인에 기록할 파일 정보의 형태 (구조체)
    struct FileRecord {
        string cid;          // IPFS에서 받아온 해시값 (예: Qm...)
        string fileName;     // 암호화된 파일 이름
        uint256 timestamp;   // 블록체인에 기록된 시간
        address owner;       // 파일을 올린 사람의 지갑 주소
    }

    // 2. 지갑 주소(소유자)를 열쇠로 삼아, 그 사람이 올린 파일 목록을 저장하는 사전(mapping)
    mapping(address => FileRecord[]) private userFiles;

    // 3. 파일 등록 알림 기능 (선택 사항이지만 프론트엔드 연동 시 유용함)
    event FileRegistered(address indexed owner, string cid, string fileName, uint256 timestamp);

    // 4. [핵심 기능] 새로운 파일을 블록체인에 등록하는 함수
    function registerFile(string memory _cid, string memory _fileName) public {
        // 새로운 기록 생성
        FileRecord memory newRecord = FileRecord({
            cid: _cid,
            fileName: _fileName,
            timestamp: block.timestamp, // 현재 블록이 생성된 시간
            owner: msg.sender           // 이 함수를 실행한 사람의 지갑 주소
        });

        // 소유자의 파일 목록에 추가
        userFiles[msg.sender].push(newRecord);

        // 등록되었다고 네트워크에 알림
        emit FileRegistered(msg.sender, _cid, _fileName, block.timestamp);
    }

    // 5. 특정 사용자가 등록한 파일의 총 개수를 확인하는 함수
    function getFileCount(address _user) public view returns (uint256) {
        return userFiles[_user].length;
    }

    // 6. 특정 사용자의 특정 파일을 조회하는 함수
    function getFile(address _user, uint256 _index) public view returns (string memory, string memory, uint256, address) {
        FileRecord memory file = userFiles[_user][_index];
        return (file.cid, file.fileName, file.timestamp, file.owner);
    }
}