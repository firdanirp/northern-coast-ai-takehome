from http.server import BaseHTTPRequestHandler
import json
import os

from lib.models import LeadInput, ScoredOutput
from lib.extractor import extract_signals
from lib.scorer import compute_score
from lib.fallback import fallback_score


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        # 1. Read body
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        # 2. Parse JSON
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as e:
            self._json(400, {"error": "Invalid JSON", "detail": str(e)})
            return

        # 3. Validate input structure
        try:
            lead = LeadInput(**data)
        except Exception as e:
            self._json(400, {"error": "Invalid input schema", "detail": str(e)})
            return

        # 4. Handle empty conversation gracefully
        if not lead.conversation:
            result = ScoredOutput(
                lead_id=lead.lead_id,
                score=0,
                tier="Cold",
                routing="auto_archive",
                reasoning="No conversation content provided — insufficient data to score.",
            )
            self._json(200, result.model_dump())
            return

        # 5. LLM extraction → deterministic scoring, with keyword fallback
        signals = extract_signals(lead)
        if signals is not None:
            result = compute_score(signals, lead.lead_id)
        else:
            result = fallback_score(lead)

        self._json(200, result.model_dump())

    def do_GET(self):
        self._json(200, {
            "service": "ncb-lead-scoring-agent",
            "version": "1.0.0",
            "status": "ok",
            "usage": "POST /api/score with {lead_id, channel, conversation[]}",
        })

    def log_message(self, format, *args):
        pass  # Suppress default access logs in Vercel

    def _json(self, status: int, body: dict):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
