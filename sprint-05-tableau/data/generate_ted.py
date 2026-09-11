#!/usr/bin/env python3
"""
Датасет проекта спринта 5: выступления конференции TED.

Три файла — специально, чтобы отработать связи в Tableau:
  ted_talks.csv    одна строка = одно выступление
  ted_tags.csv     связь «многие ко многим»: выступление ↔ тема
  ted_ratings.csv  длинный формат: выступление × тип оценки

Присоединение тегов размножает строки и завышает просмотры. Это главная
ловушка спринта, и она здесь намеренная.

Запуск: python3 generate_ted.py
"""
import csv, os, random
from datetime import date, timedelta

rnd = random.Random(1984)
HERE = os.path.dirname(os.path.abspath(__file__))

EVENTS = [
    ("TED2010", 2010, "Long Beach", 1), ("TED2011", 2011, "Long Beach", 1),
    ("TED2012", 2012, "Long Beach", 1), ("TED2013", 2013, "Long Beach", 1),
    ("TED2014", 2014, "Vancouver", 1), ("TED2015", 2015, "Vancouver", 1),
    ("TED2016", 2016, "Vancouver", 1), ("TED2017", 2017, "Vancouver", 1),
    ("TED2018", 2018, "Vancouver", 1), ("TED2019", 2019, "Vancouver", 1),
    ("TED2020", 2020, "Online", 1), ("TED2021", 2021, "Online", 1),
    ("TED2022", 2022, "Vancouver", 1), ("TED2023", 2023, "Vancouver", 1),
    ("TEDGlobal 2011", 2011, "Edinburgh", 1), ("TEDGlobal 2012", 2012, "Edinburgh", 1),
    ("TEDGlobal 2013", 2013, "Rio de Janeiro", 1), ("TEDGlobal 2014", 2014, "Rio de Janeiro", 1),
    ("TEDGlobal 2017", 2017, "Arusha", 1), ("TEDGlobal 2019", 2019, "Addis Ababa", 1),
    ("TEDWomen 2013", 2013, "San Francisco", 1), ("TEDWomen 2015", 2015, "Monterey", 1),
    ("TEDWomen 2017", 2017, "New Orleans", 1), ("TEDWomen 2019", 2019, "Palm Springs", 1),
    ("TEDMED 2012", 2012, "Washington", 1), ("TEDMED 2014", 2014, "San Francisco", 1),
    ("TEDSalon NY", 2016, "New York", 0), ("TEDSalon London", 2018, "London", 0),
    ("TEDx Talks", 2015, "различные", 0), ("TEDYouth 2016", 2016, "New York", 0),
]

TAGS = ["technology","science","design","business","health","education","culture",
        "society","psychology","climate change","artificial intelligence","biology",
        "economics","politics","art","music","architecture","medicine","brain",
        "innovation","future","social change","communication","creativity","data",
        "environment","global issues","history","humanity","identity","internet",
        "leadership","learning","personal growth","physics","space","storytelling",
        "sustainability","war","women"]

CATEGORY_OF = {
    "technology":"Технологии","artificial intelligence":"Технологии","internet":"Технологии",
    "data":"Технологии","innovation":"Технологии","future":"Технологии",
    "science":"Наука","biology":"Наука","physics":"Наука","space":"Наука","brain":"Наука",
    "medicine":"Здоровье","health":"Здоровье",
    "design":"Дизайн","architecture":"Дизайн","art":"Искусство","music":"Искусство",
    "storytelling":"Искусство","creativity":"Искусство",
    "business":"Бизнес","economics":"Бизнес","leadership":"Бизнес",
    "education":"Образование","learning":"Образование","personal growth":"Образование",
    "communication":"Образование",
    "culture":"Общество","society":"Общество","politics":"Общество","history":"Общество",
    "humanity":"Общество","identity":"Общество","social change":"Общество",
    "global issues":"Общество","war":"Общество","women":"Общество","psychology":"Общество",
    "climate change":"Экология","environment":"Экология","sustainability":"Экология",
}

RATINGS = ["Inspiring","Informative","Fascinating","Persuasive","Beautiful","Courageous",
           "Funny","Ingenious","Jaw-dropping","Longwinded","Unconvincing","Obnoxious",
           "Confusing","OK"]
POSITIVE = set(RATINGS[:9])

OCCUPATIONS = ["писатель","психолог","нейробиолог","журналист","архитектор","предприниматель",
               "врач","физик","дизайнер","экономист","активист","инженер","художник",
               "музыкант","историк","биолог","педагог","режиссёр","философ","астроном",
               "программист","антрополог","юрист","эколог","математик"]

FIRST = ["Alex","Maria","John","Sara","Daniel","Emma","Liam","Nora","Omar","Ines",
         "Peter","Aisha","Ravi","Lena","Tom","Yuki","Carlos","Ana","David","Zoe",
         "Hugo","Mira","Noah","Elif","Jonas","Kira","Samir","Iris","Felix","Lucia"]
LAST = ["Meyer","Silva","Okafor","Nakamura","Ferrari","Novak","Hassan","Lindqvist",
        "Kowalski","Dubois","Reyes","Petrov","Adeyemi","Haugen","Berger","Moreau",
        "Castillo","Iversen","Fischer","Almeida","Kaplan","Nilsen","Vargas","Bauer"]

