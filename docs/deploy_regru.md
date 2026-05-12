# Развёртывание AutoBuy на Reg.ru VPS

Цель: получить публичный HTTPS-URL вида `https://autobuy.example.com/jd/callback`,
который можно зарегистрировать в кабинете JD VOP для выдачи production-ключей.
До получения JD-кредов сервис работает в `JD_MODE=mock` и обслуживает
`/health` + всё API на фикстурах — этого достаточно для проверки HTTPS и
регистрации callback-URL.

Время на всё — **30–60 минут**, если домен уже есть.

---

## 0. Что нужно подготовить заранее

| Чек | Что |
|---|---|
| Домен | Зарегистрированный в Reg.ru или любом регистраторе. Если домена нет — купить можно прямо в Reg.ru, ~250 ₽/год за `.ru` или `.online`. |
| Карта | Российская (для Reg.ru) — Mir / Visa-MC от РФ-банка. |
| SSH-ключ | Публичный ключ (`~/.ssh/id_ed25519.pub` или `id_rsa.pub`). Если нет — `ssh-keygen -t ed25519`. |
| Локальный git | Репозиторий с этим кодом, доступный по SSH или HTTPS (можно push в приватный GitHub и потом clone на сервер). |

---

## 1. Заказать VPS в Reg.ru

1. Открыть https://www.reg.ru/vps/
2. Выбрать тариф. **Минимум** — 1 vCPU / 1 GB RAM / 10 GB SSD. Тариф "Cloud-1" или аналог, ~280–400 ₽/мес.
3. ОС — **Ubuntu 22.04 LTS** или 24.04. Не выбирать ISP-Manager / готовые панели — они мешают Docker.
4. На шаге "доступ" — добавить свой публичный SSH-ключ (поле "SSH-ключи").
5. После оплаты в течение ~5 минут на email придёт IP-адрес VPS и root-пароль (паролем не пользуемся, заходим по ключу).

---

## 2. DNS: привязать домен к VPS

В панели Reg.ru → Управление доменом → DNS:

| Тип | Имя | Значение | TTL |
|---|---|---|---|
| A | `autobuy` (или `@` если корневой) | IP вашего VPS | 600 |

Проверить применение DNS (займёт от 5 минут до часа):

```bash
dig +short autobuy.example.com
# должен вернуть IP вашего VPS
```

Без работающего DNS Caddy не выпустит сертификат, поэтому ждём, пока `dig` отдаст правильный адрес.

---

## 3. Подготовить сервер

```bash
ssh root@<IP-VPS>

# 3.1. Базовая защита и обновления
apt update && apt upgrade -y
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 3.2. Docker + git
apt install -y ca-certificates curl gnupg git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3.3. Проверка
docker version
docker compose version
```

---

## 4. Деплой кода

```bash
# 4.1. Клонировать репозиторий
mkdir -p /opt && cd /opt
git clone https://github.com/nekes357/AutoBuy.git autobuy
cd autobuy
git checkout claude/jd-vop-cdek-connector-c4lMq

# 4.2. Настроить .env
cp .env.example .env
nano .env
```

Что в `.env` поменять обязательно:

```bash
SERVICE_API_KEY=<сгенерируйте: openssl rand -hex 32>
JD_MODE=mock                    # пока ключей JD нет — оставляем mock
JD_CALLBACK_URL=https://autobuy.example.com/jd/callback
CNY_RUB_RATE=12.50              # текущий курс CNY→RUB, правится вручную
```

`DATABASE_URL` в `.env` менять **не нужно** — `docker-compose.yml` сам подставит `postgresql+psycopg://autobuy:autobuy@db:5432/autobuy`.

```bash
# 4.3. Подставить домен в Caddyfile
sed -i 's/autobuy.example.com/<ваш-домен>/' Caddyfile

# 4.4. Запустить
docker compose up -d --build
docker compose ps
docker compose logs -f app    # Ctrl+C когда увидите "Application startup complete"
```

---

## 5. Проверка

