// Command server runs codejudge-mcp: an MCP server (Streamable HTTP transport)
// that wraps CodeJudge's public HTTP API as tools an AI agent can call. It is a
// separate deployable from CodeJudge (D1) and the only thing that talks to
// CodeJudge (D4: MCP over Streamable HTTP; the agent never sees CodeJudge's API
// directly).
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"codejudge-mcp/internal/codejudge"
	"codejudge-mcp/internal/tools"
)

func main() {
	// Config via env, matching the microservice style: nothing is hardcoded to a
	// single host so the same binary runs locally and in a container.
	codejudgeURL := envOr("CODEJUDGE_BASE_URL", "http://localhost:8080")
	listenAddr := envOr("MCP_LISTEN_ADDR", ":8081")

	client := codejudge.NewClient(codejudgeURL)

	// Best-effort reachability check at boot: log a warning if CodeJudge isn't up
	// yet, but still start — CodeJudge may come up after us, and tools report
	// their own errors per-call.
	bootCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	if err := client.Healthz(bootCtx); err != nil {
		slog.Warn("codejudge not reachable at boot (tools will error until it is)", "url", codejudgeURL, "error", err)
	} else {
		slog.Info("codejudge reachable", "url", codejudgeURL)
	}
	cancel()

	server := mcp.NewServer(&mcp.Implementation{
		Name:    "codejudge-mcp",
		Version: "0.1.0",
	}, nil)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "get_problem_spec",
		Description: "Look up one CodeJudge problem's public spec: its grading mode, function signature/entry point, resource limits, and sample (visible) test cases. Use this to answer questions about a specific existing problem instead of guessing.",
	}, tools.GetProblemSpec(client))

	handler := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server {
		return server
	}, nil)

	slog.Info("codejudge-mcp listening", "addr", listenAddr, "codejudge", codejudgeURL)
	if err := http.ListenAndServe(listenAddr, handler); err != nil {
		slog.Error("server error", "error", err)
		os.Exit(1)
	}
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
