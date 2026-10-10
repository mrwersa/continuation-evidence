"""Two independent probes of three offline recovery strategies.

Fresh recovery deliberately changes the accounting identity for the same
logical mandate. It is a negative control, not a Coordinator handover mode.
"""

import argparse
import json
from pathlib import Path

from coordinator_model import Coordinator, Rejected


def probe(strategy, amount):
    if strategy not in ('Refuse', 'Fresh recovery', 'Carry'):
        raise ValueError('unknown strategy')
    c = Coordinator()
    old = c.open('original', 'principal', 'old', 1000)
    assert c.admit(old, 'initial', 600) == 'allow'
    ticket = c.close(old)
    if strategy == 'Fresh recovery':
        active = c.open('fresh', 'principal', 'new', 1000)
    elif strategy == 'Carry':
        active = c.accept(ticket, 'new', 1000)
    else:
        active = old
    try:
        admitted = c.admit(active, 'probe', amount) == 'allow'
    except Rejected:
        if strategy != 'Refuse':
            raise
        admitted = False
    # Account for the original consumption even when recovery omits it.
    total = c.snapshot('original')[2]
    if strategy == 'Fresh recovery':
        total += c.snapshot('fresh')[2]
    return {'admitted': admitted, 'mandate_total': total}


def results():
    return {strategy: {str(amount): probe(strategy, amount) for amount in (300, 600)}
            for strategy in ('Refuse', 'Fresh recovery', 'Carry')}


def table():
    rows = []
    for strategy, probes in results().items():
        answers = ['Yes' if probes[str(amount)]['admitted'] else 'No' for amount in (300, 600)]
        rows.append(' & '.join([strategy, *answers]) + r' \\')
    return '\n'.join([
        r'% Generated comparison, checked by compare_recovery.py --check.',
        r'\begin{table}[htbp]', r'\centering',
        r'\caption{Offline recovery comparison after consuming 600 under a strict',
        r'1,000 threshold. Each column uses a separate run. Admitting 300 preserves',
        r'useful work, while admitting 600 makes the mandate total 1,200.}',
        r'\label{tab:recovery}',
        r'\begin{tabular}{@{}lcc@{}}', r'\toprule',
        r'Strategy & Admits next 300 & Admits next 600 \\', r'\midrule',
        *rows, r'\bottomrule', r'\end{tabular}', r'\end{table}', ''])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        if Path(__file__).with_name('coordinator_table.tex').read_text() != table():
            raise SystemExit('FAIL: recovery table differs from computed outcomes')
        print('PASS: offline recovery table matches independently initialised probes')
    else:
        print(json.dumps(results(), indent=2, sort_keys=True))
