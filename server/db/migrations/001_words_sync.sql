-- 001_words_sync.sql
-- 橦云学习练习记录同步入库表结构

CREATE TABLE IF NOT EXISTS words_attempts (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  client_event_id  CHAR(36)     NOT NULL,
  user_id          VARCHAR(32)  NOT NULL DEFAULT 'boss',
  word             VARCHAR(128) NOT NULL,
  point_id         VARCHAR(64)  NULL,
  level            VARCHAR(8)   NULL,
  mode             VARCHAR(16)  NOT NULL DEFAULT 'recall',
  correct          TINYINT(1)   NOT NULL,
  duration_ms      INT UNSIGNED NOT NULL,
  answer_text      VARCHAR(512) NULL,
  answered_at      DATETIME(3)  NOT NULL,
  interval_days    TINYINT UNSIGNED NOT NULL,
  next_review_on   DATE         NOT NULL,
  wordlist_ver     VARCHAR(16)  NULL,
  client_ua        VARCHAR(64)  NULL,
  received_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_client_event (client_event_id),
  KEY ix_user_time (user_id, answered_at),
  KEY ix_user_word (user_id, word),
  CONSTRAINT ck_interval CHECK (interval_days IN (1,3,7,14,30))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

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
