import base64, json, sys, urllib.request, importlib.util
spec = importlib.util.spec_from_file_location("x", "4_extract.py")
X = importlib.util.module_from_spec(spec); spec.loader.exec_module(X)
X.load_env(); cfg = X.llm_config()
pdf = sys.argv[1]; model = sys.argv[2] if len(sys.argv) > 2 else cfg["LLM_MODEL"]
b64 = base64.b64encode(open(pdf, "rb").read()).decode()
q = {"type": "text", "text": "What is the partnership name printed in item B? Reply with the exact text only."}
for label, part in [("image_url", {"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{b64}"}}),
                    ("file", {"type": "file", "file": {"file_data": f"data:application/pdf;base64,{b64}"}})]:
    body = json.dumps({"model": model, "temperature": 0,
                       "messages": [{"role": "user", "content": [q, part]}]}).encode()
    req = urllib.request.Request(cfg["LLM_BASE_URL"].rstrip("/") + "/chat/completions", body,
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {cfg['LLM_API_KEY']}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print(model, label, "->", json.loads(r.read())["choices"][0]["message"]["content"][:200])
    except Exception as e:
        print(model, label, "-> FAILED", type(e).__name__, getattr(e, "code", ""))