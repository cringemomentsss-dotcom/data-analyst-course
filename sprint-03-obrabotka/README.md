# Спринт 3. PostgreSQL: обработка данных

**1 неделя.** Здесь заканчивается «умею писать запросы» и начинается «умею собирать данные под задачу». Один `SELECT` из одной таблицы не отвечает ни на один настоящий вопрос бизнеса — данные всегда лежат в разных местах, с пропусками, дубликатами и разной зернистостью.

**На выходе:** проект на данных оператора связи и понимание, почему после `JOIN` сумма выросла втрое.

Тренажёр: [trenazher/zadachi.sql](trenazher/zadachi.sql), 18 задач. Решай по ходу чтения — каждая привязана к своей части.

---

## Часть 1. Связи между таблицами

### 1.1. Типы связей

| Связь | Пример | Как выглядит в схеме |
|---|---|---|
| 1:1 | игрок ↔ его паспортные данные | внешний ключ с уникальным индексом |
| 1:N | игрок → его ставки | внешний ключ в таблице «многих» |
| N:M | плейлист ↔ треки | отдельная таблица-связка |

В нашей базе: `users` 1:N `bets`, `users` 1:N `deposits`, `games` 1:N `bets`, а `playlist_tracks` в базе «Потока» — классическая связка N:M.

### 1.2. Ключи

**Первичный ключ** — столбец (или набор), однозначно определяющий строку. **Внешний ключ** — ссылка на первичный ключ другой таблицы. СУБД не даст записать ставку несуществующего игрока — это и есть ссылочная целостность.

Важно для аналитика: наличие внешнего ключа — гарантия, что `JOIN` не потеряет строки из-за «висящих» ссылок. Отсутствие — повод проверить.

### 1.3. Как прочитать незнакомую схему

Первое, что делаешь на новом месте. Порядок:

```sql
-- какие таблицы есть и сколько в них строк
SELECT relname, n_live_tup FROM pg_stat_user_tables
WHERE schemaname = 'casino' ORDER BY n_live_tup DESC;

-- какие столбцы в таблице и каких типов
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'casino' AND table_name = 'deposits'
ORDER BY ordinal_position;

-- какие внешние ключи куда ведут
SELECT tc.table_name, kcu.column_name,
       ccu.table_name AS references_table, ccu.column_name AS references_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu USING (constraint_name)
JOIN information_schema.constraint_column_usage ccu USING (constraint_name)
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'casino';
```

Эти три запроса дают ER-диаграмму без всякого инструмента. Сохрани их — понадобятся на каждой новой работе.

### 1.4. Нормализация и почему её нарушают

Нормализация — устранение дублирования: страна игрока хранится один раз в `users`, а не в каждой его ставке. Это правильно для продуктовой базы: обновить страну надо в одном месте.

Для аналитики это неудобно: чтобы посчитать оборот по странам, нужен `JOIN`. Поэтому в аналитических хранилищах нормализацию сознательно нарушают и строят **звезду**: таблица фактов (ставки) в центре, таблицы измерений (игроки, игры, даты) по краям, и часть атрибутов дублируется прямо в факте.

Подробно — в модуле 6. Пока достаточно понимать, что схема продуктовой базы оптимизирована не под тебя.

---

## Часть 2. JOIN

### 2.1. Типы

```sql
FROM a INNER JOIN b ON a.id = b.a_id   -- только совпавшие
FROM a LEFT  JOIN b ON a.id = b.a_id   -- все из a, из b что нашлось
FROM a RIGHT JOIN b ON a.id = b.a_id   -- зеркально; почти не используется
FROM a FULL  JOIN b ON a.id = b.a_id   -- всё из обеих
FROM a CROSS JOIN b                    -- все пары
```

`RIGHT JOIN` существует, но читается плохо: глаз ожидает, что главная таблица слева. Пиши `LEFT`, меняя таблицы местами.

`CROSS JOIN` нужен реже, чем кажется, но незаменим для календарей и матриц: «все даты × все каналы», чтобы в отчёте не пропали пустые комбинации.

### 2.2. ON против WHERE

Разница проявляется только на внешних соединениях, и это одна из двух главных ловушек `JOIN`.

```sql
-- условие в ON: игроки без успешных депозитов остаются, у них 0
SELECT u.country, count(d.deposit_id)
FROM users u LEFT JOIN deposits d
  ON d.user_id = u.user_id AND d.status = 'success'
GROUP BY u.country;

-- условие в WHERE: LEFT JOIN превращается в INNER
SELECT u.country, count(d.deposit_id)
FROM users u LEFT JOIN deposits d ON d.user_id = u.user_id
WHERE d.status = 'success'
GROUP BY u.country;
```

