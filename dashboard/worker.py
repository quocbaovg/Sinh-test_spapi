"""
DeepSeek (OpenAI-compatible) + chạy script sinh test + validate AC.
ponytail: subprocess sandbox mỏng (timeout only) — nâng cấp container/nsjail nếu production.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from openai import OpenAI

# Catalog model — ready=False = chỉ hiện trên trang Models (đang phát triển)
AI_MODELS = [
    {
        "id": "deepseek-v4-flash",
        "name": "DeepSeek-V4 Flash",
        "provider": "DeepSeek",
        "tag": "Nhanh · Rẻ",
        "desc": "Sinh test nhanh, ổn định. Phù hợp hầu hết bài HSG/CP.",
        "specs": "Flash · Latency thấp · Chi phí thấp",
        "context": "64K+ tokens",
        "latency": "~0.5–2s",
        "cost": "Thấp",
        "strength": "Sinh test / JSON ổn định",
        "endpoint": "OpenAI-compatible",
        "default": True,
        "ready": True,
    },
    {
        "id": "deepseek-v4-pro",
        "name": "DeepSeek-V4 Pro",
        "provider": "DeepSeek",
        "tag": "Mạnh · Chậm hơn",
        "desc": "Chất lượng cao hơn, case biên/khó tốt hơn. Tốn token & thời gian hơn Flash.",
        "specs": "Pro · Latency trung bình · Chi phí cao hơn",
        "context": "64K+ tokens",
        "latency": "~1–5s",
        "cost": "Cao hơn",
        "strength": "Biên / bài khó / chất lượng",
        "endpoint": "OpenAI-compatible",
        "default": False,
        "ready": True,
    },
    {
        "id": "kimi-k2",
        "name": "Kimi K2",
        "provider": "Moonshot",
        "tag": "Context dài",
        "desc": "Model context siêu dài của Moonshot — phù hợp đề dài / nhiều ảnh.",
        "specs": "K2 · Context dài · Đa modal",
        "context": "128K–1M",
        "latency": "—",
        "cost": "—",
        "strength": "Đề dài / multimodal",
        "endpoint": "Chưa tích hợp",
        "default": False,
        "ready": False,
    },
    {
        "id": "fable",
        "name": "Fable",
        "provider": "Cursor",
        "tag": "Reasoning",
        "desc": "Model reasoning mạnh — dự kiến dùng cho bài khó / case biên phức tạp.",
        "specs": "Reasoning · Chất lượng cao",
        "context": "—",
        "latency": "—",
        "cost": "—",
        "strength": "Suy luận / bài khó",
        "endpoint": "Chưa tích hợp",
        "default": False,
        "ready": False,
    },
    {
        "id": "gpt-4o",
        "name": "GPT-4o",
        "provider": "OpenAI",
        "tag": "Multimodal",
        "desc": "Model đa phương thức phổ biến — đọc đề ảnh tốt, JSON ổn định.",
        "specs": "4o · Vision · JSON mode",
        "context": "128K",
        "latency": "—",
        "cost": "—",
        "strength": "Vision / đề ảnh",
        "endpoint": "Chưa tích hợp",
        "default": False,
        "ready": False,
    },
    {
        "id": "claude-sonnet",
        "name": "Claude Sonnet",
        "provider": "Anthropic",
        "tag": "Code · Logic",
        "desc": "Mạnh về code và logic — tiềm năng sinh script validate chất lượng cao.",
        "specs": "Sonnet · Code-aware",
        "context": "200K",
        "latency": "—",
        "cost": "—",
        "strength": "Code / logic",
        "endpoint": "Chưa tích hợp",
        "default": False,
        "ready": False,
    },
    {
        "id": "gemini-2.5-pro",
        "name": "Gemini 2.5 Pro",
        "provider": "Google",
        "tag": "Vision · Context",
        "desc": "Context lớn + vision mạnh — dự kiến hỗ trợ đề PDF/ảnh nhiều trang.",
        "specs": "2.5 Pro · Vision",
        "context": "1M+",
        "latency": "—",
        "cost": "—",
        "strength": "Vision / context lớn",
        "endpoint": "Chưa tích hợp",
        "default": False,
        "ready": False,
    },
]

ALLOWED_LANGS = {"python", "cpp"}


def ready_models() -> list[dict]:
    """Model đã mở — dùng cho hub select + validate job."""
    return [m for m in AI_MODELS if m.get("ready", True)]


def probe_models_status() -> list[dict]:
    """
    Kiểm tra API key + endpoint. Gắn đèn trạng thái cho từng model trong catalog.
    Model ready=False → luôn 'Đang phát triển' (không ping).
    ponytail: 1 lần list models — không ping từng model riêng.
    """
    import time

    def _dev_row(m: dict) -> dict:
        return {
            **m,
            "status": "dev",
            "status_label": "Đang phát triển",
            "status_detail": "Sắp tích hợp · chưa mở endpoint",
            "latency_ms": None,
        }

    key = getattr(settings, "DEEPSEEK_API_KEY", "") or ""
    if not key:
        rows = []
        for m in AI_MODELS:
            if not m.get("ready", True):
                rows.append(_dev_row(m))
            else:
                rows.append({
                    **m,
                    "status": "offline",
                    "status_label": "Offline",
                    "status_detail": "Thiếu DEEPSEEK_API_KEY",
                    "latency_ms": None,
                })
        return rows

    available_ids: set[str] = set()
    latency_ms = None
    err = None
    try:
        t0 = time.perf_counter()
        client = _client()
        listed = client.models.list()
        latency_ms = int((time.perf_counter() - t0) * 1000)
        for item in getattr(listed, "data", []) or []:
            mid = getattr(item, "id", None)
            if mid:
                available_ids.add(mid)
    except Exception as e:
        err = str(e)[:120]

    rows = []
    for m in AI_MODELS:
        if not m.get("ready", True):
            rows.append(_dev_row(m))
            continue
        row = dict(m)
        if err:
            row.update({
                "status": "offline",
                "status_label": "Offline",
                "status_detail": err,
                "latency_ms": None,
            })
        else:
            # Endpoint sống → đèn xanh cho model ready
            online = latency_ms is not None and not err
            row.update({
                "status": "online" if online else "degraded",
                "status_label": "Hoạt động tốt" if online else "Cảnh báo",
                "status_detail": (
                    f"Endpoint OK · ping {latency_ms}ms"
                    if online and latency_ms is not None
                    else "Key OK nhưng id không có trong /models"
                ),
                "latency_ms": latency_ms,
            })
        rows.append(row)
    return rows


def _client() -> OpenAI:
    key = getattr(settings, "DEEPSEEK_API_KEY", "") or ""
    if not key:
        raise RuntimeError("Thiếu DEEPSEEK_API_KEY trong .env")
    return OpenAI(
        api_key=key,
        base_url=getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


def _system_prompt(n: int, language: str) -> str:
    lang_note = "Python 3" if language == "python" else "C++17 (stdin/stdout)"
    return f"""Bạn là engine sinh testcase cho competitive programming.
