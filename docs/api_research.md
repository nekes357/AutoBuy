# API Research

Это «источник истины» по обоим API для проекта. Поля и пути, помеченные **TBD**, нужно будет уточнить из личного кабинета JD VOP / СДЭК после регистрации приложений.

Дата ресёрча: 2026-05-05.

---

## 1. JD VOP (vop.jd.com)

### Что это

JD VOP (Vendor Open Platform) — закрытая B2B-платформа JD.com для корпоративных закупок. Партнёр через REST-API забирает товары/цены/остатки и заказы из JD во внутреннюю систему клиента.

Портал: https://vop.jd.com/
Документация (требует JS, недоступна для curl/web_fetch): https://vop.jd.com/doc/api

### Базовый URL

- Production: `https://bizapi.jd.com`
  - Подтверждено по исходникам PHP-обёртки [zmq3821/jd_biz](https://github.com/zmq3821/jd_biz).
- Sandbox / тестовый: **TBD** — VOP не предоставляет публичный sandbox; тесты идут на боевом контуре после выдачи тестового `app_key`. Вместо sandbox используем mock-клиент.

### Авторизация

VOP — **REST + token в теле запроса** (это **НЕ** JOS-стиль с MD5-подписью URL-параметров; на это легко наступить, если идти от поиска).

Поток:
1. В кабинете VOP создаётся приложение. Выдаются `app_key`, `app_secret`, `username`, `password` (логин корпоративного пользователя JD).
2. Получение `access_token` — отдельным вызовом TokenLib (точный путь **TBD**, в `zmq3821/jd_biz` он скрыт за `TokenLib::getAccessToken()`). Предположительно `/api/getAccessToken` или аналог; уточним при первом ручном тесте.
3. Полученный токен кладётся в **тело POST-запроса** под ключом `token` ко всем бизнес-эндпоинтам.
4. **TTL access_token: TBD** — в VOP-кабинете будет указано, обычно 24h. Refresh-token поток — **TBD**.

В коде это инкапсулируется в `src/jd/auth.py::JdAuth.get_token()` с кешем в БД и автоматическим перевыпуском.

### Эндпоинты (подтверждены по исходникам zmq3821/jd_biz)

| Назначение | Путь | Что нужно нам |
|---|---|---|
| Список новых заказов | `POST /api/checkOrder/checkNewOrder` | **Да, основной pull** |
| Список доставленных | `POST /api/checkOrder/checkDlokOrder` | По желанию |
| Список отказов | `POST /api/checkOrder/checkRefuseOrder` | По желанию |
| Список завершённых | `POST /api/checkOrder/checkCompleteOrder` | По желанию |
| Детали заказа | `POST /api/order/selectJdOrder` | **Да** |
| Поиск JD-заказа по внешнему № | `POST /api/order/selectJdOrderIdByThirdOrder` | По желанию |
| Трекинг доставки | `POST /api/order/orderTrack` | По желанию |
| Создание заказа | `POST /api/order/submitOrder` | Не нужно (мы read-only к JD) |
| Отмена | `POST /api/order/cancel` | Нет |
| Подтверждение | `POST /api/order/confirmOrder` | Нет |
| Подтверждение получения | `POST /api/order/confirmReceived` | Нет |

Точная схема параметров каждого эндпоинта (поля JSON-тела) — **TBD**, уточняется при первом ручном вызове в кабинете VOP. В коде вынесем пути в `src/jd/methods.py` константами, поля — в `src/jd/schemas.py`.

### Whitelisted callback URL

Регистрируется при создании приложения. Назначение: webhook от JD (нотификации о новых заказах) и/или OAuth-redirect, если применяется. В сервисе зарезервируем `POST /jd/callback` (HTTPS, публичный).

### Rate limits

**TBD.** В публичной документации лимиты не озвучены; пишутся в кабинете приложения. По умолчанию закладываем экспоненциальный backoff на 5xx/timeout через `tenacity`.

### Сигнатура запросов

В отличие от JOS (JD Open Services с `sign=MD5(...)`), VOP **подписи не требует** — авторизация по `token` в теле. Это упрощает клиент. Подтверждено по `zmq3821/jd_biz/src/request/Request.php`: токен прокидывается в `$postData['token']`, MD5-обвязки нет.

---

## 2. СДЭК — отложено

По решению заказчика на текущей итерации СДЭК **не реализуется**. Цель текущего этапа — выгружать данные из JD и хранить их у себя. Интеграция со СДЭК будет добавлена отдельным шагом, когда определится формат склад-отправитель/тариф/международный профиль.

Сохранённые на будущее факты (чтобы не терять):

- Production base: `https://api.cdek.ru/v2/`
- Sandbox base: `https://api.edu.cdek.ru/v2/`
- OAuth: `POST {base}/oauth/token` с `grant_type=client_credentials`, `client_id`, `client_secret`. TTL — **3600 секунд**. Заголовок: `Authorization: Bearer ...`.
- Создание заказа: `POST {base}/orders` с `type`, `number`, `tariff_code`, `recipient`, `from_location`, `to_location`, `packages[].items[]`.

Источники: [AntistressStore/cdek-sdk-v2/Constants.php](https://github.com/AntistressStore/cdek-sdk-v2), [shevernitskiy/cdek](https://github.com/shevernitskiy/cdek).

---

## 3. Решения по проекту (зафиксированные с заказчиком 2026-05-05)

| # | Вопрос | Решение |
|---|---|---|
| 1 | Стек | Python **3.12** + FastAPI + httpx + Pydantic v2 + SQLAlchemy 2.0 + Alembic. Менеджер пакетов — `uv`. |
| 2 | Режим без JD-кредов | `JD_MODE=mock` (фикстуры в `src/jd/mock.py`) или `JD_MODE=live`. |
| 3 | СДЭК | Отложено. Из проекта удалены клиент/маппер/таблица CdekOrder. Оставлен только pull JD → БД. |
| 4 | Доставка | Международная, со склада в КНР. Расчёт стоимости не нужен. |
| 4a | Валюта | JD отдаёт CNY. Конвертация в RUB по **статичному курсу из ENV** (`CNY_RUB_RATE`), правится вручную. Каждое применение курса логируется (`correlation_id`, исходное значение, курс, результат). |
| 4b | Габариты/вес | Если JD не отдаёт — fallback на `DEFAULT_WEIGHT_G`, `DEFAULT_LWH_CM` из ENV + warning в лог. |
| 5 | Хостинг | Reg.ru (VPS) предпочтителен; в README — пошаговая инструкция под Reg.ru с Caddy для автоматического HTTPS. |
| 6 | Точные имена методов JD | Используем REST-пути из таблицы выше (подтверждено по SDK). При расхождении с реальным кабинетом — пути правятся в одном месте (`src/jd/methods.py`). |

---

## 4. Открытые TBD к моменту получения JD-кредов

1. Точный путь и формат запроса/ответа `getAccessToken`.
2. Формат тела для `checkNewOrder` (как фильтровать по дате? `startDate`/`endDate`? пагинация — `pageNo`/`pageSize`?).
3. Формат поля адреса в `selectJdOrder` (китайский адрес — отдельные поля province/city/county/town или единая строка?).
4. Структура `items` (наименование, количество, цена, валюта, единица измерения).
5. Передаются ли в заказе габариты/вес или их надо запрашивать через `productDetail`.
6. TTL `access_token` и наличие refresh-flow.
7. Whitelisted URL — формат пинг-проверки от JD (HEAD? GET? POST с подписью?).
8. Лимиты QPS.

Все эти TBD не блокируют написание скелета и mock-сценария — закрываются при первом ручном вызове в боевом VOP.