Почему: `ON` работает во время соединения, `WHERE` — после. У игрока без депозитов `LEFT JOIN` подставит `NULL` во все столбцы `d`, а условие `d.status = 'success'` на `NULL` даст `NULL`, то есть не `true`, и строка отфильтруется.

Правило: **фильтр по правой таблице внешнего соединения — в `ON`. Фильтр по левой — в `WHERE`.**

> **Упражнение:** задача t3.3. Реши сначала с условием в `WHERE`, посмотри на число строк, потом перенеси в `ON`.

### 2.3. Fan-out

Вторая ловушка, и более дорогая, потому что не выдаёт себя ошибкой.

Если соединить `users` с `sessions` (у игрока 5 сессий) и с `deposits` (у него 3 депозита), получится 15 строк на одного игрока. Сумма депозитов вырастет впятеро, число сессий — втрое.

```sql
-- НЕВЕРНО: депозиты размножены сессиями
SELECT u.source, sum(d.amount_eur), count(s.session_id)
FROM users u
LEFT JOIN deposits d ON d.user_id = u.user_id
LEFT JOIN sessions s ON s.user_id = u.user_id
GROUP BY u.source;
```

Правильный способ — агрегировать каждую сторону отдельно, потом соединить:

```sql
WITH dep AS (SELECT user_id, sum(amount_eur) AS dep_sum FROM deposits
             WHERE status='success' GROUP BY user_id),
     ses AS (SELECT user_id, count(*) AS sessions FROM sessions GROUP BY user_id)
SELECT u.source, sum(dep.dep_sum), sum(ses.sessions)
FROM users u
LEFT JOIN dep ON dep.user_id = u.user_id
LEFT JOIN ses ON ses.user_id = u.user_id
GROUP BY u.source;
```

**Как ловить.** Перед любым `JOIN` и после него сравни число строк:

```sql
SELECT count(*) FROM users;                       -- 1200
SELECT count(*) FROM users u JOIN bets b ON ...;  -- 51087 — размножение есть
```

Если это ожидаемо (одна строка на ставку) — хорошо. Если ты собирался получить строку на игрока — ошибка. Возьми это в привычку: она отделяет аналитика, которому доверяют цифры, от того, кому не доверяют.

> **Упражнение:** задача t3.4. Сначала посчитай «в лоб», зафиксируй результат, потом правильно. Разница покажет масштаб проблемы.

### 2.4. Анти-джойн

«Кто есть в A, но не в B» — три способа:

```sql
-- 1. LEFT JOIN + IS NULL  (обычно быстрее всего)
SELECT count(*) FROM users u
LEFT JOIN bets b ON b.user_id = u.user_id
WHERE b.user_id IS NULL;

-- 2. NOT EXISTS  (читается лучше всего, безопасен к NULL)
SELECT count(*) FROM users u
WHERE NOT EXISTS (SELECT 1 FROM bets b WHERE b.user_id = u.user_id);

-- 3. NOT IN  (ОПАСНО, если подзапрос может вернуть NULL)
SELECT count(*) FROM users
WHERE user_id NOT IN (SELECT user_id FROM bets);
```

Третий вариант при наличии `NULL` в подзапросе молча вернёт ноль строк. Первые два — нет. Используй первые два.

### 2.5. Самосоединение

Таблица соединяется сама с собой: найти пары, сравнить строку с предыдущей, разложить иерархию.

```sql
-- пары депозитов одного игрока, сделанных в один день
SELECT a.user_id, a.deposit_id, b.deposit_id
FROM deposits a JOIN deposits b
  ON a.user_id = b.user_id
 AND a.deposit_ts::date = b.deposit_ts::date
 AND a.deposit_id < b.deposit_id;
```

Условие `a.id < b.id` избавляет от дублей пар и от соединения строки с самой собой. В большинстве задач, где напрашивается самосоединение, оконная функция короче — это уже спринт 4.

---

## Часть 3. Пропуски и дубликаты

### 3.1. Откуда берутся пропуски

Четыре источника, и решение зависит от источника:

| Источник | Пример | Что делать |
|---|---|---|
| Не собрали | страна не определилась по IP | оставить как «неизвестно», отдельной категорией |
| Не заполнили | необязательное поле формы | то же |
| Потеряли при джойне | `LEFT JOIN` не нашёл пары | искать причину, это часто баг |
| Логически нет | `dep_number` у неуспешного депозита | это не пропуск, это корректный `NULL` |

