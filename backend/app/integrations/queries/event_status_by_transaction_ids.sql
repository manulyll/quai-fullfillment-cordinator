SELECT
  transaction AS so_id,
  MAX(status) AS event_status
FROM calendarEvent
WHERE transaction IN (%s)
GROUP BY transaction