Trả về ĐÚNG một JSON object (không markdown):

{{
  "script": "<toàn bộ mã Python>"
}}

QUY TẮC BẮT BUỘC cho `script` (vi phạm = sai):

1) Viết HÀM THAM CHIẾU (thuật toán đúng) dựa trên đề + code AC, ví dụ:
   def solve(...):  # hoặc brute-force đúng nếu AC tối ưu
       ...
       return answer

2) SINH INPUT BẰNG RANDOM theo ràng buộc đề (randint, sample, shuffle...).
   KHÔNG được hardcode từng bộ số cố định kiểu:
     cases.append({{"input": "1 2", "expected": "3"}})  ← CẤM

3) Tính expected BẰNG CÁCH GỌI thuật toán tham chiếu trên input vừa random:
     inp = gen_input()
     expected = format_output(solve(...))
   Không gán expected bằng tay.

4) Cấu trúc gợi ý:
   - import json, random, ...
   - def solve(...): ...
   - def gen_one(kind):  # NOMINAL / BOUNDARY / ...
         # random input trong bound
         # return (input_str, expected_str, type)
   - main: tạo đúng ~{n} case (trộn nominal + boundary), print(json.dumps(list))

5) Mỗi phần tử JSON: {{"id":"TC-001","input":"...","expected":"...","type":"NOMINAL|BOUNDARY|OVERFLOW|NULL_VAL"}}
   - `input` = chuỗi stdin cho chương trình AC ({lang_note})
   - `expected` = stdout đúng (strip), kết quả từ solve(), không bịa