```bash
# 5.1. Локально на VPS
curl -fsS http://localhost:8000/health
# {"status":"ok"}

# 5.2. Снаружи через Caddy (HTTPS)
curl -fsS https://autobuy.example.com/health
# {"status":"ok"}

# 5.3. Mock-pull работает
curl -X POST https://autobuy.example.com/sync/run \
    -H "x-api-key: <SERVICE_API_KEY из .env>"
# {"id":1,"correlation_id":"...","fetched":2,"new":2,"errors":0,...}

curl https://autobuy.example.com/orders \
    -H "x-api-key: <SERVICE_API_KEY>"
# [{"jd_order_id":"100000000001",...}]
```

Если `/health` снаружи не отвечает, но локально на VPS отвечает — почти всегда проблема в DNS или firewall:

```bash
docker compose logs caddy   # видны попытки выпуска сертификата
ufw status                  # должны быть открыты 80 и 443
```

---

## 6. Регистрация в JD VOP

Когда зайдёте в кабинет vop.jd.com (после решения вопроса с SMS):

1. Создать приложение.
2. В поле «Whitelisted callback URL» / «Redirect URI» / «Callback URL» вписать:
   `https://autobuy.example.com/jd/callback`
3. JD выдаст: `app_key`, `app_secret`, корпоративный `username`/`password`.
4. На VPS:
   ```bash
   cd /opt/autobuy
   nano .env
   # выставить: JD_MODE=live, JD_APP_KEY, JD_APP_SECRET, JD_USERNAME, JD_PASSWORD
   docker compose restart app
   docker compose logs -f app
   ```
5. Первый ручной pull:
   ```bash
   curl -X POST "https://autobuy.example.com/sync/run?since=2026-05-01T00:00:00Z&until=2026-05-05T00:00:00Z" \
       -H "x-api-key: <SERVICE_API_KEY>"
   ```
   Если поля JD-ответа разойдутся с нашими ожиданиями (5 TBD из `docs/api_research.md`) — ошибки будут видны в `docker compose logs app` и правятся точечно.

---

## 7. Обслуживание

| Задача | Команда |
|---|---|
| Обновить курс CNY→RUB | `nano .env` → правка `CNY_RUB_RATE` → `docker compose up -d --force-recreate app` |
| Посмотреть последние sync'и | `curl https://.../sync/logs -H "x-api-key: ..."` |
| Бэкап БД | `docker compose exec db pg_dump -U autobuy autobuy > backup-$(date +%F).sql` |
| Обновить код | `git pull && docker compose up -d --build` (миграции БД применятся автоматически в entrypoint'е) |
| Включить периодический pull | в `.env` выставить `SYNC_INTERVAL_MINUTES=15` → `docker compose up -d --force-recreate app` |
| Просмотреть применённые миграции | `docker compose exec app alembic current` |
| Откатить последнюю миграцию (опасно!) | `docker compose exec app alembic downgrade -1` |

### Миграции БД

Схема управляется Alembic. На старте контейнера `app` выполняется `python -m src.cli_migrate`, который:

1. Если в БД уже есть таблицы приложения (`jd_orders`), но нет служебной `alembic_version` (как было у первых деплоев, делавшихся через `init_db()`) — выполняет `alembic stamp head`, чтобы пометить текущее состояние как актуальное без попытки повторно создавать таблицы.
2. Затем всегда выполняет `alembic upgrade head` — поднимает БД до последней миграции (no-op, если уже на head).

При выпуске новой миграции (изменение моделей):

```bash
# Локально
. .venv/bin/activate
alembic revision --autogenerate -m "describe change"
# отредактировать сгенерированный файл при необходимости, закоммитить
git push
```

На сервере:
```bash
cd /opt/autobuy
git pull
docker compose up -d --build app
# entrypoint сам выполнит alembic upgrade head перед стартом uvicorn
```

---

## 8. Если что-то идёт не так

| Симптом | Куда смотреть |
|---|---|
| `curl https://...` тайм-аутится | DNS ещё не обновился (`dig +short ...`); UFW блокирует 80/443; Caddy не вышел в interneт |
| Caddy в логах `tls handshake error` | Проверить, что DNS реально указывает на этот VPS — Let's Encrypt валидирует через HTTP-01 |
| `app` падает на старте | `docker compose logs app` — обычно либо неверный `DATABASE_URL`, либо БД ещё не готова |
| `/sync/run` возвращает 500 в live-режиме | Реальный ответ JD не сматчился со схемой → смотреть `docker compose logs app` и править `src/jd/schemas.py` / `src/sync.py::_summarize` |
