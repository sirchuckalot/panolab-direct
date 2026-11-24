package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	setupURL            = "http://setup:8766/mcp"
	setupProtocol       = "2025-06-18"
	installConfirmation = "INSTALL_ISE_14_7_IN_PANOLAB_ONLY"
	setupResponseLimit  = 64 << 10
)

var (
	installSHA256       = regexp.MustCompile("^[a-f0-9]{64}$")
	errSetupUnavailable = errors.New("ISE setup service unavailable")
	errSetupResponse    = errors.New("invalid response from ISE setup service")
	errSetupRejected    = errors.New("ISE setup service rejected the request")
)

type setupInstallInput struct {
	SHA256       string
	Confirmation string
}

type setupProxy struct {
	url           string
	authorization string
	client        *http.Client
}

func newSetupProxy(authorization string) *setupProxy {
	return &setupProxy{
		url:           setupURL,
		authorization: authorization,
		client: &http.Client{
			Transport: &http.Transport{},
			Timeout:   15 * time.Minute, // The setup service can hash up to 20 GiB of media.
			CheckRedirect: func(*http.Request, []*http.Request) error {
				return http.ErrUseLastResponse
			},
		},
	}
}

func registerSetupTools(s *mcp.Server, p *setupProxy) {
	for _, tool := range []struct{ name, downstream, description string }{
		{"ise_setup_status", "lab_status", "Read restricted ISE setup service status"},
		{"ise_media_inspect", "ise_media_inspect", "Inspect the private ISE archive checksum and size"},
		{"ise_install_status", "ise_install_status", "Read the ISE installation state"},
	} {
		mcp.AddTool(s, &mcp.Tool{Name: tool.name, Description: tool.description},
			func(ctx context.Context, _ *mcp.CallToolRequest, in Empty) (*mcp.CallToolResult, any, error) {
				return p.call(ctx, tool.downstream, in)
			})
	}
	mcp.AddTool(s, &mcp.Tool{
		Name:        "ise_install_start",
		Description: "Start ISE installation only with explicit owner approval for the inspected SHA256 and vendor terms",
	}, p.install)
}

func (p *setupProxy) install(ctx context.Context, _ *mcp.CallToolRequest, in setupInstallInput) (*mcp.CallToolResult, any, error) {
	if in.Confirmation != installConfirmation {
		return nil, nil, errors.New("explicit owner confirmation INSTALL_ISE_14_7_IN_PANOLAB_ONLY required")
	}
	if !installSHA256.MatchString(in.SHA256) {
		return nil, nil, errors.New("SHA256 must be exactly 64 lowercase hexadecimal digits")
	}
	return p.call(ctx, "ise_install_start", in)
}

func (p *setupProxy) call(ctx context.Context, name string, arguments any) (*mcp.CallToolResult, any, error) {
	// The stateless setup SDK handler creates an initialized session per POST.
	payload, err := json.Marshal(Out{
		"jsonrpc": "2.0", "id": 1, "method": "tools/call",
		"params": Out{"name": name, "arguments": arguments},
	})
	if err != nil {
		return nil, nil, errors.New("could not encode ISE setup request")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.url, bytes.NewReader(payload))
	if err != nil {
		return nil, nil, errSetupUnavailable
	}
	req.Header.Set("Authorization", p.authorization)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	req.Header.Set("MCP-Protocol-Version", setupProtocol)

	resp, err := p.client.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return nil, nil, ctx.Err()
		}
		return nil, nil, errSetupUnavailable
	}
	defer resp.Body.Close()
	// An in-flight cancellation can race with an HTTP response arriving.
	// Prefer the caller's cancellation over status/content-type validation:
	// otherwise a canceled request may be misreported as a malformed reply.
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, nil, errSetupUnavailable
	}
	mediaType, _, err := mime.ParseMediaType(resp.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return nil, nil, errSetupResponse
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, setupResponseLimit+1))
	if ctx.Err() != nil {
		return nil, nil, ctx.Err()
	}
	if err != nil || len(body) > setupResponseLimit {
		return nil, nil, errSetupResponse
	}
	return p.decode(name, body)
}

func (p *setupProxy) decode(name string, body []byte) (*mcp.CallToolResult, any, error) {
	var reply struct {
		Version string `json:"jsonrpc"`
		ID      int    `json:"id"`
		Error   json.RawMessage
		Result  *mcp.CallToolResult
	}
	if json.Unmarshal(body, &reply) != nil || reply.Version != "2.0" || reply.ID != 1 {
		return nil, nil, errSetupResponse
	}
	if len(reply.Error) != 0 || (reply.Result != nil && reply.Result.IsError) {
		return nil, nil, errSetupRejected
	}
	if reply.Result == nil || reply.Result.InputRequests != nil {
		return nil, nil, errSetupResponse
	}

	// Only return the tool data. Discard metadata and regenerate the text
	// representation of structured results after removing installer diagnostics.
	if out := reply.Result.StructuredContent; out != nil {
		if fields, ok := out.(map[string]any); ok && name == "ise_install_status" {
			if fields["error"] != nil && fields["error"] != "" {
				fields["error"] = "ISE setup reported an installation error"
			}
		}
		encoded, err := json.Marshal(out)
		if err != nil || p.containsBearer(string(encoded)) {
			return nil, nil, errSetupResponse
		}
		return nil, out, nil
	}

	var content []mcp.Content
	for _, item := range reply.Result.Content {
		item, ok := item.(*mcp.TextContent)
		if !ok || p.containsBearer(item.Text) {
			return nil, nil, errSetupResponse
		}
		content = append(content, &mcp.TextContent{Text: item.Text})
	}
	if len(content) == 0 {
		return nil, nil, errSetupResponse
	}
	return &mcp.CallToolResult{Content: content}, nil, nil
}

func (p *setupProxy) containsBearer(value string) bool {
	secret := strings.TrimPrefix(p.authorization, "Bearer ")
	return secret != "" && strings.Contains(value, secret)
}
