-- Down for 001_words_sync.sql. Run only this file to roll back.
-- Order: drop words_card_state first, then words_attempts.
-- Up creates words_attempts, then words_card_state. There is no foreign key today;
-- this order stays correct if card state later references attempts.
DROP TABLE IF EXISTS words_card_state;
DROP TABLE IF EXISTS words_attempts;
