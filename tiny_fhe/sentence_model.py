"""Experimental learned fixed-length conditional token model over CKKS.

Not a transformer/LLM or medical product. Token selection happens on the client.
Only ciphertext matrix multiplication is performed by the evaluator.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import numpy as np

EOS = '<끝>'
# Fictional drugs and synthetic instructions, not medical guidance.
TRAINING_PAIRS = [
    ('가상약A 1정 처방', '실험용 문구입니다 음주를 피하세요'),
    ('가상약B 1정 처방', '실험용 문구입니다 식사 시간을 확인하세요'),
]


def train():
    """Learn token-position classifiers with cross-entropy gradient descent."""
    inputs = sorted({w for prompt, _ in TRAINING_PAIRS for w in prompt.split()})
    outputs = sorted({EOS} | {w for _, answer in TRAINING_PAIRS for w in answer.split()})
    length = max(len(answer.split()) for _, answer in TRAINING_PAIRS) + 1
    x = np.array([[prompt.split().count(w) for w in inputs] + [1.0]
                  for prompt, _ in TRAINING_PAIRS], dtype=float)
    targets = np.zeros((len(x), length, len(outputs)))
    for i, (_, answer) in enumerate(TRAINING_PAIRS):
        words = answer.split() + [EOS] * length
        for pos in range(length):
            targets[i, pos, outputs.index(words[pos])] = 1
    weights = np.zeros((x.shape[1], length * len(outputs)))
    for _ in range(600):
        logits = (x @ weights).reshape(targets.shape)
        exp = np.exp(logits - logits.max(axis=2, keepdims=True))
        probabilities = exp / exp.sum(axis=2, keepdims=True)
        gradient = x.T @ (probabilities - targets).reshape(len(x), -1) / len(x)
        weights -= 0.2 * gradient
    return dict(kind='learned-conditional-token-model', input_vocab=inputs,
                output_vocab=outputs, output_length=length, weights=weights.tolist())


def encode(prompt, model):
    # Input validation is local; the inference process never receives this text.
    if not isinstance(prompt, str) or prompt.strip() not in {p for p, _ in TRAINING_PAIRS}:
        raise ValueError('지원 입력: ' + ' / '.join(p for p, _ in TRAINING_PAIRS))
    return [float(prompt.split().count(w)) for w in model['input_vocab']] + [1.0]


def prepare(folder, prompt):
    import tenseal as ts
    model = train()
    vector = encode(prompt, model)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'secret.key').exists():
        raise ValueError('새 작업 폴더를 사용하세요.')
    context = ts.context(ts.SCHEME_TYPE.CKKS, poly_modulus_degree=8192,
                         coeff_mod_bit_sizes=[60, 40, 40, 60])
    context.global_scale = 2 ** 40
    context.generate_galois_keys()
    (folder / 'secret.key').write_bytes(context.serialize(save_secret_key=True))
    public = context.serialize(save_secret_key=False)
    if ts.context_from(public).has_secret_key():
        raise RuntimeError('Public context contains a secret key')
    # Local state is never included in public_request.zip.
    (folder / 'client.json').write_text(json.dumps({'vector': vector, 'model': model}), encoding='utf-8')
    with zipfile.ZipFile(folder / 'public_request.zip', 'w') as z:
        z.writestr('context.bin', public)
        z.writestr('input.bin', ts.ckks_vector(context, vector).serialize())
        z.writestr('model.json', json.dumps(model))


def evaluate(request_path, response_path):
    import tenseal as ts
    with zipfile.ZipFile(request_path) as z:
        if set(z.namelist()) != {'context.bin', 'input.bin', 'model.json'}:
            raise ValueError('Invalid public request')
        if sum(i.file_size for i in z.infolist()) > 64 * 1024 * 1024:
            raise ValueError('Request too large')
        context = ts.context_from(z.read('context.bin'))
        if context.has_secret_key():
            raise ValueError('Evaluator must not receive secret keys')
        model = json.loads(z.read('model.json'))
        encrypted = ts.ckks_vector_from(context, z.read('input.bin'))
        weights = np.asarray(model['weights'], dtype=float)
        if weights.ndim != 2 or max(weights.shape) > 512 or not np.isfinite(weights).all():
            raise ValueError('Invalid weights')
        if encrypted.size() != weights.shape[0]:
            raise ValueError('Invalid input shape')
        # No plaintext prompt, output lookup, or secret key in this computation.
        encrypted_logits = encrypted.matmul(weights.tolist())
    with zipfile.ZipFile(response_path, 'w') as z:
        z.writestr('logits.bin', encrypted_logits.serialize())
        z.writestr('server.json', json.dumps({'server_has_secret_key': False,
                                            'operation': 'ciphertext-matrix-multiplication'}))


def finish(folder, response_path):
    import tenseal as ts
    folder = Path(folder)
    local = json.loads((folder / 'client.json').read_text(encoding='utf-8'))
    model = local['model']
    context = ts.context_from((folder / 'secret.key').read_bytes())
    with zipfile.ZipFile(response_path) as z:
        actual = np.array(ts.ckks_vector_from(context, z.read('logits.bin')).decrypt())
    expected = np.asarray(local['vector']) @ np.asarray(model['weights'])
    if actual.shape != expected.shape or not np.isfinite(actual).all():
        raise ValueError('Invalid output shape')
    error = float(np.max(np.abs(actual - expected)))
    # Comparison is a local experiment check, not cryptographic server attestation.
    if error > 0.001:
        raise ValueError('CKKS numerical verification failed')
    actual_ids = actual.reshape(model['output_length'], -1).argmax(axis=1)
    expected_ids = expected.reshape(model['output_length'], -1).argmax(axis=1)
    if not np.array_equal(actual_ids, expected_ids):
        raise ValueError('Prediction mismatch')
    words = []
    for index in actual_ids:
        word = model['output_vocab'][int(index)]
        if word == EOS:
            break
        words.append(word)
    return {'explanation': ' '.join(words), 'model': model['kind'],
            'execution': 'local-encrypt/separate-process-ckks/local-decrypt',
            'medical_llm': False, 'clinically_validated': False,
            'max_error': error, 'verified': True,
            'notice': '가상 약물로 만든 실험입니다. 실제 복약 안내에 사용하지 마세요.'}


def generate(prompt):
    with tempfile.TemporaryDirectory(prefix='encrypted-sentence-') as folder:
        prepare(folder, prompt)
        request_path = Path(folder) / 'public_request.zip'
        response_path = Path(folder) / 'response.zip'
        subprocess.run([sys.executable, str(Path(__file__).resolve()), 'evaluate',
                        str(request_path), str(response_path)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        return finish(folder, response_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['demo', 'prepare', 'evaluate', 'finish'], nargs='?', default='demo')
    parser.add_argument('path', nargs='?')
    parser.add_argument('other', nargs='?')
    args = parser.parse_args()
    if args.command == 'demo':
        print('입력 예: 가상약A 1정 처방 / 가상약B 1정 처방')
        result = generate(args.path or input('처방 문장: ').strip())
    elif args.command == 'prepare':
        prepare(args.path, args.other)
        result = {'public_request': str(Path(args.path) / 'public_request.zip')}
    elif args.command == 'evaluate':
        evaluate(args.path, args.other)
        result = {'evaluated': True}
    else:
        result = finish(args.path, args.other)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
