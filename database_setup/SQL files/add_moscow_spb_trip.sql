
-- Добавляем рейс Москва - Санкт-Петербург на 15 мая
INSERT INTO trips (route_id, train_num, departure_time) VALUES
(267, '002А «Сапсан»','2026-05-15 08:00:00');

-- Получаем ID только что созданного рейса
DO $$
DECLARE
    new_trip_id INT;
BEGIN
    SELECT MAX(id) INTO new_trip_id FROM trips;

    INSERT INTO train_comp (trip_id, wagon_num, class_id) VALUES
    (new_trip_id, 1, 1), 
    (new_trip_id, 2, 2),
    (new_trip_id, 3, 3), 
    (new_trip_id, 4, 4), 
    (new_trip_id, 5, 5); 
END $$;
