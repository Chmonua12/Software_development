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
    RANK --> PG
    CELERY --> PG

    PROFILE --> MINIO
    MEDIA --> MINIO

    RANK --> REDIS
    FEED --> REDIS

    AUTH -->|"publish events"| KAFKA
    INTERACTION -->|"publish events"| KAFKA

    KAFKA -->|"consume events"| RANK
    KAFKA -->|"consume events"| NOTIFY
    KAFKA -->|"consume events"| CELERY

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
| HTTP REST | Синхронные запросы (регистрация, анкеты, лайки, лента) |
| MQ events | Асинхронные события (`profile.liked`, `profile.skipped`, `social.link.clicked`, `referral.registered`) |
| metrics | Экспорт метрик для Prometheus |

## Описание сервисов

| Сервис | Ответственность |
|--------|----------------|
| Bot Service | Приём команд от пользователей Telegram, отправка уведомлений |
| Auth / User Service | Регистрация, аутентификация, реферальная система |
| Profile Service | Хранение анкет, соцсетей, полнота профиля |
| Interaction Service | Лайки, пропуски, переходы по ссылкам |
| Rating Service | Трёхуровневая система рейтинга, пересчёты |
| Feed Service | Формирование ленты, кэширование топа |
| Media Service | Загрузка фото в Minio (S3) |
| Notification Service | Уведомления о лайках, попадании в топ |
| Celery Workers | Фоновые задачи, пересчёт рейтингов |
