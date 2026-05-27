# 트랙길잡이

한림대학교 모듈형 전공트랙 이수 현황을 학생이 직접 확인할 수 있도록 만든 웹 기반 진단 도구입니다.  
사용자가 학과를 선택하고 이수한 과목을 체크하면, 전공트랙별 진행률과 부족 과목을 계산하고 현재 이수 상태와 가까운 전공트랙을 추천합니다.

## 프로젝트 개요

한림대학교의 모듈형 전공트랙은 여러 모듈과 교과목을 조합하여 학생의 진로와 전문성에 맞는 학습 경로를 설계할 수 있는 제도입니다. 다만 학과별 전공트랙 조건, 모듈 구성, 필수 과목, 이수 학점 기준이 서로 달라 학생이 가이드북을 직접 보며 자신의 이수 현황을 판단하기에는 부담이 있습니다.

트랙길잡이는 이러한 과정을 자동화하여 학생이 자신의 현재 위치를 빠르게 확인하고, 앞으로 어떤 과목을 수강하면 원하는 전공트랙에 가까워질 수 있는지 파악할 수 있도록 돕습니다.

## 주요 기능

- 학과별 전공트랙 및 모듈 정보 조회
- 사용자의 이수 과목 선택 및 분석
- 전공트랙별 진행률 계산
- 이수 완료 여부 및 부족 조건 확인
- 부족 과목 및 선택 가능한 보완 과목 안내
- 현재 이수 내역과 가까운 추천 전공트랙 제공
- PC와 모바일을 고려한 반응형 화면 제공

## 서비스 흐름

1. 관심 학과 선택
2. 선택 학과의 전공트랙과 모듈 확인
3. 본인이 이수한 과목 체크
4. 전공트랙별 분석 결과 확인
5. 추천 트랙과 부족 과목을 참고하여 수강 계획 수립

## 기술 스택

### Frontend

- React
- TypeScript
- Vite
- Pretendard

### Backend

- Python
- FastAPI
- Uvicorn
- PostgreSQL
- psycopg2

### Data

- 한림대학교 모듈형 전공트랙 교육과정 가이드북 기반 전공트랙 데이터
- 학과, 트랙, 모듈, 과목, 이수 조건 구조화

## 폴더 구조

```text
project-github-upload/
├─ backend/
│  ├─ data/
│  │  ├─ schema.sql
│  │  └─ track_rules.json
│  ├─ routers/
│  ├─ schemas/
│  ├─ services/
│  ├─ scripts/
│  ├─ main.py
│  ├─ db.py
│  └─ requirements.txt
├─ frontend/
│  ├─ public/
│  ├─ src/
│  ├─ package.json
│  └─ vite.config.ts
├─ DEPLOY.md
└─ Dockerfile
```

## 실행 방법

### 1. 백엔드 환경 설정

`project-github-upload/backend` 경로에 `.env` 파일을 생성하고 PostgreSQL 접속 정보를 설정합니다.

```text
TRACK_DATA_SOURCE=db
DB_HOST=localhost
DB_PORT=5432
DB_NAME=track_db
DB_USER=postgres
DB_PASSWORD=your_password
```

또는 `DATABASE_URL`을 사용할 수 있습니다.

```text
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

### 2. 데이터베이스 준비

PostgreSQL에 스키마를 적용합니다.

```bash
psql -U postgres -d track_db -f backend/data/schema.sql
```

전공트랙 JSON 데이터를 데이터베이스로 옮깁니다.

```bash
cd project-github-upload/backend
python scripts/migrate_json_to_db.py
```

### 3. 백엔드 실행

```bash
cd project-github-upload/backend
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

백엔드가 실행되면 다음 주소에서 API 문서를 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

### 4. 프론트엔드 실행

```bash
cd project-github-upload/frontend
npm install
npm run dev
```

기본 실행 주소는 다음과 같습니다.

```text
http://127.0.0.1:5173
```

## 주요 API

| Method | Endpoint | 설명 |
| --- | --- | --- |
| GET | `/api/v1/health` | 서버 상태 확인 |
| GET | `/api/v1/tracks` | 전체 전공트랙 조회 |
| GET | `/api/v1/tracks/by-department` | 학과별 전공트랙 조회 |
| GET | `/api/v1/modules/by-department` | 학과별 모듈 및 과목 조회 |
| POST | `/api/v1/analyze` | 이수 과목 기반 전공트랙 분석 |

## 기대 효과

- 학생이 전공트랙 조건을 직접 계산해야 하는 부담 감소
- 수강 신청 전 부족 과목과 가까운 트랙 확인 가능
- 교수 상담 및 학과 안내 과정에서 기초 자료로 활용 가능
- 모듈형 전공트랙 제도의 접근성과 활용도 향상

## 향후 개선 방향

- 과목별 개설 학기 정보 제공
- 학사 시스템 연동을 통한 최신 이수 정보 반영
- 분석 결과 리포트 출력 기능
- 개인별 이수 현황 저장 기능
- 관심 분야와 희망 진로를 반영한 맞춤형 추천 기능

## 오픈소스

본 프로젝트는 다음 오픈소스 및 공개 리소스를 활용했습니다.

| 이름 | 용도 | 소스 |
| --- | --- | --- |
| React | 프론트엔드 UI 구현 | https://github.com/facebook/react |
| TypeScript | 정적 타입 기반 프론트엔드 개발 | https://github.com/microsoft/TypeScript |
| Vite | 프론트엔드 개발 및 빌드 도구 | https://github.com/vitejs/vite |
| FastAPI | 백엔드 API 서버 구현 | https://github.com/fastapi/fastapi |
| Uvicorn | ASGI 서버 | https://github.com/encode/uvicorn |
| PostgreSQL | 관계형 데이터베이스 | https://github.com/postgres/postgres |
| psycopg2 | Python PostgreSQL 연결 드라이버 | https://github.com/psycopg/psycopg2 |
| python-dotenv | 환경변수 관리 | https://github.com/theskumar/python-dotenv |
| cachetools | 데이터 로딩 캐시 처리 | https://github.com/tkem/cachetools |
| cryptography | 보안 관련 유틸리티 | https://github.com/pyca/cryptography |
| Pretendard | 웹 폰트 | https://github.com/orioncactus/pretendard |
