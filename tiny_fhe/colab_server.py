import tenseal as ts
import zipfile, json, time
def evaluate(request, response):
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

print(json.dumps(evaluate("/content/public_request.zip", "/content/colab_response.zip"), indent=2))
from google.colab import files
files.download("/content/colab_response.zip")
