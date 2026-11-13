"""Regression for Cloud9 runner-web's native, official ChatGPT-Web Codex MCP entry."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TestMcpPackage(unittest.TestCase):
    def test_native_mcp_bundle_is_packaged_version_aware(self):
        dockerfile = (ROOT / "overlays/Dockerfile.cloud9-branding").read_text()
        self.assertIn("COPY --from=mcpvendor", dockerfile)
        self.assertIn("mcp-server.ts", dockerfile)
        self.assertIn("mcp-server.js", dockerfile)
        self.assertIn("esbuild", dockerfile)
        self.assertIn("runChatGptMcpServer", dockerfile)
        self.assertIn('{"type":"module"}', dockerfile)

    def test_ci_uses_exact_upstream_source_not_local_bridge(self):
        workflow = (ROOT / ".github/workflows/ghcr-candidate.yml").read_text()
        self.assertIn("--build-context mcpvendor=./upstream/open-sse/vendor/codex-chatgpt-web", workflow)
        self.assertIn("branches: [main, 'fix/**']", workflow)
        self.assertIn("CHATGPT_WEB_CODEX_MCP_BUNDLE_PASS", workflow)
        self.assertNotIn("curl | bash", workflow)

if __name__ == "__main__":
    unittest.main()
