import os
import logging
from dotenv import load_dotenv
from config import DB_POOL_MAX, DB_POOL_MIN

load_dotenv()
logger = logging.getLogger(__name__)

# 전역 커넥션 풀 변수
_db_pool = None

def _get_pool():
    """커넥션 풀을 초기화하거나 반환합니다."""
    import psycopg2
    from psycopg2.pool import SimpleConnectionPool
    from psycopg2.extras import RealDictCursor
    
    global _db_pool
    if _db_pool is None:
        database_url = os.getenv("DATABASE_URL", "").strip()
        logger.info(
            "데이터베이스 커넥션 풀 초기화 (min=%s, max=%s, source=%s)",
            DB_POOL_MIN,
            DB_POOL_MAX,
            "DATABASE_URL" if database_url else "DB_*",
        )

        if database_url:
            _db_pool = SimpleConnectionPool(
                DB_POOL_MIN,
                DB_POOL_MAX,
                database_url,
                cursor_factory=RealDictCursor,
            )
            return _db_pool

        connection_options = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": os.getenv("DB_PORT", "5432"),
            "dbname": os.getenv("DB_NAME", "capstone_db"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD"),
            "cursor_factory": RealDictCursor,
        }
        sslmode = os.getenv("DB_SSLMODE", "").strip()
        if sslmode:
            connection_options["sslmode"] = sslmode

        _db_pool = SimpleConnectionPool(
            DB_POOL_MIN,
            DB_POOL_MAX,
            **connection_options,
        )
    return _db_pool


class PoolConnectionWrapper:
    """
    기존 코드 변경을 최소화하기 위한 래퍼 클래스입니다.
    기존 코드가 conn.close()를 호출할 때, 연결을 끊는 대신 풀(Pool)로 반납합니다.
    """
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        """실제 연결을 종료하지 않고 풀로 반환합니다."""
        if self._conn is not None:
            self._pool.putconn(self._conn)
            self._conn = None


def get_connection():
    """
    커넥션 풀에서 데이터베이스 연결을 하나 가져옵니다.
    반환된 연결 객체는 사용 후 반드시 close()를 호출해야 풀로 반환됩니다.
    """
    pool = _get_pool()
    conn = pool.getconn()
    return PoolConnectionWrapper(conn, pool)

def check_database_health() -> dict:
    """
    /api/v1/health 에서 사용할 DB 연결 점검 함수입니다.

    주의:
    - 비밀번호, 상세 접속 문자열은 절대 반환하지 않습니다.
    - 오류가 나도 서버 전체가 죽지 않도록 error_type만 반환합니다.
    - 현재 백엔드는 트랙 기준 데이터를 DB에서 읽기 때문에, health에서 DB 상태를 함께 보여줍니다.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # 가장 가벼운 연결 확인 쿼리
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()

            # 발표/시연 때 기준 데이터가 실제로 들어왔는지 빠르게 확인하기 위한 카운트
            # 테이블이 없거나 아직 마이그레이션 전이면 except로 내려가 degraded 상태가 됩니다.
            cur.execute("SELECT COUNT(*) AS count FROM departments")
            department_count = int(cur.fetchone()["count"])

            cur.execute("SELECT COUNT(*) AS count FROM tracks")
            track_count = int(cur.fetchone()["count"])

            cur.execute("SELECT COUNT(*) AS count FROM modules")
            module_count = int(cur.fetchone()["count"])

            cur.execute("SELECT COUNT(*) AS count FROM source_documents")
            source_document_count = int(cur.fetchone()["count"])

            if department_count == 0 or track_count == 0 or module_count == 0:
                return {
                    "status": "missing_data",
                    "data_source": "postgresql",
                    "department_count": department_count,
                    "track_count": track_count,
                    "module_count": module_count,
                    "source_document_count": source_document_count,
                    "error_type": "MissingReferenceData",
                }

        return {
            "status": "connected",
            "data_source": "postgresql",
            "department_count": department_count,
            "track_count": track_count,
            "module_count": module_count,
            "source_document_count": source_document_count,
        }
    except Exception as exc:
        logger.warning("DB 상태 확인 실패: %s", type(exc).__name__)
        return {
            "status": "error",
            "data_source": "postgresql",
            "error_type": type(exc).__name__,
        }
    finally:
        if conn is not None:
            conn.close()
