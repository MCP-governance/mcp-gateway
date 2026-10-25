#!/usr/bin/env bash
# 서버 한 대에 MINT를 설치한다: ./install.sh --bind <사내 IPv4> [--name <DNS 이름>]
exec "$(dirname "${BASH_SOURCE[0]}")/mint.sh" install "$@"
