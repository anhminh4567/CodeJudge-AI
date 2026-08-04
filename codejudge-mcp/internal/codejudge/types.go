package codejudge

// Wire types mirror CodeJudge's HTTP response shapes (api/dto in the CodeJudge
// repo). We keep our own copy rather than importing them, because codejudge-mcp
// is a separate deployable that must not share a module with CodeJudge (D1) and
// only ever talks to it over HTTP.
//
// Envelopes (from CodeJudge api/dto/envelope.go):
//
//	object : { "data": <object> }
//	error  : { "error": { "code", "message" } }

// dataEnvelope wraps a single-object success response.
type dataEnvelope[T any] struct {
	Data T `json:"data"`
}

// errorEnvelope wraps an error response.
type errorEnvelope struct {
	Error ErrorBody `json:"error"`
}

// ErrorBody is CodeJudge's error payload.
type ErrorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// Limits mirrors dto.Limits: the resource caps applied when grading.
type Limits struct {
	WallTimeMs int64   `json:"wallTimeMs"`
	MemoryMB   int64   `json:"memoryMb"`
	CPUs       float64 `json:"cpus"`
	PidsMax    int     `json:"pidsMax"`
}

// SampleCase mirrors dto.SampleCase: a visible (non-hidden) test case.
type SampleCase struct {
	CaseID         string `json:"caseId"`
	Stdin          string `json:"stdin"`
	ExpectedStdout string `json:"expectedStdout"`
}

// ProblemDetail mirrors dto.ProblemDetail: metadata plus sample cases. Hidden
// cases are never exposed by CodeJudge, so they never appear here.
type ProblemDetail struct {
	ID          string       `json:"id"`
	Mode        string       `json:"mode"`      // "stdio" | "function"
	Signature   string       `json:"signature"` // function mode only
	EntryFunc   string       `json:"entryFunc"` // function mode only
	Limits      Limits       `json:"limits"`
	SampleCases []SampleCase `json:"sampleCases"`
}
