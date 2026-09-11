#!/usr/bin/env python3
"""
Датасет проекта спринта 2: музыкальный стриминговый сервис «Поток».

Схема stream в той же базе casino. Данные синтетические, детерминированные.
Запуск:  python3 generate_stream.py   →  CSV в ./out
"""
import csv, os, random
from datetime import datetime, timedelta

rnd = random.Random(4242)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
TS = "%Y-%m-%d %H:%M:%S"
START = datetime(2025, 7, 1)
END = datetime(2026, 6, 30)
DAYS = (END - START).days + 1

GENRES = ["pop", "rock", "hip-hop", "electronic", "jazz", "classical", "metal",
          "indie", "r&b", "folk"]
COUNTRIES = [("DE",.18),("PL",.13),("BR",.12),("MX",.10),("IN",.10),("CA",.08),
             ("PT",.07),("FI",.06),("NO",.05),("TR",.05),(None,.06)]
PLANS = [("free",.58),("individual",.27),("duo",.09),("family",.06)]
PRICE = {"free":0.00,"individual":9.99,"duo":13.99,"family":17.99}
DEVICES = [("mobile",.71),("desktop",.19),("smart_speaker",.06),("tv",.04)]
SOURCES = [("playlist",.41),("search",.24),("radio",.19),("album",.16)]

def pick(pairs):
    r=rnd.random(); acc=0.0
    for v,w in pairs:
        acc+=w
        if r<=acc: return v
    return pairs[-1][0]

def ts(d): return d.strftime(TS)

os.makedirs(OUT, exist_ok=True)

# ---- артисты -------------------------------------------------------------
SYL1 = ["Nor","Vel","Kai","Mor","Ash","Lun","Fen","Riv","Sol","Tor","Bly","Cyn",
        "Dus","Eve","Gla","Hol","Ira","Jun","Kel","Lyr"]
SYL2 = ["dane","wave","mora","fell","stone","light","brook","fire","haze","reef",
        "vale","crest","drift","gale","mint","noor","peak","rune","salt","tide"]
artists=[]
seen=set()
for aid in range(1, 401):
    for _ in range(80):
        name = rnd.choice(SYL1)+rnd.choice(SYL2)
        if rnd.random()<0.22: name = "The "+name
        if name not in seen:
            break
    else:
        name = f"{name} {aid}"
    seen.add(name)
    artists.append([aid, name, pick([(g,1/len(GENRES)) for g in GENRES]),
                    pick(COUNTRIES)])

# популярность артистов: длинный хвост
pop = sorted((rnd.paretovariate(1.25) for _ in artists), reverse=True)
art_w = [(a[0], p) for a,p in zip(artists, pop)]
tot = sum(p for _,p in art_w)
art_w = [(i, p/tot) for i,p in art_w]

# ---- треки ---------------------------------------------------------------
WORDS = ["Midnight","Golden","Paper","Static","Velvet","Broken","Neon","Slow",
         "Hollow","Bright","Silver","Wild","Quiet","Endless","Crimson","Little",
         "Distant","Electric","Weightless","Northern","Salt","Ember","Glass","Ivory"]
NOUNS = ["Hours","Rivers","Machines","Letters","Rooms","Lights","Winter","Ghosts",
         "Signals","Mornings","Waves","Streets","Fires","Names","Dreams","Bones",
         "Harbour","Orbit","Silence","Threads","Shadows","Gardens","Anchors"]
tracks=[]
for tid in range(1, 6001):
    aid = pick(art_w)
    title = f"{rnd.choice(WORDS)} {rnd.choice(NOUNS)}"
    dur = int(rnd.gauss(203, 58))
    dur = max(62, min(dur, 480))
    rel = START - timedelta(days=rnd.randrange(0, 2200))
    tracks.append([tid, aid, title, dur, rel.date().isoformat(),
                   1 if rnd.random()<0.13 else 0])
track_artist = {t[0]: t[1] for t in tracks}
track_dur = {t[0]: t[3] for t in tracks}

tr_pop = sorted((rnd.paretovariate(1.1) for _ in tracks), reverse=True)
tr_w = [(t[0], p) for t,p in zip(tracks, tr_pop)]
tot = sum(p for _,p in tr_w)
tr_w = [(i, p/tot) for i,p in tr_w]