Последняя строка важна: `NULL` не всегда проблема. `churn_date IS NULL` означает «абонент действующий» — это значимая информация, а не дыра.

### 3.2. Явные дубликаты

Полностью совпадающие строки. Ищем так:

```sql
SELECT visitor_id, event_ts, event_name, count(*)
FROM page_events
GROUP BY 1,2,3 HAVING count(*) > 1;
```

Ключевое решение — **что считать дубликатом**. Полное совпадение всех столбцов? Совпадение по смысловому ключу? В `page_events` у дублей разные `page_event_id`, поэтому по всем столбцам они не совпадают, а по смыслу это одно событие.

### 3.3. Неявные дубликаты

Одна сущность, записанная по-разному: `facebook` и `Facebook`, «Иван Петров» и «Иван П.», «Заречная» и «Заречная ».

```sql
-- увидеть масштаб
SELECT lower(trim(utm_source)) AS canon, count(DISTINCT utm_source) AS variants, count(*)
FROM visitors
GROUP BY 1 HAVING count(DISTINCT utm_source) > 1;
```

Приведение к канону: `lower`, `trim`, `replace`, регулярки. Там, где автоматика не справляется (сокращения имён), нужен справочник соответствий и решение человека.

### 3.4. DISTINCT, GROUP BY, DISTINCT ON

```sql
SELECT DISTINCT country FROM users;              -- уникальные значения
SELECT country FROM users GROUP BY country;      -- то же самое
```

Разница появляется, когда нужны не просто уникальные значения, а **первая строка в каждой группе**. Здесь у PostgreSQL есть `DISTINCT ON` — конструкция, которой нет ни в SQLite, ни в стандарте:

```sql
-- первая ставка каждого игрока
SELECT DISTINCT ON (user_id) user_id, bet_ts, game_id
FROM bets
ORDER BY user_id, bet_ts, bet_id;
```

`DISTINCT ON (x)` оставляет по одной строке на каждое значение `x` — ту, что идёт первой согласно `ORDER BY`. Обязательное условие: `ORDER BY` начинается с тех же столбцов, что и `DISTINCT ON`.

Тай-брейк (`bet_id` в примере) нужен всегда: если у игрока две ставки в одну секунду, без него результат недетерминирован.

> **Упражнение:** задача t3.10.

---

## Часть 4. Операции над множествами

```sql
SELECT a FROM t1 UNION     SELECT a FROM t2;   -- объединение, дубликаты убраны
SELECT a FROM t1 UNION ALL SELECT a FROM t2;   -- объединение как есть
SELECT a FROM t1 INTERSECT SELECT a FROM t2;   -- пересечение
SELECT a FROM t1 EXCEPT    SELECT a FROM t2;   -- разность
```

Требования: одинаковое число столбцов и совместимые типы. Имена берутся из первого запроса.

`UNION` убирает дубликаты, а значит сортирует или хеширует весь результат — это дорого. Если дубликатов быть не может (складываем депозиты и выводы), пиши `UNION ALL`. Разница на миллионе строк — секунды.

Где реально нужно:
- сложить разнородные потоки в один (движение денег: приход и расход);
- собрать строки отчёта, которые считаются по-разному (итоговая строка «Всего»);
- сравнить два множества: что появилось, что пропало.

> **Упражнения:** задачи t3.6 и t3.7.

---

## Часть 5. Подзапросы

### 5.1. Четыре вида

**Скалярный** — возвращает одно значение, ставится куда угодно:

```sql
SELECT category, sum(stake_eur),
       round(100.0 * sum(stake_eur) / (SELECT sum(stake_eur) FROM bets), 1) AS share
FROM bets JOIN games USING (game_id) GROUP BY category;
```

**В `FROM`** — временная таблица:

```sql
SELECT source, avg(dep_sum) FROM (
  SELECT u.source, sum(d.amount_eur) AS dep_sum
  FROM users u JOIN deposits d ON d.user_id = u.user_id
  GROUP BY u.source, u.user_id
) t GROUP BY source;
```

**В `WHERE` через `IN` / `EXISTS`** — фильтр по наличию:

```sql
WHERE user_id IN (SELECT user_id FROM deposits WHERE status='success')
WHERE EXISTS (SELECT 1 FROM deposits d WHERE d.user_id = u.user_id)
```

**Коррелированный** — ссылается на внешний запрос и выполняется для каждой строки:

```sql
SELECT u.user_id,
       (SELECT count(*) FROM bets b WHERE b.user_id = u.user_id) AS bets
FROM users u;
```

