import pandas as pd, sys
d = pd.read_csv(sys.argv[1])
d["kt_entity"] = d.name.str.startswith("KT CORP")
ne_ok = (d.news_events_pass > 0) & ~d.kt_entity          # KT: summaries name Keysight
gn_ok = d.gnews_pass > 0
news_any = ne_ok | gn_ok
contacts = d.contacts > 0
jobs = d.jobs > 0
tech_rows = d.techno > 0
tech_stack = d.techno_stack
score = d.intent_score > 0
cat = d.cat_usable
astra = d.name.str.startswith("PT ASTRA")


def cls(ready, blocked):
    return pd.Series(["BLOCKED" if b else ("READY" if r else "PARTIAL") for r, b in zip(ready, blocked)], index=d.index)


F = {}
F["Executive Dashboard"] = cls(jobs & contacts, d.firmo == 0)
F["Recent News Signals"] = cls(ne_ok & gn_ok, ~news_any)
F["Intent & Demand Signals"] = cls(cat & score & ~d.topics_mismatch, ~cat & ~score)
F["Opportunity Map"] = cls(news_any & contacts & tech_stack & (score | cat), ~news_any)
F["Stakeholder Map"] = cls(d.contacts >= 3, ~contacts)
F["Technographic Map"] = cls(tech_stack & d.webstack_tech, ~tech_rows)
F["Objection Playbook"] = cls(tech_rows & contacts, ~tech_rows)
F["Content Messaging"] = cls((d.firmo > 0) & tech_stack & score & gn_ok, ~((d.firmo > 0) | tech_stack | score | gn_ok))
F["Content Studio"] = cls(jobs & contacts, pd.Series(False, index=d.index))
F["Strategy Chat"] = cls(d.pdfs > 0, pd.Series(False, index=d.index))
F["Message Evaluator"] = cls(contacts, ~contacts & ~jobs)

m = pd.DataFrame(F)
m.insert(0, "account", d.name)
m.to_csv(sys.argv[2], index=False)
for f in F:
    vc = m[f].value_counts()
    print(f"{f:28s} R {vc.get('READY',0):3d}  P {vc.get('PARTIAL',0):3d}  B {vc.get('BLOCKED',0):3d}")

feat = list(F)
allready = (m[feat] == "READY").all(axis=1)
noblock = ~(m[feat] == "BLOCKED").any(axis=1)
print("all 11 ready", allready.sum(), "| none blocked", noblock.sum(), "| >=1 blocked", (~noblock).sum())
print("blocked count dist", (m[feat] == "BLOCKED").sum(axis=1).value_counts().to_dict())
print("ready count dist", (m[feat] == "READY").sum(axis=1).value_counts().sort_index().to_dict())
cells = m[feat].stack().value_counts(); print("cells", cells.to_dict(), "of", 220 * 11)
# detail lists
print("OM partial reasons: no contacts", int((news_any & ~contacts).sum()), "no stack", int((news_any & ~tech_stack).sum()), "no intent", int((news_any & ~(score | cat)).sum()))
print("ID partial: cat only", int((cat & ~score).sum()), "score only", int((~cat & score).sum()), "mismatch", int((cat & score & d.topics_mismatch).sum()))
print("CM partial reasons: no stack", int(~tech_stack.sum() if False else (~tech_stack).sum()), "no score", int((~score).sum()), "no gnews", int((~gn_ok).sum()))
print("ED partial: no jobs", int((~jobs).sum()), "no contacts", int((~contacts).sum()), "both", int((~jobs & ~contacts).sum()))
print("ME blocked", list(d[~contacts & ~jobs].name))
print("SM thin", int(((d.contacts > 0) & (d.contacts < 3)).sum()))
print("TM partial", list(d[tech_rows & ~(tech_stack & d.webstack_tech)].name))
print("CM partial list n", int((m['Content Messaging']=='PARTIAL').sum()))
print("no contacts & no jobs & ...", int((~contacts & ~jobs).sum()))
