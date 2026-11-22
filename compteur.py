#!/usr/bin/env python3
"""Compteur 30 jours (23/11 -> 23/12/2026) : 3 chiffres, lecture seule. Stdlib seule.
1 reels/7 jours (API Instagram Graph, jeton lu dans son fichier) ; 2 delai prise->publication (non mesurable : champ `recu`
de la rampe a lire sur le cerveau quand il existera) ; 3 decisions widget/notification (widget-taps.json du cerveau)."""
import json, os, subprocess, urllib.request
from datetime import date, datetime, timedelta, timezone

ICI = os.path.dirname(os.path.realpath(__file__))
DONNEES = os.path.join(ICI, "donnees")
HIST = os.path.join(DONNEES, "historique.jsonl")
BRUT = os.path.join(DONNEES, "brut")
TOKEN = os.path.expanduser("~/.local/share/damienprime/instagram-api/token")
CLE = os.path.expanduser("~/.local/share/damienprime/cerveau/cle")
CERVEAU = "damien@100.125.157.100"
DEBUT, FIN = date(2026, 11, 23), date(2026, 12, 23)
DECISIONS = {"oui", "non", "plus_tard", "fini", "bloque", "appliquee", "retirer_methode", "post"}


def ssh(cmd):
    r = subprocess.run(["ssh", "-i", CLE, "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", CERVEAU, cmd],
                       capture_output=True, text=True, timeout=40)
    if r.returncode:
        raise RuntimeError("ssh " + r.stderr.strip()[:100])
    return r.stdout


def reels_ig():
    tok = open(TOKEN).read().strip()
    url = ("https://graph.instagram.com/v21.0/me/media?fields=id,media_type,media_product_type,timestamp,permalink"
           "&limit=100&access_token=" + tok)
    out, pages = [], 0
    while url and pages < 6:
        with urllib.request.urlopen(url, timeout=30) as f:
            d = json.load(f)
        out += d.get("data", [])
        url = d.get("paging", {}).get("next")
        pages += 1
        if out and out[-1]["timestamp"] < "2026-09-01":
            break
    return [datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone().date()
            for m in out if m.get("media_product_type") == "REELS" or m.get("media_type") == "REELS"]


def sur7(jours, j):
    return sum(1 for x in jours if j - timedelta(days=6) <= x <= j)


def decisions_cerveau():
    d = json.loads(ssh("cat ~/tokn-data/widget-taps.json"))
    open(os.path.join(BRUT, "widget-taps.json"), "w").write(json.dumps(d))
    par_jour, tous = {}, {}
    for action, e in d.items():
        for j, n in e.get("jours", {}).items():
            tous[j] = tous.get(j, 0) + n
            if action in DECISIONS:
                par_jour[j] = par_jour.get(j, 0) + n
    return par_jour