Коррелированные подзапросы читаются легко и работают медленно: для каждой из 1200 строк выполняется отдельный запрос. На аналитических объёмах почти всегда лучше `JOIN` с предварительной агрегацией.

### 5.2. IN против EXISTS

`EXISTS` останавливается на первом совпадении, `IN` материализует весь список. На больших подзапросах `EXISTS` быстрее. И, главное, `EXISTS` безопасен к `NULL`, а `NOT IN` — нет.

Практическое правило: **`EXISTS` / `NOT EXISTS` по умолчанию**, `IN` — только для коротких явных списков (`IN ('card','crypto')`).

> **Упражнения:** задачи t3.8, t3.9.

---

## Часть 6. CTE

### 6.1. Зачем

```sql
WITH ftd AS (
  SELECT DISTINCT ON (user_id) user_id, amount_eur, deposit_ts
  FROM deposits WHERE status='success' AND dep_number=1
  ORDER BY user_id, deposit_ts, deposit_id
),
by_source AS (
  SELECT u.source, count(*) AS regs, count(f.user_id) AS ftd_cnt,
         avg(f.amount_eur) AS avg_ftd
  FROM users u LEFT JOIN ftd f ON f.user_id = u.user_id
  GROUP BY u.source
)
SELECT * FROM by_source ORDER BY regs DESC;
```

Тот же запрос через вложенные подзапросы читается втрое хуже. CTE — главный инструмент аналитика не потому, что быстрее (он не быстрее), а потому, что **запрос на 80 строк можно перечитать через месяц.**

Правила именования: CTE называется по смыслу того, что в нём лежит — `ftd`, `active_users`, `monthly_revenue`. Не `t1`, `t2`, `a`, `tmp`.

### 6.2. Что важно знать про производительность

До PostgreSQL 12 CTE всегда материализовался — вычислялся целиком, даже если снаружи нужна одна строка. С версии 12 планировщик сам решает, встроить его или материализовать. Управлять можно явно:

```sql
WITH heavy AS MATERIALIZED (...)      -- посчитать один раз
WITH light AS NOT MATERIALIZED (...)  -- встроить в основной запрос
```

`MATERIALIZED` полезен, когда CTE тяжёлый и используется дважды. В остальных случаях доверяй планировщику.

### 6.3. Рекурсивный CTE

Для иерархий и цепочек:

```sql
WITH RECURSIVE chain AS (
  SELECT attempt_id, 1 AS len          -- якорь: начала цепочек
  FROM payment_attempts WHERE retry_of IS NULL
  UNION ALL
  SELECT p.attempt_id, c.len + 1       -- рекурсивная часть
  FROM payment_attempts p JOIN chain c ON p.retry_of = c.attempt_id
)
SELECT max(len) FROM chain;
```

Устройство: якорная часть даёт стартовые строки, рекурсивная присоединяется к уже полученным, пока не перестанет находить новые.

Где нужно аналитику: организационные иерархии, категории с подкатегориями, цепочки платёжных ретраев, реферальные деревья. И — генерация последовательностей, хотя для этого есть `generate_series`.

Осторожно: цикл в данных (A ссылается на B, B на A) даст бесконечную рекурсию. Защита — счётчик глубины с ограничением.

> **Упражнения:** задачи t3.11, t3.17.

---

## Часть 7. Категоризация

```sql
SELECT CASE
         WHEN amount_eur < 20  THEN '1. до 20'
         WHEN amount_eur < 50  THEN '2. 20-50'
         WHEN amount_eur < 100 THEN '3. 50-100'
         ELSE '4. 100+'
       END AS bucket,
       count(*)
FROM deposits WHERE status='success' AND dep_number=1
GROUP BY bucket ORDER BY bucket;
```

Два приёма из этого примера:

1. **Числовой префикс в названии бакета** (`'1. до 20'`). Без него сортировка будет алфавитной, и `'100+'` окажется перед `'20-50'`. Альтернатива — сортировать по отдельному выражению, но префикс проще и виден в отчёте.
2. **Условия проверяются сверху вниз**, первое сработавшее выигрывает. Поэтому границы не надо описывать дважды: `WHEN amount_eur < 50` уже означает «от 20 до 50», раз предыдущее условие не сработало.

Полезные сокращения:

```sql
COALESCE(country, 'unknown')       -- первое не-NULL
NULLIF(divisor, 0)                 -- защита от деления на ноль
GREATEST(a, b), LEAST(a, b)        -- максимум и минимум из аргументов
```

> **Упражнение:** задача t3.12.

---

## Часть 8. Даты и время

### 8.1. Типы

