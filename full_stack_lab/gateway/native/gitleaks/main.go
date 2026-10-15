// Gitleaks as an in-process C-ABI library for the Gateway.
//
// The Gateway used to start the gitleaks binary for every inspection: a process
// spawn, a temp directory and a full rule compile per call. This library loads the
// same upstream rule catalog once and scans in the calling process. Each scan gets a
// fresh detector because DetectSource accumulates findings on the detector; the
// compiled rules are shared, which upstream does across its own goroutines.
//
// The detector is configured exactly like `gitleaks stdin --redact=100
// --ignore-gitleaks-allow` with no config file: default catalog, decode depth 5,
// no archive traversal, Go's stdlib regexp (the official binary is built the same
// way). tests/secret_engine_parity_check.py compares the two on every rule.
package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
	"unsafe"

	"github.com/rs/zerolog"
	"github.com/spf13/viper"
	"github.com/zricethezav/gitleaks/v8/config"
	"github.com/zricethezav/gitleaks/v8/detect"
	"github.com/zricethezav/gitleaks/v8/logging"
	"github.com/zricethezav/gitleaks/v8/sources"
)

const scanTimeout = 5 * time.Second

var (
	setup     sync.Once
	catalog   config.Config
	setupFail error
)

func load() {
	// Findings and fragments reach the logger at debug level, secrets included.
	logging.Logger = zerolog.Nop()
	viper.SetConfigType("toml")
	if err := viper.ReadConfig(strings.NewReader(config.DefaultConfig)); err != nil {
		setupFail = err
		return
	}
	var vc config.ViperConfig
	if err := viper.Unmarshal(&vc); err != nil {
		setupFail = err
		return
	}
	catalog, setupFail = vc.Translate()
}

type outcome struct {
	Rules []string `json:"rules"`
	Error string   `json:"error,omitempty"`
}

func scan(data []byte) (result outcome) {
	defer func() {
		if r := recover(); r != nil {
			result = outcome{Error: fmt.Sprint("panic: ", r)}
		}
	}()
	setup.Do(load)
	if setupFail != nil {
		return outcome{Error: setupFail.Error()}
	}
	ctx, cancel := context.WithTimeout(context.Background(), scanTimeout)
	defer cancel()
	detector := detect.NewDetectorContext(ctx, catalog)
	detector.MaxDecodeDepth = 5
	detector.MaxArchiveDepth = 0
	detector.Redact = 100
	detector.IgnoreGitleaksAllow = true
	findings, err := detector.DetectSource(ctx, &sources.File{Content: bytes.NewReader(data), MaxArchiveDepth: 0})
	if err != nil {
		return outcome{Error: err.Error()}
	}
	if ctx.Err() != nil {
		return outcome{Error: ctx.Err().Error()}
	}
	seen := map[string]bool{}
	for _, finding := range findings {
		seen[finding.RuleID] = true
	}
	rules := make([]string, 0, len(seen))
	for id := range seen {
		rules = append(rules, id)
	}
	sort.Strings(rules)
	return outcome{Rules: rules}
}

// mcpgw_gitleaks_scan returns a malloc'd JSON document {"rules": [...]} or
// {"error": "..."}; the caller releases it with mcpgw_gitleaks_free.
//
//export mcpgw_gitleaks_scan
func mcpgw_gitleaks_scan(data *C.char, size C.longlong) *C.char {
	if size < 0 || (size > 0 && data == nil) {
		return C.CString(`{"rules":[],"error":"invalid input"}`)
	}
	body, err := json.Marshal(scan(C.GoBytes(unsafe.Pointer(data), C.int(size))))
	if err != nil {
		return C.CString(`{"rules":[],"error":"encode"}`)
	}
	return C.CString(string(body))
}

//export mcpgw_gitleaks_free
func mcpgw_gitleaks_free(pointer *C.char) {
	C.free(unsafe.Pointer(pointer))
}

func main() {}
