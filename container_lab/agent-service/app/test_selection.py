from app.main import select_fixture


assert select_fixture("비중요 팀 노트 보여줘") == "/data/nonimportant/team-note.txt"
assert select_fixture("중요 비밀 문서 보여줘") == "/data/sensitive/secret.txt"
assert select_fixture("공개 공지 보여줘") == "/data/public/notice.txt"
print("agent selection self-check: PASS")
