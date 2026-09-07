"""One-hop source-adjacency ablation. No event history, graph writes or labels."""

def expand(index, scope, rows):
    # Three seeds, two neighbors each, one hop. Original ranking is the seed set.
    seeds = {r['rowid'] for r in rows[:3]}
    output, seen = [], set()
    for row in rows:
        candidates = [row]
        if row['rowid'] in seeds:
            candidates += [dict(r) for r in index.db.execute('''SELECT * FROM docs
                WHERE scope=? AND session=? AND ord BETWEEN ? AND ? AND rowid!=?
                ORDER BY ABS(ord-?),ord,id LIMIT 2''',
                (scope, row['session'], row['ord']-1, row['ord']+1, row['rowid'], row['ord']))]
        for candidate in candidates:
            if candidate['rowid'] not in seen:
                seen.add(candidate['rowid']);output.append(candidate)
    return output
