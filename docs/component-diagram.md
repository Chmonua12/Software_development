## Диаграмма компонентов (Component Diagram)

Высокоуровневое представление сервисов, инфраструктуры и связей между ними.

```mermaid
flowchart TB
    subgraph external["Внешние системы"]
        TG[Telegram API]
    end

    subgraph services["Сервисы приложения"]
        BOT[Bot Service (aiogram)]
        AUTH[Auth / User Service]
        PROFILE[Profile Service]
        INTERACTION[Interaction Service]
        MATCHES[Matches / Chat Service]
        RANK[Rating Service]
        FEED[Feed / Recommendation Service]
        MEDIA[Media Service]
        NOTIFY[Notification Service]
        CELERY[Celery Workers]
    end

    subgraph infrastructure["Инфраструктура"]
        PG[(PostgreSQL)]
        REDIS[(Redis)]
        KAFKA[Kafka]
        MINIO[(MinIO)]
        PROM[Prometheus]
        LOKI[Loki]
    end

    TG <--> BOT

    BOT -->|"HTTP REST"| AUTH
    BOT -->|"HTTP REST"| PROFILE
    BOT -->|"HTTP REST"| INTERACTION
    BOT -->|"HTTP REST"| FEED

    AUTH --> PG
    PROFILE --> PG
    INTERACTION --> PG
    MATCHES --> PG
    RANK --> PG
    CELERY --> PG

    PROFILE --> MINIO
    MEDIA --> MINIO

    RANK --> REDIS
    FEED --> REDIS
    MATCHES --> REDIS

    AUTH -->|"publish events"| KAFKA
    INTERACTION -->|"publish events"| KAFKA
    MATCHES -->|"publish events"| KAFKA

    KAFKA -->|"consume events"| RANK
    KAFKA -->|"consume events"| NOTIFY
    KAFKA -->|"consume events"| CELERY
    KAFKA -->|"consume events"| MATCHES

    RANK --> CELERY

    BOT -->|"metrics"| PROM
    AUTH -->|"metrics"| PROM
    PROFILE -->|"metrics"| PROM
    INTERACTION -->|"metrics"| PROM
    RANK -->|"metrics"| PROM
    FEED -->|"metrics"| PROM
    CELERY -->|"metrics"| PROM

    PROM --> GRAF[Grafana]
    LOKI --> GRAF
```

## Легенда

| Тип связи | Описание |
|----------|----------|
| HTTP REST | Синхронные запросы (регистрация, анкеты, лайки, лента, мэтчи) |
| MQ events | Асинхронные события (`profile.liked`, `profile.favorited`, `profile.skipped`, `social.link.clicked`, `match.created`, `referral.registered`) |
| metrics | Экспорт метрик для Prometheus |

## Описание сервисов

| Сервис | Ответственность |
|--------|----------------|
| Bot Service | Приём команд от пользователей Telegram, отправка уведомлений |
| Auth / User Service | Регистрация, аутентификация, реферальная система |
| Profile Service | Хранение анкет, соцсетей, полнота профиля |
| Interaction Service | Лайки (для общения и в избранное), пропуски, переходы по ссылкам |
| Matches / Chat Service | Отслеживание взаимных лайков, создание мэтчей, внутренняя переписка |
| Rating Service | Трёхуровневая система рейтинга, пересчёты |
| Feed Service | Формирование ленты, кэширование топа |
| Media Service | Загрузка фото в Minio (S3) |
| Notification Service | Уведомления о лайках, мэтчах, попадании в топ |
| Celery Workers | Фоновые задачи, пересчёт рейтингов |
