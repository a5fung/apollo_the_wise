exec(open('/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/xref.py').read().split("def tier(k)")[0])
from collections import Counter
# independent: HIGH live alerts 05-11..09-03, first-pass (any tier) minute
mine_late=set(); mine_ctrl=set(); cnt=Counter()
for k,al in aby.items():
    fpt=min((a['first_pass_et'] for a in al if a['first_pass_et']), default='')
    if not fpt: cnt['no_scored_pass_tick']+=1; continue
    hi=any(a['score_tier']=='HIGH' for a in al)
    fm=fpt[:5]
    if '09:45'<=fm<'10:00': (mine_late if True else None).add(k); cnt[('late',hi)]+=1
    elif fm<'09:45': mine_ctrl.add(k); cnt[('inwin',hi)]+=1
    else: cnt['after10']+=1
print('my SQL (05-11..09-03 alert rows):',dict(cnt))
st_late=set(k for k in late if k[1]>='2026-05-11'); st_ctrl=set(k for k in ctrl if k[1]>='2026-05-11')
print('study late post-0511',len(st_late),'mine',len(mine_late),'overlap',len(st_late&mine_late),'study-only',sorted(st_late-mine_late)[:8],'mine-only',sorted(mine_late-st_late)[:8])
print('study ctrl post-0511',len(st_ctrl),'mine in-window',len(mine_ctrl),'overlap',len(st_ctrl&mine_ctrl),'mine-only (unreadable in study?)',len(mine_ctrl-st_ctrl))
# window skip rows (live) in the window: all HIGH late per live system
ws=[(t['ticker'],t['alert_date'],t['skip_reason']) for t in trades if t['skip_reason'].startswith('window:out_of_orb') and '2026-05-01'<=t['alert_date']<='2026-09-03']
print('live WINDOW_OUT_OF_ORB skip rows 05-01..09-03:',len(ws),' in study LATE:',sum(1 for w in ws if (w[0],w[1]) in set(late)))
notin=[w for w in ws if (w[0],w[1]) not in set(late)]
print('window rows NOT in study LATE:',notin)
