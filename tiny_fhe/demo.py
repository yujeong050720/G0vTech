"""Actual CKKS next-token inference; a learned bigram model, NOT a medical LLM.

Only prepare/finish touch the secret key. evaluate works on a public ZIP.
"""
import argparse
import json
import math
from pathlib import Path
import time
import zipfile


# User-provided experimental text; not clinically validated medication guidance.
CORPUS = [
    "타이레놀 음주 금지",
    "타이레놀 담배 금지",
    "바라크루드는 식사 전후 2시간에 복용",
    "판피린 큐는 음주 금지",
]


def train():
    sentences = [s.split() + ["<끝>"] for s in CORPUS]
    vocab = sorted({t for s in sentences for t in s})
    counts = [[0.1] * len(vocab) for _ in vocab]
    for sentence in sentences:
        for a, b in zip(sentence, sentence[1:]):
            counts[vocab.index(a)][vocab.index(b)] += 1
    weights = [[math.log(c / sum(row)) for c in row] for row in counts]
    return {"kind": "synthetic-bigram-log-probabilities", "vocab": vocab, "weights": weights}


def prepare(folder, tokens=None):
    import tenseal as ts
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / "secret.key").exists():
        raise FileExistsError("Existing client key: choose a new folder to preserve pending responses")
    model = train()
    tokens = ["음악", "산책"] if tokens is None else tokens
    if not isinstance(tokens, list) or len(tokens) != 2 or any(t not in model['vocab'] for t in tokens):
        raise ValueError('Exactly two vocabulary tokens are required')
    ctx = ts.context(ts.SCHEME_TYPE.CKKS, poly_modulus_degree=8192,
                     coeff_mod_bit_sizes=[60, 40, 40, 60])
    ctx.global_scale = 2 ** 40
    ctx.generate_galois_keys()
    # Secret file NEVER belongs in an upload or source archive.
    (folder / "secret.key").write_bytes(ctx.serialize(save_secret_key=True))
    public = ctx.serialize(save_secret_key=False)
    assert not ts.context_from(public).has_secret_key()
    local = {"tokens": tokens, "model": model}
    (folder / "client.json").write_text(json.dumps(local, ensure_ascii=False), encoding="utf-8")
    with zipfile.ZipFile(folder / "public_request.zip", "w", zipfile.ZIP_STORED) as z:
        z.writestr("public_context.bin", public)
        z.writestr("model.json", json.dumps(model, ensure_ascii=False))
        for i, token in enumerate(tokens):
            vector = [float(t == token) for t in model["vocab"]]
            z.writestr(f"input_{i}.bin", ts.ckks_vector(ctx, vector).serialize())
    return {"request_bytes": (folder / "public_request.zip").stat().st_size,
            "cases": len(tokens), "secret_uploaded": False}


def evaluate(request, response):
    import tenseal as ts
    started = time.perf_counter()
    with zipfile.ZipFile(request) as z:
        names = set(z.namelist())
        if names != {"public_context.bin", "model.json", "input_0.bin", "input_1.bin"}:
            raise ValueError("Unexpected request entries")
        ctx = ts.context_from(z.read("public_context.bin"))
        if ctx.has_secret_key():
            raise ValueError("Server must never receive a secret key")
        model = json.loads(z.read("model.json"))
        outputs = []
        for i in range(2):
            encrypted = ts.ckks_vector_from(ctx, z.read(f"input_{i}.bin"))
            try:
                encrypted.decrypt()
            except ValueError:
                pass
            else:
                raise AssertionError("Server could decrypt input")
            outputs.append(encrypted.matmul(model["weights"]).serialize())
    report = {"server_has_secret_key": False, "server_decrypt_blocked": True,
              "seconds": time.perf_counter() - started,
              "tenseal_version": ts.__version__, "cases": len(outputs)}
    with zipfile.ZipFile(response, "w", zipfile.ZIP_STORED) as z:
        for i, ciphertext in enumerate(outputs):
            z.writestr(f"output_{i}.bin", ciphertext)
        z.writestr("server_report.json", json.dumps(report))
    return report


def finish(folder, response):
    import tenseal as ts
    folder = Path(folder)
    ctx = ts.context_from((folder / "secret.key").read_bytes())
    local = json.loads((folder / "client.json").read_text(encoding="utf-8"))
    model = local["model"]
    rows = []
    with zipfile.ZipFile(response) as z:
        server = json.loads(z.read("server_report.json"))
        for i, token in enumerate(local["tokens"]):
            actual = ts.ckks_vector_from(ctx, z.read(f"output_{i}.bin")).decrypt()
            expected = model["weights"][model["vocab"].index(token)]
            error = max(abs(a-b) for a, b in zip(actual, expected))
            predicted = model["vocab"][max(range(len(actual)), key=actual.__getitem__)]
            baseline = model["vocab"][max(range(len(expected)), key=expected.__getitem__)]
            assert predicted == baseline and error < 0.001
            rows.append({"input": token, "prediction": predicted,
                         "plaintext_prediction": baseline, "max_error": error})
    report = {"model": model["kind"], "vocab_size": len(model["vocab"]),
              "server": server, "results": rows, "passed": True}
    (folder / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["prepare", "evaluate", "finish"])
    p.add_argument("path")
    p.add_argument("other", nargs="?")
    a = p.parse_args()
    result = {"prepare": lambda: prepare(a.path),
              "evaluate": lambda: evaluate(a.path, a.other),
              "finish": lambda: finish(a.path, a.other)}[a.command]()
    print(json.dumps(result, ensure_ascii=False, indent=2))
