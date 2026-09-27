# Wikipedia Interest

**Wikipedia Interest** — навичка для AI-агента, яка досліджує зміну уваги до теми за переглядами статей Wikipedia. Вона допомагає порівняти мовні розділи, оцінити напрям тренду та підготувати графік і короткий звіт для подальшого обговорення.

Реалізація навички міститься в [skills/wikipedia-interest](skills/wikipedia-interest). Агент отримує інструкції з [SKILL.md](skills/wikipedia-interest/SKILL.md), а розрахунки й створення файлів виконує Python-код.

## Що виконує навичка

1. Знаходить і перевіряє статті у вибраних мовних розділах Wikipedia. Якщо відповідність неоднозначна, повертає запит на уточнення.
2. Отримує статистику Wikimedia Pageviews за вказаний період і зберігає її в кеші для повторного використання.
3. Порівнює рівні часові періоди, обчислює стійкий тренд і позначає чинники, які знижують надійність висновку: пропуски, неповні місяці, піки, сезонність або малу кількість переглядів.
4. За потреби перевіряє задані користувачем числові пороги або повторює аналіз без конкретного піку.
5. Створює PNG-графік і односторінковий PDF із метриками, поясненням, обмеженнями та посиланнями на джерела.

Одна стаття представляє одну мову. Перегляди статті є показником уваги до неї; вони самі по собі не доводять попит на продукт чи готовність платити.

## Швидкий запуск

Потрібен Python 3.11 або новіший. Із кореня проєкту встановіть залежності:

```sh
python3 -m venv /tmp/wikipedia-interest-venv
/tmp/wikipedia-interest-venv/bin/python -m pip install -r skills/wikipedia-interest/requirements.txt
```

Запустіть повний аналіз. Замініть `you@example.org` на власну контактну адресу або HTTPS-сторінку для запитів до Wikimedia:

```sh
/tmp/wikipedia-interest-venv/bin/python skills/wikipedia-interest/scripts/run.py \
  --topic 'Астрономія' \
  --languages uk \
  --start 2023-01-01 \
  --end 2024-12-31 \
  --contact 'you@example.org' \
  --cache-dir /tmp/wikipedia-interest-cache \
  --artifact-dir ./wikipedia-interest-result
```

За успішного запуску в `wikipedia-interest-result/` з’являться `resolved_pages.json`, `series.json`, `analysis.json`, `chart.png` і `report.pdf`. Команда також виведе стислий JSON зі статусом `complete` і шляхами до файлів. Якщо статті потребують уточнення, вона поверне `needs_confirmation` та зупиниться після `resolved_pages.json`.

Для наступного повного запуску задайте **нову** папку `--artifact-dir`. Попередні результати зберігаються; той самий кеш можна використовувати повторно. Перший запит до Wikipedia/Wikimedia потребує доступу до мережі.

## Де читати далі

| Документ | Зміст |
| --- | --- |
| [SKILL.md](skills/wikipedia-interest/SKILL.md) | Інструкції для AI-агента, який використовує навичку. |
| [methodology.md](skills/wikipedia-interest/references/methodology.md) | Формули тренду й правила оцінки надійності. |

Окремі етапи можна запускати скриптами `resolve_topic.py`, `fetch_pageviews.py`, `analyze_trend.py`, `plot.py` і `report.py` у [директорії scripts](skills/wikipedia-interest/scripts). Повний маршрут виконує `run.py`.