6) Không mạng, không ghi file; chỉ stdlib: json, random, math, itertools, string, sys.
"""


def request_gen_script(
    problem: str,
    ac_code: str,
    *,
    attempt: int = 1,
    testcase_count: int = 8,
    language: str = "python",
    ai_model: str = "deepseek-v4-flash",
    image_paths: list[str] | None = None,
) -> str:
    """Gọi DeepSeek, ép JSON, lấy script Python sinh test. Có thể kèm ảnh đề."""
    n = max(3, min(int(testcase_count or 8), 30))
    language = language if language in ALLOWED_LANGS else "python"
    model_ids = {m["id"] for m in ready_models()}
    model = ai_model if ai_model in model_ids else "deepseek-v4-flash"
    image_paths = image_paths or []

    client = _client()
    text = (
        f"Lần thử: {attempt}\n"
        f"Số testcase cần: {n}\n"
        f"Ngôn ngữ code AC: {language}\n"
        f"Số ảnh đề đính kèm: {len(image_paths)}\n\n"
        f"=== ĐỀ BÀI (text) ===\n{(problem or '(xem ảnh đính kèm)').strip()}\n\n"
        f"=== CODE AC ({language}) — dùng để viết lại thuật toán tham chiếu Python ===\n"
        f"{ac_code}\n\n"
        "YÊU CẦU SCRIPT:\n"
        "- Viết hàm solve()/thuật toán ngược (tham chiếu đúng) từ AC.\n"
        "- Random sinh input theo ràng buộc đề.\n"
        "- expected = kết quả chạy thuật toán trên input đó.\n"
        "- CẤM hardcode từng test cố định (input/expected gán số sẵn).\n"
        "- Mỗi lần chạy script phải ra bộ test khác nhau (trừ vài case biên cố ý).\n"
        + (
            "Lần chạy lại: tăng tỷ lệ case biên / case khó, vẫn phải random + solve().\n"
            if attempt > 1
            else ""
        )
    )

    if image_paths:
        content: list[dict] = [{"type": "text", "text": text}]
        for p in image_paths[:5]:
            content.append({
                "type": "image_url",
                "image_url": {"url": _file_to_data_url(p)},
            })
        user_message: dict = {"role": "user", "content": content}
    else:
        user_message = {"role": "user", "content": text}

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _system_prompt(n, language)},
                user_message,
            ],
            response_format={"type": "json_object"},
            temperature=0.5 if attempt == 1 else 0.75,
        )
    except Exception as e:
        # Một số model DeepSeek chưa nhận ảnh — fallback text-only
        if image_paths:
            fallback = text + (
                "\n\n[Lưu ý: có ảnh đề nhưng API không nhận ảnh lần này — "
                f"dựa vào text. Chi tiết lỗi: {e}]"
            )
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _system_prompt(n, language)},
                    {"role": "user", "content": fallback},
                ],
                response_format={"type": "json_object"},
                temperature=0.5 if attempt == 1 else 0.75,
            )
        else:
            raise

    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    script = (data.get("script") or "").strip()
    if not script:
        raise RuntimeError("DeepSeek trả JSON nhưng thiếu field `script`")
    script = re.sub(r"^```(?:python)?\s*", "", script)
    script = re.sub(r"\s*```$", "", script)
    return script


def _file_to_data_url(path: str) -> str:
    import base64
    import mimetypes

    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def run_python_script(script: str, timeout: int = 15) -> list[dict]:
    """Chạy script sinh test, parse JSON array từ stdout."""
    with tempfile.TemporaryDirectory(prefix="ugt_") as tmp:
        path = Path(tmp) / "gen_tests.py"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmp,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "unknown")[:500]
            raise RuntimeError(f"Script sinh test lỗi: {err}")
        out = (proc.stdout or "").strip()
        start = out.find("[")
        end = out.rfind("]")
        if start < 0 or end < 0:
            raise RuntimeError(f"Script không in JSON array. stdout={out[:300]}")
        cases = json.loads(out[start : end + 1])
        if not isinstance(cases, list) or not cases:
            raise RuntimeError("Danh sách testcase rỗng hoặc không hợp lệ")
        cleaned = []
        for i, c in enumerate(cases, 1):
            cleaned.append({
                "id": str(c.get("id") or f"TC-{i:03d}"),
                "input": str(c.get("input", "")),
                "expected": str(c.get("expected", "")).strip(),
                "type": str(c.get("type") or "NOMINAL"),
                "got": "",
                "ok": False,
            })
        return cleaned


def _compile_cpp(src: Path, out_bin: Path, timeout: int = 20) -> None:
    gxx = shutil.which("g++")
    if not gxx:
        raise RuntimeError(
            "Không tìm thấy g++. Cài MinGW/MSYS2 hoặc dùng ngôn ngữ Python."
        )
    proc = subprocess.run(
        [gxx, "-O2", "-std=c++17", str(src), "-o", str(out_bin)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Compile C++ lỗi: {(proc.stderr or proc.stdout)[:400]}")


def validate_ac(
    ac_code: str,
    cases: list[dict],
    language: str = "python",
    timeout: int = 5,
) -> list[dict]:
    """Chạy code AC (Python hoặc C++) với từng input, so khớp expected."""
    language = language if language in ALLOWED_LANGS else "python"
    results = []

    with tempfile.TemporaryDirectory(prefix="ugt_ac_") as tmp:
        tmp_path = Path(tmp)

        if language == "python":
            ac_path = tmp_path / "ac.py"
            ac_path.write_text(ac_code, encoding="utf-8")
            run_cmd = [sys.executable, str(ac_path)]
        else:
            src = tmp_path / "ac.cpp"
            exe = tmp_path / ("ac.exe" if sys.platform == "win32" else "ac")
            src.write_text(ac_code, encoding="utf-8")
            _compile_cpp(src, exe)
            run_cmd = [str(exe)]

        for case in cases:
            item = dict(case)
            try:
                proc = subprocess.run(
                    run_cmd,
                    input=case.get("input", ""),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmp,
                )
                got = (proc.stdout or "").strip()
                item["got"] = got
                if proc.returncode != 0:
                    item["ok"] = False
                    item["got"] = (proc.stderr or got or f"exit {proc.returncode}")[:200]
                else:
                    item["ok"] = got == str(case.get("expected", "")).strip()
            except subprocess.TimeoutExpired:
                item["got"] = "TIMEOUT"
                item["ok"] = False
            results.append(item)
    return results
