# -*- coding: utf-8 -*-
"""校对服务：静态文件 + POST /submit 接收勾选结果，存到审批文件
用法: python _approve_server.py 8139
"""
import json, os, sys, threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

ROOT = r"C:/Users/dhamm/WorkBuddy/巴帝摩卡背诵"
APPROVAL = os.path.join(ROOT, "校对结果.json")

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path.startswith("/submit"):
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = {}
            # 合并模式：保留历史提交，不覆盖
            old = {}
            if os.path.exists(APPROVAL):
                try:
                    old = json.load(open(APPROVAL, encoding="utf-8"))
                except Exception:
                    old = {}
            old_appr = set(old.get("approved", []))
            new_appr = set(data.get("approved", []))
            merged = sorted(old_appr | new_appr)
            data["approved"] = merged
            data["total_merged"] = len(merged)
            data["submits"] = old.get("submits", 0) + 1
            with open(APPROVAL, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(('{"ok":true,"approved":%d,"merged_total":%d,"saved":"校对结果.json"}' % (len(new_appr), len(merged))).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8139
    print("校对服务:", "http://127.0.0.1:%d" % port, "| 审批文件:", APPROVAL)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
