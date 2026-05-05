# AutoBuy — JD VOP connector

Сервис-посредник: забирает заказы из **JD VOP** (vop.jd.com), сохраняет их у себя в БД, отдаёт через REST. Интеграция со СДЭК на этой итерации не реализуется — будет добавлена отдельным шагом.

Стек: Python 3.12, FastAPI, httpx, Pydantic v2, SQLAlchemy 2.0, SQLite (dev) / PostgreSQL (prod), APScheduler.

---

## Быстрый старт (локально, без реальных JD-кредов)

```bash
# 1. Зависимости через uv (рекомендуется) либо pip
pip install uv
uv venv -p 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# 2. Конфиг
cp .env.example .env
# По умолчанию JD_MODE=mock — реальные ключи не нужны.

# 3. Запуск
uvicorn src.main:app --reload

# 4. Пробный pull (через мок)
curl -X POST http://localhost:8000/sync/run -H "x-api-key: change-me"
curl http://localhost:8000/orders -H "x-api-key: change-me"
curl http://localhost:8000/orders/100000000001 -H "x-api-key: change-me"
```

Swagger UI: http://localhost:8000/docs

## Тесты

```bash
pytest -q
```

В тестах (`tests/test_sync_e2e.py`) проверяется полный путь pull → БД на фикстурах JD, идемпотентность повторного запуска, и API-эндпоинты.

---

## Эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| GET  | `/health` | liveness |
| POST | `/sync/run?since=...&until=...` | запуск синхронизации (требует `x-api-key`) |
| GET  | `/sync/logs` | последние запуски |
| GET  | `/orders` | список заказов |
| GET  | `/orders/{jd_order_id}` | детали заказа + сырой payload JD |
| ANY  | `/jd/callback` | whitelisted callback для регистрации в JD VOP |

Все админские эндпоинты защищены заголовком `x-api-key: <SERVICE_API_KEY>`.

---

## Переменные окружения

Полный список — в `.env.example`. Ключевые:

| Переменная | Что |
|---|---|
| `JD_MODE` | `mock` (фикстуры) или `live` (реальные вызовы JD) |
| `JD_BASE_URL` | по умолчанию `https://bizapi.jd.com` |
| `JD_APP_KEY/SECRET/USERNAME/PASSWORD` | креды JD VOP, выдаются при создании приложения |
| `JD_CALLBACK_URL` | публичный HTTPS-URL вашего инстанса, для регистрации в VOP |
| `CNY_RUB_RATE` | статичный курс CNY→RUB. Правится вручную. Применение курса логируется. |
| `DEFAULT_WEIGHT_G/LWH_CM` | дефолты, если JD не отдал габариты |
| `SYNC_INTERVAL_MINUTES` | если задано — встроенный планировщик дёргает sync; пусто = только ручной |
| `SYNC_LOOKBACK_MINUTES` | окно, за которое тянуть заказы при каждом тике (по умолчанию 60) |

---

## Деплой на Reg.ru VPS (рекомендуемый сценарий)

Цель — получить публичный HTTPS-URL вида `https://autobuy.example.com/jd/callback`, который можно зарегистрировать в кабинете JD VOP для выдачи production-ключей.

1. **Заказать VPS** в Reg.ru (минимально: 1 vCPU / 1 GB RAM / Ubuntu 22.04 — около 250–400 ₽/мес).
2. **Привязать домен** в DNS Reg.ru: A-запись `autobuy.example.com → IP вашего VPS`.
3. **Подготовить сервер:**
   ```bash
   ssh root@<ip>
   apt update && apt install -y docker.io docker-compose-plugin git
   git clone <ваш-репо> /opt/autobuy && cd /opt/autobuy
   cp .env.example .env && nano .env   # заполнить креды
   sed -i 's/example.com/autobuy.example.com/' Caddyfile
   docker compose up -d
   ```
4. **Проверить HTTPS:**
   ```bash
   curl https://autobuy.example.com/health
   ```
   Caddy сам выпустит Let's Encrypt-сертификат.
5. **Зарегистрироваться в JD VOP:**
   - Зайти в личный кабинет JD VOP (https://vop.jd.com), создать приложение.
   - Указать `Whitelisted callback URL`: `https://autobuy.example.com/jd/callback`.
   - Получить `app_key`, `app_secret`, корпоративный `username/password`.
   - Прописать их в `/opt/autobuy/.env`, переключить `JD_MODE=live`, перезапустить:
     ```bash
     docker compose restart app
     ```

### Альтернативные хостинги

- **Hetzner CX11** (~€4/мес, лучшее соотношение цена/перформанс, но карта может быть проблемой из РФ).
- **Timeweb Cloud** (российский, оплата картой РФ, аналогичный сетап).
- **Railway / Render** — проще, но дороже и без своего IP.

---

## Получение кредов (чек-листы)

### JD VOP

1. Регистрация юрлица-партнёра в кабинете https://vop.jd.com (китайская сторона должна подтвердить контракт).
2. Создать приложение → получить `app_key` / `app_secret`.
3. Прописать `Whitelisted callback URL` (= ваш `JD_CALLBACK_URL`).
4. Получить `username` / `password` корпоративного пользователя для логина в API.
5. Тестовые ключи и боевые — в одном кабинете; sandbox-контура у VOP нет.

### СДЭК (на будущее, когда дойдёт очередь)

См. `docs/api_research.md` раздел «СДЭК — отложено».

---

## Структура

```
src/
├── main.py            # FastAPI + lifespan + APScheduler
├── config.py          # pydantic-settings
├── db.py / models.py  # SQLAlchemy 2.0
├── jd/
│   ├── methods.py     # REST-пути JD VOP в одном месте
│   ├── schemas.py     # Pydantic-модели ответов
│   ├── auth.py        # token cache в БД
│   ├── client.py      # httpx + tenacity
│   └── mock.py        # фикстуры вместо реальных вызовов
├── currency.py        # CNY → RUB по статичному курсу
├── sync.py            # оркестратор: pull → upsert
└── api/routes.py      # HTTP-эндпоинты
docs/api_research.md   # источник истины по API
tests/                 # юнит + e2e
```

## Что осталось / TBD

См. раздел «Открытые TBD» в `docs/api_research.md`. Главное:

- Точный путь и поля `getAccessToken`.
- Точные поля запроса/ответа `checkNewOrder` (даты, пагинация).
- Структура `selectJdOrder` с китайским адресом и `items`.
- Лимиты QPS и формат пинга от JD на callback.

Эти TBD не блокируют запуск на моках — закроются при первом ручном вызове после получения боевых JD-кредов.