| Тип | Что хранит | Когда |
|---|---|---|
| `date` | дата | день рождения, дата регистрации |
| `timestamp` | дата и время без пояса | когда пояс один на всю систему |
| `timestamptz` | момент времени | почти всегда правильный выбор |
| `interval` | промежуток | результат вычитания дат |

**Про часовые пояса.** `timestamp` хранит «14:30», не отвечая на вопрос «14:30 где». Если сервер в UTC, а бизнес считает сутки по Алматы, дневной отчёт будет сдвинут на пять часов — и половина ночных событий уедет в соседний день. Это не гипотетическая проблема: расхождения между отчётом маркетинга и отчётом продукта чаще всего именно отсюда.

```sql
SELECT deposit_ts AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Almaty' FROM deposits;
```

В нашей базе всё в `timestamp` и в UTC — как в большинстве продуктовых баз.

### 8.2. Усечение и извлечение

```sql
date_trunc('day',   bet_ts)          -- начало суток
date_trunc('week',  bet_ts)          -- понедельник этой недели
date_trunc('month', bet_ts)          -- первое число месяца
date_trunc('quarter', bet_ts)

extract(hour  FROM bet_ts)           -- 0-23
extract(dow   FROM bet_ts)           -- день недели, 0 = воскресенье
extract(isodow FROM bet_ts)          -- 1 = понедельник
extract(epoch FROM (b - a))          -- разница в секундах
```

`date_trunc` возвращает `timestamp`, поэтому для группировки по дням обычно приводят: `date_trunc('week', bet_ts)::date`.

В PostgreSQL неделя по ISO начинается с понедельника — в отличие от SQLite, где приходилось считать вручную.

### 8.3. Арифметика

```sql
reg_date + 1                              -- следующий день (для date)
reg_ts + interval '7 days'
deposit_ts - reg_ts                       -- interval
age(deposit_ts, reg_ts)                   -- в годах/месяцах/днях, для человека
extract(epoch FROM (deposit_ts - reg_ts)) / 3600.0   -- в часах, для расчёта
```

`age()` возвращает человекочитаемое «1 mon 3 days» — годится для отчёта, не годится для сортировки и агрегации. Для расчётов бери `epoch`.

### 8.4. Календарь без дыр

Главный приём этой части.

Если сгруппировать депозиты по дням, дни без депозитов просто исчезнут из результата. График нарисует прямую линию между соседними точками — и провала не будет видно вообще. Отчёт соврёт, не показав ошибки.

```sql
SELECT d::date AS d, count(dp.deposit_id) AS deposits
FROM generate_series('2026-03-01'::date, '2026-03-31'::date, '1 day') AS d
LEFT JOIN deposits dp
  ON dp.deposit_ts::date = d::date AND dp.status = 'success'
GROUP BY d ORDER BY d;
```

`generate_series` создаёт полный ряд дат, `LEFT JOIN` подвешивает к нему данные, `count` по столбцу правой таблицы даёт 0 там, где данных нет. Обрати внимание: `count(dp.deposit_id)`, а не `count(*)` — второй вернул бы 1 для пустых дней.

Тот же приём для матрицы «дата × канал»: `generate_series` CROSS JOIN список каналов.

Это не педантизм. В нашей базе `marketing_spend` не покрывает три дня — без календаря без дыр расходы за февраль будут занижены, и никто этого не заметит.

> **Упражнения:** задачи t3.13–t3.16, t3.18.

---

## Проект спринта

Анализ тарифов и активности абонентов оператора связи «Мегасеть». ТЗ и критерии приёмки — в [project/README.md](project/README.md).

---

## Литература

- [Документация PostgreSQL 17 на русском](https://postgrespro.ru/docs/postgresql/17/index) — разделы 7.8 (`WITH`), 9.9 (дата и время), 7.4 (операции над множествами).
- [Date/Time Functions and Operators](https://postgrespro.ru/docs/postgresql/17/functions-datetime) — таблица, к которой будешь возвращаться постоянно.
- Cathy Tanimura, *SQL for Data Analysis* (O'Reilly, 2021) — главы 3 (работа со временем), 4 (когорты), 8 (сложные запросы).
- Anthony Molinaro, *SQL Cookbook* (2-е изд., 2020) — справочник рецептов: «как сделать X» с готовым решением.
- Ralph Kimball, *The Data Warehouse Toolkit* (3-е изд., 2013) — главы 1–2 про звезду и снежинку. Читать не всю, но модель понять нужно.
- [Modern SQL](https://modern-sql.com/) — Markus Winand про возможности стандарта, которые появились после 1992 года и о которых мало кто знает.
