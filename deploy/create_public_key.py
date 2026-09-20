"""Generate a local decryption key; print only its public counterpart."""
import base64
from pathlib import Path
from Crypto.PublicKey import RSA

target = Path('local_data/web-owner-private.pem')
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists():
    key = RSA.import_key(target.read_bytes())
else:
    key = RSA.generate(3072)
    with target.open('xb') as stream:
        stream.write(key.export_key(pkcs=8))
print('HOSPITAL_PUBLIC_KEY_B64:')
print(base64.b64encode(key.publickey().export_key()).decode())
print('Keep the private key locally:', target)
