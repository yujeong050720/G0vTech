"""One-command local experiment: IPFS/blockchain storage + real CKKS."""
import io
import json
import os
import secrets
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', type=Path, help='업로드할 처방전 JSON')
    args = parser.parse_args()
    os.environ['LOCAL_API_TOKEN'] = secrets.token_urlsafe(32)
    from app import app
    print('기존 Pinata IPFS 업로드·블록체인 등록 + 동형암호 AI를 실행합니다.')
    if args.file:
        document = json.loads(args.file.read_text(encoding='utf-8-sig'))
    else:
        print('입력 예: 가상약A 1정 처방 / 가상약B 1정 처방')
        prompt = input('처방 문장 (Enter=가상약A 1정 처방): ').strip() or '가상약A 1정 처방'
        document = {'patient_ref': 'demo-patient-001', 'prescription': prompt}
    headers = {'Authorization': 'Bearer '+os.environ['LOCAL_API_TOKEN']}
    client = app.test_client()
    result = client.post('/hospital/prescriptions', headers=headers,
                         data={'file': (io.BytesIO(json.dumps(document, ensure_ascii=False).encode()), 'prescription.json')})
    print(json.dumps(result.json, ensure_ascii=False, indent=2))
    if result.status_code in (201, 207):
        records = client.get('/hospital/patients/'+result.json['patient_ref']+'/records', headers=headers)
        print('이 환자의 저장 기록:', records.json['count'])


if __name__ == '__main__':
    main()
