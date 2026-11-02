// The Windows setup program is the same fixed executable for everyone; the console download appends the
// employee's kit after it. It runs the appended PowerShell command unelevated, which asks for UAC itself.
package main

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unsafe"
)

// Only the command marker is a literal here: the loader splits the file on the first payload marker line,
// so that line must not appear inside this program.
const commandMark = "\r\n:MCPGW_COMMAND "

func main() {
	if err := run(); err != nil {
		message("설치 실패 · 콘솔에서 설치 파일을 다시 받아 실행하세요\r\n" + err.Error())
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
	start := bytes.LastIndex(data, []byte(commandMark))
	if start < 0 {
		return errors.New("설치 파일이 손상되었습니다")
	}
	rest := data[start+len(commandMark):]
	end := bytes.Index(rest, []byte("\r\n"))
	if end <= 0 || !bytes.HasPrefix(rest[end+2:], []byte(":MCPGW_")) {
		return errors.New("설치 파일이 손상되었습니다")
	}
	shell := filepath.Join(os.Getenv("SystemRoot"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
	cmd := exec.Command(shell, "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", string(rest[:end]))
	cmd.Env = append(os.Environ(), "MCPGW_SETUP_FILE="+self)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000} // CREATE_NO_WINDOW
	if err := cmd.Run(); err != nil {
		var exit *exec.ExitError
		if errors.As(err, &exit) {
			os.Exit(exit.ExitCode()) // a declined UAC prompt is not an error to show
		}
		return err
	}
	return nil
}

func message(text string) {
	body, _ := syscall.UTF16PtrFromString(text)
	title, _ := syscall.UTF16PtrFromString("MCP")
	syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW").Call(0, uintptr(unsafe.Pointer(body)), uintptr(unsafe.Pointer(title)), 0x10)
}
