package mcp
import rego.v1
default allow := false
allow if {
  input.approved == true
  input.subject != ""
  input.tool != ""
}
