# Чеклист соответствия практике

## Уровни рейтинга

- Уровень 1: первичный рейтинг анкеты — реализован в `bot/rating.py`.
- Уровень 2: поведенческий рейтинг — лайки, пропуски, просмотры, мэтчи, переходы по соцсетям.
- Уровень 3: комбинированный рейтинг — весовая формула `0.4 * primary + 0.6 * behavior + referral_bonus`.

## Этапы

| Этап | Требование | Где реализовано |
|---|---|---|
| 1 | Описание сервисов и архитектуры | `README.md`, `ARCHITECTURE.md`, `docs/` |
| 1 | Схема БД | `docs/schema.dbml`, SQLite-схема в `bot/storage.py` |
| 2 | Telegram Bot API | `bot/main.py` |
| 2 | Регистрация по Telegram ID | `/start`, `UserStorage.register_or_update_user` |
| 3 | CRUD анкет | `/start`, `/profile`, `/edit`, `/delete` |
| 3 | Алгоритм ранжирования | `bot/rating.py`, `bot/feed_cache.py` |
| 3 | Redis-кэш ленты | `feed_queue:{profile_id}` в `bot/feed_cache.py` |
| 3 | Интеграция с ботом | `/feed`, callback-кнопки лайков |
| 4 | Отложенные задачи | Celery/fallback в `bot/tasks.py` |
| 4 | Оптимизация БД | индексы в `bot/storage.py` |
| 4 | Тестирование | `test_bot_setup.py`, `py_compile` |
| 4 | Локальный деплой | `docker-compose.yml`, `run_bot.py` |

## Дополнительные баллы

- Отдельная таблица рейтингов: `profile_ratings`.
- Регулярный пересчёт рейтингов: Celery beat или локальный fallback-планировщик.
- Redis-кэш предранжированных списков анкет: `feed_queue:{profile_id}`.
- MQ: Redis-list `mq:interaction_events` как лёгкая очередь событий.
- Метрики: `bot/metrics.py`, команда `/metrics`.
- Логирование: `logs/interactions_YYYYMMDD.log` и `events_log`.
- S3/Minio: `bot/minio_client.py`, включается через `ENABLE_MINIO=true`.
- Нестандартная предметная область: арт-комьюнити, портфолио, соцсети, избранное и топ художников.
