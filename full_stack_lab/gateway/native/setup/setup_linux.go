// The Linux setup program is the same fixed executable for everyone; the console download appends the
// employee's kit ZIP after it. It unpacks the kit where the removal command expects it and runs install.sh.
package main

import (
	"archive/zip"
	"bytes"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

const archiveMark = "\n:MCPGW_ARCHIVE\n"

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "설치 실패 · 콘솔에서 설치 파일을 다시 받아 실행하세요:", err)
		os.Exit(1)
	}
}

func run() error {
	self, err := os.Executable()
	if err != nil {
		return err
	}
	data, err := os.ReadFile(self)
	if err != nil {
		return err
	}
	start := bytes.LastIndex(data, []byte(archiveMark))
	if start < 0 {
		return errors.New("설치 파일이 손상되었습니다")
	}
	raw, err := base64.StdEncoding.DecodeString(string(bytes.TrimSpace(data[start+len(archiveMark):])))
	if err != nil {
		return errors.New("설치 파일이 손상되었습니다")
	}
	archive, err := zip.NewReader(bytes.NewReader(raw), int64(len(raw)))
	if err != nil {
		return errors.New("설치 파일이 손상되었습니다")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	dest := filepath.Join(home, "mcp-managed-kit")
	if err := os.RemoveAll(dest); err != nil {
		return err
	}
	if err := os.Mkdir(dest, 0o700); err != nil {
		return err
	}
	for _, file := range archive.File {
		if err := extract(file, dest); err != nil {
			return err
		}
	}
	install := filepath.Join(dest, "install.sh")
	if err := os.Chmod(install, 0o755); err != nil {
		return err
	}
	return syscall.Exec(install, append([]string{install}, os.Args[1:]...), os.Environ())
}

func extract(file *zip.File, dest string) error {
	// The kit is a flat list of files; anything else is not a kit this gateway made.
	if !filepath.IsLocal(file.Name) || strings.ContainsAny(file.Name, `/\`) {
		return fmt.Errorf("잘못된 설치 파일 목록: %q", file.Name)
	}
	mode := os.FileMode(0o644)
	if file.Mode()&0o111 != 0 {
		mode = 0o755
	}
	in, err := file.Open()
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(filepath.Join(dest, file.Name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}
