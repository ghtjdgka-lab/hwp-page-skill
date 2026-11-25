---
name: hwp-page
description: 한글(hwp/hwpx) 문서의 쪽 방향(가로/세로)·용지·여백·본문 글자 크기를 바꾸고, «1) 가. - ①» 같은 부호 문단을 내어쓰기하는 hwp-page MCP 서버를 설치하고 쓴다. "한글 가로로 바꿔줘", "여백 줄여줘", "글자 크기 키워줘", "내어쓰기 맞춰줘", "hwp-page 설치해줘" 라고 하면 실행.
---

# hwp-page — 한글 쪽 설정 MCP

이 폴더의 `server.py` 가 MCP 서버다. 도구 2개를 준다.

| 도구 | 하는 일 | 파일 |
|---|---|---|
| `set_page` | 쪽 방향(가로/세로)·용지(A4/B5/A5/LETTER)·여백(mm)·본문 글자 크기(pt) 바꾸기. `file_path` 만 주면 지금 여백·글자 크기를 알려 줌 | .hwpx 만 |
| `indent_bullets` | «1) 가. - ① ※ (1)» 로 시작하는 문단의 둘째 줄을 부호 뒤 글자에 맞춤 (표 칸 안 포함) | .hwp / .hwpx |

둘 다 고치기 전에 `<파일>.bak` 백업을 남기고, 실패하면 원본을 되돌린다.

## 1. 도구가 안 보이면 — 설치

`mcp__hwp-page__set_page` 도구가 없으면 아래를 순서대로 한다. 사용자는 대부분 개발자가 아니니
각 단계를 네가 직접 돌리고, 사용자에게는 결과만 쉽게 말한다.

1. **윈도우 + 한글(한컴오피스) 확인.** `indent_bullets` 는 실제 한글 프로그램을 COM 으로 부른다.
   한글이 없으면 `set_page` 만 쓸 수 있다고 알린다.
2. **진짜 파이썬 찾기 (3.10 이상).** `python --version` 이 Microsoft Store 안내를 띄우면 가짜다.
   `py -3 -c "import sys;print(sys.executable)"` 로 실제 경로를 얻는다. 없으면
   [python.org](https://www.python.org/downloads/windows/) 에서 설치하시라고 안내한다
   (설치 화면 첫 장의 **«Add python.exe to PATH»** 체크).
3. **라이브러리 설치:**
   ```
   "<파이썬 경로>" -m pip install "mcp>=1.10" pywin32
   ```
4. **MCP 등록** (모든 폴더에서 쓰이도록 user 범위). 경로는 이 SKILL.md 가 있는 폴더의 `server.py` 절대경로:
   ```
   claude mcp add hwp-page --scope user -- "<파이썬 경로>" "<이 폴더>\server.py"
   ```
   - 명령 경로는 **절대경로**로 준다. 윈도우는 `.venv/Scripts/python.exe` 처럼 슬래시만 있는 상대경로를
     실행 파일로 못 찾고, 틀려도 오류 없이 `/mcp` 목록에서 조용히 빠진다.
5. **확인:** 등록 직후 stdio 로 실제 도구가 잡히는지 본다.
   ```
   claude mcp get hwp-page
   ```
   `Status: ✓ Connected` 가 나와야 한다.
6. 사용자에게 **«VS Code(또는 클로드 창)를 완전히 껐다 켜 주세요»** 라고 안내한다.
   MCP 목록은 시작할 때 한 번만 읽혀서, 껐다 켜야 도구가 뜬다.

## 2. 쓰는 법

- **가로로:** `set_page(file_path, orientation="landscape")`
  - 방향만 바뀐다. 세로 폭(A4 본문 ≈ 42000 HWPUNIT)에 맞춰 만든 표는 오른쪽이 비니,
    표도 넓혀야 하면 사용자에게 알린다.
- **여백만:** `set_page(file_path, left=20, right=20)` — 안 준 여백은 그대로.
- **글자 크기:** `set_page(file_path, font_size=11)` — 본문 기준, 제목 등 다른 크기도 같은 비율로.
  - 본문 10pt 가 기본. 한두 줄 넘쳐 쪽이 늘면 9~9.5, 빈 곳이 많으면 11~12.
- **지금 상태 보기:** `set_page(file_path)` 만.
- **내어쓰기:** `indent_bullets(file_path)` — 한글에서 그 파일을 열어 두었으면 **먼저 닫으시라고** 한다.
  새 한글 창을 숨겨서 띄우므로 사용자가 열어 둔 다른 문서에는 붙지 않는다.

`.hwp` 를 `set_page` 하려면 한글에서 **다른 이름으로 저장 → HWPX** 로 바꾼 뒤 한다.

## 3. 고친 뒤 확인

- 고친 다음 **PDF 로 내보내 쪽 수·표 넘침을 눈으로 확인**한다. 도구가 «OK» 라고 해도 그대로 믿지 않는다.
- 결과가 이상하면 `<파일>.bak` 을 원래 이름으로 되돌리면 원래대로 돌아간다.

## 4. 한글 문서 규칙 (서버가 MCP instructions 로도 알려 준다)

- 표의 구분 칸(첫 열·머리글)과 짧은 말은 가로·세로 가운데, 긴 문장만 왼쪽. 머리글 줄은 굵게.
- 정렬은 표를 다 채운 뒤 마지막에 (표 만들며 바로 하면 COM 커서가 꼬인다).
- 부호로 시작하는 문단은 `indent_bullets` 로 둘째 줄을 맞춘다.

## 알려진 한계

- `set_page` 는 .hwpx 전용 (zip 안 `Contents/section*.xml`·`header.xml` 을 직접 고친다).
- `indent_bullets` 는 윈도우 + 한글 설치 필요. 문단이 아주 많으면(20만 조각 넘게) 앞부분만 처리한다.
- 한글 COM 접근 보안 팝업이 뜨면 사용자가 **[모두 허용]** 을 눌러야 한다.
