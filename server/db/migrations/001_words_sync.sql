-- 001_words_sync.sql
-- 橦云学习练习记录同步入库 DDL
-- 目标库：82 MySQL tongyun_learn

CREATE TABLE IF NOT EXISTS words_attempts (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  client_event_id  CHAR(36)     NOT NULL,             -- 前端 crypto.randomUUID()，幂等键
  user_id          VARCHAR(32)  NOT NULL DEFAULT 'boss',
  word             VARCHAR(128) NOT NULL,
  point_id         VARCHAR(64)  NULL,                 -- 如 en.x-community
  level            VARCHAR(8)   NULL,                 -- L1..L6
  mode             VARCHAR(16)  NOT NULL DEFAULT 'recall', -- recall=拼词 / sentence=敲例句
  correct          TINYINT(1)   NOT NULL,
  duration_ms      INT UNSIGNED NOT NULL,
  answer_text      VARCHAR(512) NULL,                 -- 错时记录写了什么，便于易错分析
  answered_at      DATETIME(3)  NOT NULL,             -- 客户端作答时间（UTC 存）
  interval_days    TINYINT UNSIGNED NOT NULL,         -- 作答后档位 1/3/7/14/30
  next_review_on   DATE         NOT NULL,             -- 按 Asia/Shanghai 计算的日期
  wordlist_ver     VARCHAR(16)  NULL,                 -- v0.2
  client_ua        VARCHAR(64)  NULL,
  received_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_client_event (client_event_id),
  KEY ix_user_time (user_id, answered_at),
  KEY ix_user_word (user_id, word),
  CONSTRAINT ck_interval CHECK (interval_days IN (1,3,7,14,30))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 每词当前复习状态（由 attempts 推导，服务端写入时 upsert；可随时由 attempts 重建）
CREATE TABLE IF NOT EXISTS words_card_state (
  user_id          VARCHAR(32)  NOT NULL,
  word             VARCHAR(128) NOT NULL,
  point_id         VARCHAR(64)  NULL,
  interval_days    TINYINT UNSIGNED NOT NULL,
  next_review_on   DATE         NOT NULL,
  reps             INT UNSIGNED NOT NULL DEFAULT 0,
  lapses           INT UNSIGNED NOT NULL DEFAULT 0,
  last_answered_at DATETIME(3)  NOT NULL,
  PRIMARY KEY (user_id, word),
  KEY ix_due (user_id, next_review_on)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 账号授权参考（按需由 DBA 执行）：
-- CREATE USER IF NOT EXISTS 'tongyun_words'@'127.0.0.1' IDENTIFIED BY '<WORDS_DB_PASS>';
-- GRANT SELECT, INSERT, UPDATE ON tongyun_learn.words_attempts TO 'tongyun_words'@'127.0.0.1';
-- GRANT SELECT, INSERT, UPDATE ON tongyun_learn.words_card_state TO 'tongyun_words'@'127.0.0.1';
-- CREATE USER IF NOT EXISTS 'tongyun_learn_ro'@'127.0.0.1' IDENTIFIED BY '<RO_PASS>';
-- GRANT SELECT ON tongyun_learn.words_attempts TO 'tongyun_learn_ro'@'127.0.0.1';
-- GRANT SELECT ON tongyun_learn.words_card_state TO 'tongyun_learn_ro'@'127.0.0.1';
