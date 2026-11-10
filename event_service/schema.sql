CREATE DATABASE IF NOT EXISTS event_db;
USE event_db;

DROP TABLE IF EXISTS events;
CREATE TABLE events (
  event_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(150) NOT NULL,
  capacity INT NOT NULL,
  seats_taken INT NOT NULL DEFAULT 0
);

INSERT INTO events (event_id, name, capacity, seats_taken) VALUES
  (1, 'Git workshop', 12, 3),
  (2, 'API design lab', 4, 0),
  (3, 'Testing clinic', 1, 0);
