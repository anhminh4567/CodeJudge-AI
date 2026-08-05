// Package codejudge is a thin HTTP client for CodeJudge's public API. It is the
// only thing in codejudge-mcp that knows CodeJudge's wire shape; the MCP tool
// layer talks to CodeJudge exclusively through this client (D1: they never share
// a module, only HTTP).
package codejudge

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// Client calls CodeJudge's HTTP API.
type Client struct {
	baseURL string
	http    *http.Client
}

// NewClient returns a Client rooted at baseURL (e.g. "http://localhost:8080").
// A trailing slash is trimmed so path joins are predictable.
func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		http:    &http.Client{Timeout: 15 * time.Second},
	}
}

// APIError is a non-2xx response from CodeJudge, carrying its error envelope.
type APIError struct {
	StatusCode int
	Body       ErrorBody
}

func (e *APIError) Error() string {
	if e.Body.Message != "" {
		return fmt.Sprintf("codejudge: %d %s: %s", e.StatusCode, e.Body.Code, e.Body.Message)
	}
	return fmt.Sprintf("codejudge: unexpected status %d", e.StatusCode)
}

// Healthz reports whether CodeJudge is reachable (GET /healthz returns 200).
func (c *Client) Healthz(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/healthz", nil)
	if err != nil {
		return err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("reaching codejudge at %s: %w", c.baseURL, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return &APIError{StatusCode: resp.StatusCode}
	}
	return nil
}

// GetProblem fetches one problem's metadata and sample cases (GET /problems/:id).
func (c *Client) GetProblem(ctx context.Context, id string) (*ProblemDetail, error) {
	var env dataEnvelope[ProblemDetail]
	if err := c.getJSON(ctx, "/problems/"+url.PathEscape(id), &env); err != nil {
		return nil, err
	}
	return &env.Data, nil
}

// getJSON performs a GET and decodes the JSON body into out, mapping a non-2xx
// response to an *APIError (decoding CodeJudge's error envelope when present).
func (c *Client) getJSON(ctx context.Context, path string, out any) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+path, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("GET %s: %w", path, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading %s response: %w", path, err)
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		apiErr := &APIError{StatusCode: resp.StatusCode}
		var env errorEnvelope
		if json.Unmarshal(body, &env) == nil {
			apiErr.Body = env.Error
		}
		return apiErr
	}

	if err := json.Unmarshal(body, out); err != nil {
		return fmt.Errorf("decoding %s response: %w", path, err)
	}
	return nil
}
