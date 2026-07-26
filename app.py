# -*- coding: utf-8 -*-
import os
import sys
import json
import uuid
import tempfile
import webbrowser
import cgi
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from excel_processor import ExcelSetProcessor

PORT = 8000
TEMP_DIR = os.path.join(tempfile.gettempdir(), "excel_set_analyzer")
os.makedirs(TEMP_DIR, exist_ok=True)

# In-memory storage for active file processors and analysis results
FILE_SESSIONS = {}
ANALYSIS_SESSIONS = {}

class SetAnalyzerRequestHandler(BaseHTTPRequestHandler):

    def _set_response(self, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path in ["/", "/index.html"]:
            self.serve_static_file("web/index.html", "text/html; charset=utf-8")
        elif path == "/style.css":
            self.serve_static_file("web/style.css", "text/css; charset=utf-8")
        elif path == "/app.js":
            self.serve_static_file("web/app.js", "application/javascript; charset=utf-8")
        elif path == "/api/sample":
            self.handle_get_sample()
        elif path == "/api/export":
            query_params = parse_qs(parsed_path.query)
            file_id = query_params.get("file_id", [None])[0]
            self.handle_export(file_id)
        else:
            self.send_error(404, "File Not Found")

    def serve_static_file(self, rel_path, content_type):
        full_path = os.path.join(os.path.dirname(__file__), rel_path)
        if os.path.exists(full_path):
            self._set_response(content_type=content_type)
            with open(full_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404, f"File {rel_path} not found")

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == "/api/upload":
            self.handle_upload()
        elif path == "/api/columns":
            self.handle_get_columns()
        elif path == "/api/analyze":
            self.handle_analyze()
        else:
            self.send_error(404, "Endpoint Not Found")

    def handle_upload(self):
        try:
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._set_response(status=400)
                self.wfile.write(json.dumps({'error': 'Invalid content type'}).encode('utf-8'))
                return

            # Multi-part form-data parsing
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': self.headers['Content-Type']}
            )

            if 'file' not in form:
                self._set_response(status=400)
                self.wfile.write(json.dumps({'error': 'No file uploaded'}).encode('utf-8'))
                return

            file_item = form['file']
            filename = file_item.filename
            file_id = str(uuid.uuid4())
            saved_path = os.path.join(TEMP_DIR, f"{file_id}_{filename}")

            with open(saved_path, 'wb') as f:
                f.write(file_item.file.read())

            processor = ExcelSetProcessor(saved_path)
            FILE_SESSIONS[file_id] = {
                'path': saved_path,
                'filename': filename,
                'processor': processor
            }

            sheets = processor.get_sheet_names()
            self._set_response()
            self.wfile.write(json.dumps({
                'file_id': file_id,
                'filename': filename,
                'sheets': sheets
            }).encode('utf-8'))

        except Exception as e:
            self._set_response(status=500)
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_get_columns(self):
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_len)
            data = json.loads(post_body.decode('utf-8'))

            file_id = data.get('file_id')
            sheet_name = data.get('sheet_name')

            if file_id not in FILE_SESSIONS:
                self._set_response(status=404)
                self.wfile.write(json.dumps({'error': 'Session expired'}).encode('utf-8'))
                return

            processor = FILE_SESSIONS[file_id]['processor']
            cols = processor.get_columns(sheet_name)

            self._set_response()
            self.wfile.write(json.dumps({'columns': cols}).encode('utf-8'))

        except Exception as e:
            self._set_response(status=500)
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_analyze(self):
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_len)
            data = json.loads(post_body.decode('utf-8'))

            file_id = data.get('file_id')
            if file_id not in FILE_SESSIONS:
                self._set_response(status=404)
                self.wfile.write(json.dumps({'error': 'Session expired'}).encode('utf-8'))
                return

            processor = FILE_SESSIONS[file_id]['processor']
            
            result = processor.analyze_sets(
                sheet_a=data.get('sheet_a'),
                col_a=data.get('col_a'),
                sheet_b=data.get('sheet_b'),
                col_b=data.get('col_b'),
                case_sensitive=data.get('case_sensitive', False),
                trim_space=data.get('trim_space', True),
                drop_empty=data.get('drop_empty', True)
            )

            ANALYSIS_SESSIONS[file_id] = result

            self._set_response()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            self._set_response(status=500)
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_get_sample(self):
        try:
            sample_path = os.path.join(os.path.dirname(__file__), "sample_data.xlsx")
            if not os.path.exists(sample_path):
                from test_processor import make_sample_data
                make_sample_data()

            file_id = "sample_file_id"
            processor = ExcelSetProcessor(sample_path)
            FILE_SESSIONS[file_id] = {
                'path': sample_path,
                'filename': 'sample_data.xlsx',
                'processor': processor
            }

            self._set_response()
            self.wfile.write(json.dumps({
                'file_id': file_id,
                'filename': 'sample_data.xlsx',
                'sheets': processor.get_sheet_names()
            }).encode('utf-8'))

        except Exception as e:
            self._set_response(status=500)
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def handle_export(self, file_id):
        try:
            if file_id not in FILE_SESSIONS or file_id not in ANALYSIS_SESSIONS:
                self.send_error(404, "Analysis session not found")
                return

            processor = FILE_SESSIONS[file_id]['processor']
            result = ANALYSIS_SESSIONS[file_id]

            out_filename = f"집합분석보고서_{FILE_SESSIONS[file_id]['filename']}"
            out_path = os.path.join(TEMP_DIR, out_filename)
            processor.export_excel_report(result, out_path)

            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="Set_Analysis_Report.xlsx"')
            self.end_headers()

            with open(out_path, "rb") as f:
                self.wfile.write(f.read())

        except Exception as e:
            self.send_error(500, str(e))

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, SetAnalyzerRequestHandler)
    print(f"🚀 Excel Set Analyzer Web Application Server running at http://localhost:{PORT}")
    print("브라우저가 자동으로 열립니다...")
    webbrowser.open(f"http://localhost:{PORT}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