def delai_rampe():
    """Mediane (jours) entre `recu` et la publication, si la rampe existe et porte les deux champs. Sinon None."""
    try:
        txt = ssh("cat ~/tokn-data/rampe/*/etat.json 2>/dev/null")
    except Exception:
        return None
    dec = json.JSONDecoder(); i = 0; ds = []
    while i < len(txt):
        try:
            o, k = dec.raw_decode(txt, i)
        except ValueError:
            i += 1; continue
        i = k
        r, p = o.get("recu"), o.get("publie") or o.get("publie_le")
        if r and p:
            try:
                ds.append((datetime.fromisoformat(p) - datetime.fromisoformat(r)).total_seconds() / 86400)
            except Exception:
                pass
    ds.sort()
    return round(ds[len(ds) // 2], 1) if ds else None


def lire_hist():
    h = {}
    if os.path.exists(HIST):
        for l in open(HIST):
            if l.strip():
                o = json.loads(l); h[o["jour"]] = o
    return h


def main():
    auj = date.today()
    h = lire_hist()
    erreurs = []
    try:
        jours = reels_ig()
        open(os.path.join(BRUT, "reels-jours.json"), "w").write(json.dumps([str(x) for x in jours]))
    except Exception as e:
        jours = None; erreurs.append("instagram: " + str(e)[:80])
    try:
        dec = decisions_cerveau()
    except Exception as e:
        dec = None; erreurs.append("cerveau: " + str(e)[:80])
    delai = delai_rampe()
    depart_reels = sur7(jours, DEBUT - timedelta(days=1)) if jours is not None else None
    if jours is not None:  # recalcul de tout l'historique (rolling 7 j, exact depuis les dates de publication)
        j = DEBUT
        while j <= min(auj, FIN):
            o = h.setdefault(j.isoformat(), {"jour": j.isoformat()})
            o["reels_7j"] = sur7(jours, j)
            j += timedelta(days=1)
    if dec is not None:
        j = DEBUT
        while j <= min(auj, FIN):
            o = h.setdefault(j.isoformat(), {"jour": j.isoformat()})
            o["decisions"] = dec.get(j.isoformat(), 0)
            j += timedelta(days=1)
    if auj.isoformat() in h:
        h[auj.isoformat()]["delai_j"] = delai
        h[auj.isoformat()]["maj"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = {}
    mf = os.path.join(DONNEES, "depart.json")
    if os.path.exists(mf):
        meta = json.load(open(mf))
    if depart_reels is not None:
        meta["reels_7j"] = depart_reels
    meta.setdefault("decisions", 0)
    meta.setdefault("delai_j", None)
    json.dump(meta, open(mf, "w"))
    with open(HIST, "w") as f:
        for k in sorted(h):
            f.write(json.dumps(h[k], ensure_ascii=False) + "\n")
    page(h, meta, erreurs, auj)
    for e in erreurs:
        print("ATTENTION", e)


def barres(h, cle, ref):
    mx = max([ref or 0] + [h[k].get(cle) or 0 for k in h] + [1])
    out, j = [], DEBUT
    while j <= FIN - timedelta(days=1):
        v = h.get(j.isoformat(), {}).get(cle)
        if v is None:
            out.append('<i class="vide"></i>')
        else:
            out.append(f'<i style="height:{max(4, round(100 * v / mx))}%" title="{j}: {v}"></i>')
        j += timedelta(days=1)
    return "".join(out)


def page(h, meta, erreurs, auj):
    cur = h.get(auj.isoformat(), {})
    def val(c):
        v = cur.get(c); return "non lu" if v is None else v
    cumul_dec = sum(o.get("decisions") or 0 for o in h.values())
    jour_n = max(0, min(30, (auj - DEBUT).days + 1))
    d_ref = meta.get("delai_j")
    delai_now = cur.get("delai_j")
    err = "".join(f"<p class='err'>Source en panne : {e}</p>" for e in erreurs)
    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>30 jours, 3 chiffres</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#121316;color:#ededef;font:17px/1.45 -apple-system,"Helvetica Neue",sans-serif;padding:20px 16px 48px;max-width:560px;margin:auto}}
h1{{font-size:28px;margin:8px 0 4px}}.sous{{color:#a4a6ad;margin:0 0 20px}}
.c{{background:#1d1f24;border-radius:14px;padding:18px;margin:0 0 16px}}.c h2{{font-size:18px;margin:0 0 12px;font-weight:600}}
.duo{{display:flex;gap:12px}}.duo div{{flex:1}}.n{{font-size:40px;font-weight:700;line-height:1.1}}.n.b{{color:#4f7dff}}
.l{{color:#a4a6ad;font-size:16px}}.bar{{display:flex;align-items:flex-end;gap:2px;height:72px;margin-top:16px}}
.bar i{{flex:1;background:#4f7dff;border-radius:2px 2px 0 0;display:block}}.bar i.vide{{background:#2a2d34;height:4px}}
.src{{color:#a4a6ad;font-size:16px;margin:12px 0 0}}.err{{color:#ededef;border-left:3px solid #4f7dff;padding-left:10px}}
</style></head><body>
<h1>30 jours, 3 chiffres</h1>
<p class="sous">Du 23 novembre au 23 décembre 2026. Jour {jour_n} sur 30. Mis à jour le {cur.get('maj','')}.</p>{err}
<div class="c"><h2>Reels publiés sur 7 jours</h2><div class="duo"><div><div class="n">{meta.get('reels_7j','non lu')}</div><div class="l">départ (7 j avant le 23/11)</div></div>
<div><div class="n b">{val('reels_7j')}</div><div class="l">aujourd'hui (7 derniers jours)</div></div></div>
<div class="bar">{barres(h,'reels_7j',meta.get('reels_7j'))}</div>
<p class="src">Mesuré : API Instagram Graph, reels de @damien.rsl, essais compris. TikTok et Shorts : pas de source en lecture seule branchée.</p></div>
<div class="c"><h2>Délai entre la prise et la publication</h2><div class="duo"><div><div class="n">non mesuré</div><div class="l">départ</div></div>
<div><div class="n b">{'non mesuré' if delai_now is None else str(delai_now)+' j'}</div><div class="l">aujourd'hui (médiane)</div></div></div>
<div class="bar">{barres(h,'delai_j',None)}</div>
<p class="src">Aucune date de prise fiable n'existe encore. Le chiffre apparaîtra quand la rampe notera la date de réception de chaque rush.</p></div>
<div class="c"><h2>Décisions prises depuis un widget</h2><div class="duo"><div><div class="n">{meta.get('decisions',0)}</div><div class="l">départ (compteur à 0 le 23/11)</div></div>
<div><div class="n b">{val('decisions')}</div><div class="l">aujourd'hui (total {cumul_dec} sur la période)</div></div></div>
<div class="bar">{barres(h,'decisions',None)}</div>
<p class="src">Mesuré : gestes oui, non, plus tard, fini, bloqué, appliqué, post reçus par le cerveau (journal widget-taps). Les notifications ne sont pas journalisées à part.</p></div>
</body></html>"""
    open(os.path.join(ICI, "index.html"), "w").write(html)


if __name__ == "__main__":
    main()
