CREATE DATABASE IF NOT EXISTS registration_db;
USE registration_db;

DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS participants;

CREATE TABLE participants (
  participant_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL
);

CREATE TABLE bookings (
  booking_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  event_id BIGINT NOT NULL,
  participant_id BIGINT NOT NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'confirmed',
  FOREIGN KEY (participant_id) REFERENCES participants (participant_id)
);

INSERT INTO participants (name) VALUES ('Alex'), ('Bao'), ('Casey'), ('Dana'), ('Eli');
INSERT INTO bookings (event_id, participant_id) VALUES (1, 1), (1, 2), (1, 3);