TITLE_A = ["Почему","Как","Что","Зачем","Отчего","Каким образом"]
TITLE_B = ["мы","города","дети","данные","мозг","климат","алгоритмы","деньги","язык",
           "медицина","океан","сон","страх","доверие","работа","память","привычки",
           "школы","роботы","бактерии","гены","реки","леса","выборы","музыка",
           "архитектура","старение","одиночество","вода","энергия","почва","вирусы",
           "нейросети","космос","время","эмоции","семьи","врачи","суды","границы"]
TITLE_C = ["меняют всё","обманывают нас","важнее, чем кажется","не работают",
           "решают за нас","определяют будущее","стоят дороже","нуждаются в защите",
           "устроены не так","говорят правду","держат нас вместе","исчезают",
           "требуют пересмотра","недооценены","опаснее, чем принято думать",
           "работают против нас","возвращаются","зависят от нас","молчат",
           "стали другими","сложнее, чем выглядят","заслуживают внимания"]


def pick(pairs):
    r = rnd.random(); acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc: return v
    return pairs[-1][0]


talks, tags_rows, ratings_rows = [], [], []
seen_titles = set()

for tid in range(1, 2751):
    ev, year, city, is_main = rnd.choice(EVENTS)
    rec = date(year, rnd.randint(1, 12), rnd.randint(1, 28))
    pub = rec + timedelta(days=rnd.randint(10, 200))
    if pub > date(2026, 6, 30):
        pub = date(2026, 6, 30)

    for attempt in range(60):
        title = f"{rnd.choice(TITLE_A)} {rnd.choice(TITLE_B)} {rnd.choice(TITLE_C)}"
        if title not in seen_titles:
            break
    else:
        title = f"{title} ({tid})"
    seen_titles.add(title)

    speakers = pick([(1, .93), (2, .05), (3, .02)])
    speaker = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
    occupation = rnd.choice(OCCUPATIONS) if rnd.random() > 0.07 else None

    # длительность: короткие TED-talks и длинные основные выступления
    dur = int(max(120, rnd.choice([
        rnd.gauss(360, 90), rnd.gauss(720, 150), rnd.gauss(1080, 180)])))
    dur = min(dur, 2400)

    # просмотры: тяжёлый хвост, старые выступления накопили больше
    age_years = max(0.3, (date(2026, 6, 30) - pub).days / 365.0)
    base = rnd.lognormvariate(13.1, 1.05)
    views = int(base * (1 + 0.16 * age_years) * (1.55 if is_main else 0.72))
    views = max(1200, min(views, 74_000_000))

    comments = max(0, int(views / rnd.uniform(2200, 12000)))
    languages = min(72, max(1, int(rnd.gauss(28, 12) + (views / 4_000_000))))

    # темы: от одной до пяти
    n_tags = pick([(1, .10), (2, .24), (3, .31), (4, .22), (5, .13)])
    my_tags = rnd.sample(TAGS, n_tags)
    for t in my_tags:
        tags_rows.append([tid, t, CATEGORY_OF.get(t, "Прочее")])

    talks.append([tid, title, speaker, occupation, speakers, ev, year, city,
                  1 if is_main else 0, rec.isoformat(), pub.isoformat(),
                  dur, views, comments, languages])

    # оценки: сумма примерно пропорциональна просмотрам
    total_votes = max(20, int(views / rnd.uniform(900, 3200)))
    weights = {r: rnd.random() ** (0.5 if r in POSITIVE else 2.2) for r in RATINGS}
    s = sum(weights.values())
    for r in RATINGS:
        cnt = int(total_votes * weights[r] / s)
        if cnt:
            ratings_rows.append([tid, r, cnt])

# ---- грязь ---------------------------------------------------------------
# у части выступлений не указана профессия спикера — уже сделано выше
# в тегах есть дубликаты: один тег присвоен выступлению дважды
for row in rnd.sample(tags_rows, int(len(tags_rows) * 0.008)):
    tags_rows.append(list(row))
# в названии события два написания одного и того же
for t in talks:
    if t[5] == "TEDGlobal 2013" and rnd.random() < 0.35:
        t[5] = "TED Global 2013"
# несколько выступлений с нулевой длительностью — запись не сохранилась
for t in rnd.sample(talks, 9):
    t[11] = 0

talks.sort(key=lambda r: r[10])
tags_rows.sort(key=lambda r: (r[0], r[1]))
ratings_rows.sort(key=lambda r: (r[0], r[1]))


def dump(name, header, rows):
    path = os.path.join(HERE, name + ".csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:16s} {len(rows):>8,} строк, {os.path.getsize(path)/1024:.0f} КБ")


print("Генерация датасета TED:")
dump("ted_talks", ["talk_id","title","speaker","speaker_occupation","num_speakers",
                   "event","event_year","event_city","is_main_conference",
                   "recorded_date","published_date","duration_sec","views",
                   "comments","languages"], talks)
dump("ted_tags", ["talk_id","tag","category"], tags_rows)
dump("ted_ratings", ["talk_id","rating","votes"], ratings_rows)
print(f"\nГотово: {HERE}")