# ---- пользователи --------------------------------------------------------
users=[]
for uid in range(1, 8001):
    signup = START + timedelta(days=int(rnd.random()**1.4 * DAYS))
    plan = pick(PLANS)
    users.append([uid, signup.date().isoformat(), pick(COUNTRIES), plan,
                  pick([("13-17",.09),("18-24",.28),("25-34",.31),
                        ("35-44",.19),("45+",.13)])])
user_plan = {u[0]: u[3] for u in users}
user_signup = {u[0]: datetime.fromisoformat(u[1]) for u in users}

# ---- подписки ------------------------------------------------------------
subs=[]; sid=0
for u in users:
    if u[3]=="free": continue
    start = user_signup[u[0]] + timedelta(days=rnd.randrange(0, 14))
    months = rnd.choices([1,2,3,5,8,12], weights=[18,14,17,17,17,17])[0]
    ended = start + timedelta(days=30*months)
    active = ended > END
    sid+=1
    subs.append([sid, u[0], u[3], ts(start),
                 None if active else ts(ended), PRICE[u[3]],
                 "active" if active else pick([("churned",.82),("paused",.18)])])

# ---- прослушивания -------------------------------------------------------
listens=[]; lid=0
for u in users:
    uid=u[0]
    su=user_signup[uid]
    days_active=(END-su).days
    if days_active<=0: continue
    base = {"free":11,"individual":34,"duo":30,"family":27}[u[3]]
    n = int(rnd.gauss(base, base*0.55) * days_active/30)
    n = max(0, min(n, 4000))
    for _ in range(n):
        d = su + timedelta(days=rnd.randrange(0, days_active))
        hour = rnd.choices(range(24), weights=[2,1,1,1,1,2,4,7,9,8,7,7,8,8,8,9,11,13,14,13,11,9,6,4])[0]
        when = d.replace(hour=hour, minute=rnd.randrange(60), second=rnd.randrange(60))
        tid = pick(tr_w)
        dur = track_dur[tid]
        # дослушал / переключил
        if rnd.random()<0.61:
            ms = dur*1000
        else:
            ms = int(dur*1000*rnd.random()**0.6)
        lid+=1
        listens.append([lid, uid, tid, ts(when), ms, pick(DEVICES), pick(SOURCES)])

# грязь: у части строк ms_played больше длительности трека (баг клиента)
for i in rnd.sample(range(len(listens)), int(len(listens)*0.004)):
    listens[i][4] = int(track_dur[listens[i][2]]*1000 * rnd.uniform(1.4, 3.0))

listens.sort(key=lambda r: r[3])
for i,r in enumerate(listens, 1): r[0]=i

# ---- плейлисты -----------------------------------------------------------
playlists=[]; pt=[]; pid=0
for u in users:
    for _ in range(rnd.choices([0,1,2,3,5],weights=[42,26,16,10,6])[0]):
        pid+=1
        created = user_signup[u[0]] + timedelta(days=rnd.randrange(0, max(1,(END-user_signup[u[0]]).days)))
        playlists.append([pid, u[0], f"{rnd.choice(WORDS)} {rnd.choice(['mix','vibes','list','set','tape'])}",
                          ts(created), 1 if rnd.random()<0.24 else 0])
        for _ in range(rnd.randrange(3, 45)):
            t = pick(tr_w)
            pt.append([pid, t, ts(created + timedelta(minutes=rnd.randrange(0, 60*24*90)))])

# грязь: один и тот же трек добавлен в плейлист дважды
for row in rnd.sample(pt, int(len(pt)*0.012)):
    pt.append(list(row))

def dump(name, header, rows):
    with open(os.path.join(OUT, name+".csv"), "w", newline="", encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"  {name:18s} {len(rows):>9,}")

print("Генерация «Потока»:")
dump("artists", ["artist_id","artist_name","genre","country"], artists)
dump("tracks", ["track_id","artist_id","title","duration_sec","release_date","is_explicit"], tracks)
dump("users", ["user_id","signup_date","country","plan","age_group"], users)
dump("subscriptions", ["sub_id","user_id","plan","started_at","ended_at","price_eur","status"], subs)
dump("listens", ["listen_id","user_id","track_id","listened_at","ms_played","device","source"], listens)
dump("playlists", ["playlist_id","user_id","title","created_at","is_public"], playlists)
dump("playlist_tracks", ["playlist_id","track_id","added_at"], pt)
print(f"\nГотово: {OUT}")
