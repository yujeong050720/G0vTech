import requests
import os

PINATA_JWT = os.environ.get("PINATA_JWT")

UPLOAD_URL = "https://uploads.pinata.cloud/v3/files"
LIST_FILES_URL = "https://api.pinata.cloud/v3/files/public"
NETWORK = "public"


def upload_file_to_pinata(file_path, name=None):
    if not PINATA_JWT:
        print("❌ 오류: PINATA_JWT 환경변수가 설정되지 않았습니다.")
        return None

    if not os.path.exists(file_path):
        print(f"❌ 오류: '{file_path}' 파일을 찾을 수 없습니다.")
        return None

    display_name = name or os.path.basename(file_path)
    headers = {"Authorization": f"Bearer {PINATA_JWT}"}

    print(f"🚀 Pinata(IPFS)에 '{file_path}' 업로드 중...")

    try:
        with open(file_path, 'rb') as f:
            files = {'file': (display_name, f)}
            data = {"network": NETWORK, "name": display_name}
            response = requests.post(UPLOAD_URL, headers=headers, files=files, data=data, timeout=60)

        if response.status_code in (200, 201):
            cid = response.json()["data"]["cid"]
            print("✅ 업로드 성공!")
            print(f"🎉 반환된 CID: {cid}")
            return cid
        else:
            print(f"❌ 업로드 실패. 상태 코드: {response.status_code}")
            print(response.text)
            return None

    except Exception as e:
        print(f"업로드 중 오류 발생: {e}")
        return None


def check_pin_status(cid):
    if not PINATA_JWT:
        print("❌ 오류: PINATA_JWT 환경변수가 설정되지 않았습니다.")
        return False

    headers = {"Authorization": f"Bearer {PINATA_JWT}"}
    response = requests.get(LIST_FILES_URL, headers=headers, params={"cid": cid}, timeout=30)

    if response.status_code != 200:
        print(f"❌ 저장 상태 조회 실패 ({response.status_code}): {response.text}")
        return False

    files = response.json().get("data", {}).get("files", [])
    return any(f.get("cid") == cid for f in files)


if __name__ == "__main__":
    test_file_name = "encrypted.bin"
    
    returned_cid = upload_file_to_pinata(test_file_name)

    if returned_cid:
        print("📌 저장 상태 확인 중...")
        stored = check_pin_status(returned_cid)
        print("Stored:", "✅ True" if stored else "❌ False")