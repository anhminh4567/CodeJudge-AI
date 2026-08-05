// Package tools holds the MCP tool definitions codejudge-mcp exposes. Each tool
// is a thin adapter: decode the model's arguments, call the CodeJudge HTTP
// client, and return a typed result the ADK agent can reason over.
package tools

import (
	"context"
	"fmt"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"codejudge-mcp/internal/codejudge"
)

// GetProblemSpecInput is the argument schema for get_problem_spec.
type GetProblemSpecInput struct {
	ProblemID string `json:"problemId" jsonschema:"the id of the problem to look up, e.g. \"two-sum\""`
}

// GetProblemSpecOutput is the structured result: a problem's public spec.
type GetProblemSpecOutput struct {
	ID          string                 `json:"id"`
	Mode        string                 `json:"mode"`
	Signature   string                 `json:"signature,omitempty"`
	EntryFunc   string                 `json:"entryFunc,omitempty"`
	Limits      codejudge.Limits       `json:"limits"`
	SampleCases []codejudge.SampleCase `json:"sampleCases"`
}

// GetProblemSpec builds the get_problem_spec tool handler bound to client. It
// looks up a single problem's public spec (metadata + sample cases) so the
// agent can answer questions about a live problem instead of guessing.
func GetProblemSpec(client *codejudge.Client) mcp.ToolHandlerFor[GetProblemSpecInput, GetProblemSpecOutput] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in GetProblemSpecInput) (*mcp.CallToolResult, GetProblemSpecOutput, error) {
		if in.ProblemID == "" {
			return nil, GetProblemSpecOutput{}, fmt.Errorf("problemId is required")
		}

		p, err := client.GetProblem(ctx, in.ProblemID)
		if err != nil {
			// Surface the error to the model as tool content rather than a
			// transport failure, so it can react (e.g. try a different id).
			return &mcp.CallToolResult{
				IsError: true,
				Content: []mcp.Content{&mcp.TextContent{Text: err.Error()}},
			}, GetProblemSpecOutput{}, nil
		}

		out := GetProblemSpecOutput{
			ID:          p.ID,
			Mode:        p.Mode,
			Signature:   p.Signature,
			EntryFunc:   p.EntryFunc,
			Limits:      p.Limits,
			SampleCases: p.SampleCases,
		}
		return nil, out, nil
	}
}
