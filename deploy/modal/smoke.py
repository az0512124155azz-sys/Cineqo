import modal

app = modal.App("cineqo-modal-smoke")

@app.function()
def check() -> str:
    return "Cineqo Modal connection OK"

@app.local_entrypoint()
def main():
    print(check.remote())
